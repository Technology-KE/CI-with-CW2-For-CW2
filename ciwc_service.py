"""CI × CW2 联动 —— CW2 端运行时。

职责：
1. 读写共享设置（两端同一份文件），把 CW2 的小组件位置等设置应用到自己身上；
2. 与 ClassIsland 端保持 TCP 连接，互发当前课程快照；
3. 主程序/副程序分工：副程序不再重复提醒（可关），并复用主程序的课程数据；
4. 提供 QML 需要的视图模型（状态、课程、课表、时钟）。
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

from ciwc_common import (
    APP_CI,
    APP_CW2,
    APP_NAMES,
    APP_SHORT_NAMES,
    as_bool,
    data_dir,
    deep_merge,
    now_ms,
    set_path,
    read_json,
    write_json_atomic,
)
from ciwc_bridge import LinkBridge
from ciwc_settings import SettingsStore

WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

STATUS_LABELS = {
    "class": "上课中",
    "break": "课间休息",
    "preparation": "课前准备",
    "activity": "活动",
    "free": "空闲",
    "after_school": "放学",
}


def _format_clock(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _format_remaining(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, rest = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} 小时 {minutes} 分"
    return f"{minutes} 分 {rest} 秒"


class LinkService(QObject):
    """联动运行时（主线程 QObject，网络线程只投递消息）。"""

    changed = Signal()
    settingsReloaded = Signal()

    def __init__(self, api, plugin_dir: Path, version: str) -> None:
        super().__init__()
        self.api = api
        self.plugin_dir = plugin_dir
        self.version = version
        self.pid = "com.kryon.ciwithcw2"

        self.local_path = data_dir() / "cw2_local.json"
        self.local_state = read_json(self.local_path, {}) or {}
        if not isinstance(self.local_state, dict):
            self.local_state = {}

        self.store = SettingsStore(source=APP_CW2)
        self._inbox: queue.Queue = queue.Queue()
        self.bridge = LinkBridge(
            on_message=self._inbox.put,
            on_status=lambda: self._inbox.put({"type": "_status"}),
            app_version=version,
        )

        self._peer_snapshot: dict = {}
        self._peer_snapshot_at = 0.0
        self._last_status: dict = {}
        self._snapshot: dict = self._empty_snapshot()
        self._last_send = 0.0
        self._last_local_write = 0.0
        self._layout_signature = ""
        self._started = False
        self._auto_launch_at = 0.0
        self._auto_target = ""

        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self.tick)

        self.store.subscribe(lambda _data: self.settingsReloaded.emit())

    # ------------------------------ 生命周期 ------------------------------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        settings = self.store.snapshot()
        self._apply_settings(settings, force=True)
        self.bridge.start(
            int(settings["network"]["port"]),
            str(settings["network"]["token"]),
        )
        self._snapshot = self._build_local_snapshot()
        self._timer.start()
        self._auto_launch_at = time.time() + 6.0
        logger.info("CI × CW2 联动（CW2 端）已启动，主程序：{}", APP_NAMES.get(settings["role"], settings["role"]))

    def stop(self) -> None:
        self._timer.stop()
        self.bridge.stop()

    # ------------------------------ 主循环 ------------------------------
    def tick(self) -> None:
        if self.store.reload_if_changed():
            self._apply_settings(self.store.snapshot())

        while True:
            try:
                message = self._inbox.get_nowait()
            except queue.Empty:
                break
            self._handle_message(message)

        status = self.bridge.status()
        if status != self._last_status:
            self._last_status = status
            self._apply_dedupe(self.store.snapshot())
            self.changed.emit()

        now = time.time()
        if now - self._last_send >= 1.0:
            self._last_send = now
            self._snapshot = self._build_local_snapshot()
            if status.get("connected"):
                self.bridge.send({"type": "state", "app": APP_CW2, "ts": now_ms(), "state": self._snapshot})

        self._apply_stack_layout()

        settings = self.store.snapshot()
        if settings.get("enabled") and settings["process"].get("auto_launch_peer"):
            if not status.get("connected") and now >= self._auto_launch_at:
                self._auto_launch_at = now + 45.0
                self.launch_peer(auto=True)

    # ------------------------------ 消息 ------------------------------
    def _handle_message(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "_status":
            self.changed.emit()
            return
        if kind == "state":
            if message.get("app") == APP_CI:
                state = message.get("state")
                if isinstance(state, dict):
                    self._peer_snapshot = state
                    self._peer_snapshot_at = time.time()
                    self.changed.emit()
            return
        if kind == "cmd":
            self._handle_command(message)
            return

    def _handle_command(self, message: dict) -> None:
        action = str(message.get("action") or "")
        request_id = message.get("id")
        ok = False
        error = ""
        try:
            if action == "launch_peer":
                ok = self.launch_peer()
                if not ok:
                    error = "找不到 ClassIsland 主程序路径"
            elif action == "quit":
                ok = True
                QTimer.singleShot(200, self._quit_self)
            elif action == "ping":
                ok = True
            else:
                error = f"未知指令：{action}"
        except Exception as exc:  # pragma: no cover - 防御
            error = str(exc)
            logger.exception("执行联动指令失败：{}", action)
        if request_id is not None:
            self.bridge.send({"type": "ack", "id": request_id, "ok": ok, "error": error})

    def _quit_self(self) -> None:
        try:
            self.api._app.quit()
        except Exception:
            logger.exception("退出 Class Widgets 2 失败")

    # ------------------------------ 对外指令 ------------------------------
    def launch_peer(self, auto: bool = False) -> bool:
        if self.bridge.status().get("connected"):
            return True
        path = self._resolve_ci_path()
        if not path:
            if not auto:
                logger.warning("未配置 ClassIsland 主程序路径")
            return False
        try:
            creation = 0
            if sys.platform == "win32":
                creation = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            subprocess.Popen([str(path)], cwd=str(path.parent), creationflags=creation)
            logger.info("已启动 ClassIsland：{}", path)
            return True
        except Exception:
            logger.exception("启动 ClassIsland 失败：{}", path)
            return False

    def quit_peer(self) -> None:
        if self.bridge.status().get("connected"):
            self.bridge.send({"type": "cmd", "id": now_ms(), "action": "quit"})

    def _resolve_ci_path(self) -> Path | None:
        settings = self.store.snapshot()
        candidates = [
            settings["process"].get("ci_path", "").strip(),
            os.environ.get("CIWITHCW2_CI_PATH", "").strip(),
            (self.bridge.status().get("peer_exe") or "").strip(),
        ]
        local = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates += [
            os.path.join(local, "Programs", "ClassIsland", "ClassIsland.exe") if local else "",
            os.path.join(program_files, "ClassIsland", "ClassIsland.exe"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate)
            if path.is_file():
                return path
        return None

    def _bar_height(self) -> int:
        try:
            root = self.api._app.widgets_window.root_window
            if not root:
                return 0
            from PySide6.QtCore import QObject
            loader = root.findChild(QObject, "widgetsLoader")
            if not loader:
                return 0
            # CI 的 WindowDockingOffsetY 是物理像素；Qt 高度是逻辑像素，需乘 DPR。
            return int(round(loader.height() * float(root.devicePixelRatio())))
        except Exception:
            return 0

    def _peer_height(self) -> int:
        try:
            return int(self._peer_snapshot.get("window_height", 0) or 0)
        except Exception:
            return 0

    def _current_anchor(self) -> str:
        try:
            return str(self.api.globalconfig.configs.data["preferences"]["widgets_anchor"])
        except Exception:
            return "top_center"

    def _apply_stack_layout(self) -> None:
        """预设 1/2：只调整垂直偏移；用户改动锚点/停靠位置后自动转为 3 自定义。"""
        settings = self.store.snapshot()
        layout = settings["layout"]
        mode = str(layout.get("mode") or "cw2_top")
        saved = self.local_state.get("stack_cw2_original")
        enabled = (
            bool(settings.get("enabled"))
            and mode in {"cw2_top", "ci_top"}
            and not bool(settings["cw2_layout"].get("apply"))
        )

        anchor = self._current_anchor()
        peer_dock = int((self._peer_snapshot or {}).get("docking", 1) or 1)

        if not enabled:
            if saved is not None:
                self._restore_stack_original(saved)
            return

        if not anchor.startswith("top_") or peer_dock > 2:
            # 用户自己改了位置：切成自定义，不再自动排列。
            self.store.set_value("layout.mode", "custom", source=APP_CW2)
            if saved is not None:
                self._restore_stack_original(saved)
            return

        if mode == "cw2_top":
            if saved is not None:
                self._restore_stack_original(saved)
            return

        gap = int(layout.get("gap", 12) or 0)
        target_offset = max(0, self._peer_height() + gap)
        try:
            configs = self.api.globalconfig.configs
        except Exception:
            return
        if saved is None:
            self.local_state["stack_cw2_original"] = {
                "offset_y": configs.data["preferences"]["widgets_offset_y"],
                "offset_x": configs.data["preferences"]["widgets_offset_x"],
            }
            self._save_local_state()
        if not configs.isKeyLocked("preferences.widgets_offset_y") and int(configs.data["preferences"]["widgets_offset_y"]) != target_offset:
            configs.set("preferences.widgets_offset_y", target_offset)
            configs.save(silent=True)

    def _current_offset(self) -> int:
        try:
            return int(self.api.globalconfig.configs.data["preferences"]["widgets_offset_y"])
        except Exception:
            return 0

    def _restore_stack_original(self, saved: dict) -> None:
        try:
            configs = self.api.globalconfig.configs
        except Exception:
            return
        changed = False
        for key, field in (("preferences.widgets_offset_y", "offset_y"), ("preferences.widgets_offset_x", "offset_x")):
            if configs.isKeyLocked(key) or saved.get(field) is None:
                continue
            if int(configs.data["preferences"].get(key.split(".")[-1], 0)) != int(saved.get(field, 0)):
                configs.set(key, int(saved.get(field, 0)))
                changed = True
        if changed:
            configs.save(silent=True)
        self.local_state.pop("stack_cw2_original", None)
        self._save_local_state()

    # ------------------------------ 设置应用 ------------------------------
    def _apply_settings(self, settings: dict, force: bool = False) -> None:
        network = settings["network"]
        status = self.bridge.status()
        if status.get("port") != int(network["port"]) or force:
            self.bridge.start(int(network["port"]), str(network["token"]))

        self._apply_cw2_layout(settings, force=force)
        self._apply_dedupe(settings)
        self.changed.emit()

    def _apply_cw2_layout(self, settings: dict, force: bool = False) -> None:
        layout = settings["cw2_layout"]
        if not layout.get("apply"):
            self._layout_signature = ""
            return
        signature = json.dumps(layout, sort_keys=True)
        if not force and signature == self._layout_signature:
            return
        try:
            configs = self.api.globalconfig.configs
            pairs = [
                ("preferences.widgets_anchor", layout["anchor"]),
                ("preferences.widgets_offset_x", int(layout["offset_x"])),
                ("preferences.widgets_offset_y", int(layout["offset_y"])),
                ("preferences.scale_factor", float(layout["scale_factor"])),
            ]
            changed = False
            for key, value in pairs:
                if configs.isKeyLocked(key):
                    continue
                current = configs.data
                for part in key.split("."):
                    current = current[part] if isinstance(current, dict) else None
                if current != value:
                    configs.set(key, value)
                    changed = True
            if changed:
                configs.save(silent=True)
                logger.info("已应用 CW2 小组件位置：{}", signature)
            self._layout_signature = signature
        except Exception:
            logger.exception("应用 CW2 小组件位置失败")

    def _apply_dedupe(self, settings: dict) -> None:
        role = settings["role"]
        dedupe = settings["dedupe"]
        active = (
            bool(settings.get("enabled"))
            and self.bridge.status().get("connected")
            and role != APP_CW2
            and bool(dedupe.get("enable"))
            and bool(dedupe.get("cw2_disable_notifications"))
        )
        saved = self.local_state.get("cw2_notifications_original")
        try:
            configs = self.api.globalconfig.configs
            if active:
                if saved is None and not configs.isKeyLocked("notifications.enabled"):
                    self.local_state["cw2_notifications_original"] = bool(configs.data["notifications"]["enabled"])
                    self._save_local_state()
                if configs.data["notifications"]["enabled"] and not configs.isKeyLocked("notifications.enabled"):
                    configs.set("notifications.enabled", False)
                    configs.save(silent=True)
                    logger.info("副程序模式：已暂停 CW2 自身通知（避免与 ClassIsland 重复提醒）")
            elif saved is not None:
                if not configs.isKeyLocked("notifications.enabled"):
                    configs.set("notifications.enabled", bool(saved))
                    configs.save(silent=True)
                    logger.info("恢复 CW2 自身通知开关：{}", saved)
                self.local_state.pop("cw2_notifications_original", None)
                self._save_local_state()
        except Exception:
            logger.exception("应用副程序精简设置失败")

    def _save_local_state(self) -> None:
        try:
            write_json_atomic(self.local_path, self.local_state)
        except Exception:
            logger.exception("写入 CW2 端本地状态失败")

    # ------------------------------ 快照 ------------------------------
    def _empty_snapshot(self) -> dict:
        return {
            "app": APP_CW2,
            "ts": now_ms(),
            "time": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "weekday": WEEKDAY_NAMES[datetime.now().weekday()],
            "week": 0,
            "status": "free",
            "status_text": "空闲",
            "current": None,
            "next": None,
            "today": [],
        }

    def _build_local_snapshot(self) -> dict:
        now = datetime.now()
        snapshot = self._empty_snapshot()
        snapshot.update(
            {
                "ts": now_ms(),
                "time": now.strftime("%H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "weekday": WEEKDAY_NAMES[now.weekday()],
                "bar_height": self._bar_height(),
                "anchor": self._current_anchor(),
                "cw2_hidden": False,
            }
        )
        try:
            snapshot["cw2_hidden"] = bool(self.api.globalconfig.configs.data["interactions"]["hide"]["state"])
        except Exception:
            pass
        try:
            runtime = self.api.runtime
            snapshot["week"] = int(getattr(runtime, "current_week", 0) or 0)
            status = str(getattr(runtime, "current_status", "free") or "free")
            snapshot["status"] = status
            snapshot["status_text"] = STATUS_LABELS.get(status, status)

            entries = runtime.current_day_entries or []
            today = []
            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                today.append(
                    {
                        "id": str(entry.get("id") or ""),
                        "index": index,
                        "title": str(entry.get("title") or entry.get("type") or ""),
                        "start": str(entry.get("startTime") or ""),
                        "end": str(entry.get("endTime") or ""),
                        "type": str(entry.get("type") or ""),
                    }
                )
            self._mark_today_states(today, now)
            snapshot["today"] = today

            current = runtime.current_entry or {}
            subject = runtime.current_subject or {}
            if current:
                title = str(current.get("title") or subject.get("name") or "")
                if subject.get("teacher") and not current.get("title"):
                    title = str(subject.get("name") or title)
                remaining = runtime.remaining_time or {}
                remaining_sec = int(remaining.get("minute", 0)) * 60 + int(remaining.get("second", 0))
                snapshot["current"] = {
                    "title": title,
                    "start": str(current.get("startTime") or ""),
                    "end": str(current.get("endTime") or ""),
                    "type": str(current.get("type") or ""),
                    "teacher": str(subject.get("teacher") or ""),
                    "remaining_sec": remaining_sec,
                    "remaining_text": _format_remaining(remaining_sec),
                    "progress": float(getattr(runtime, "progress", 0.0) or 0.0),
                    "index": self._index_of(today, current.get("id")),
                }

            next_entries = runtime.next_entries or []
            if next_entries and isinstance(next_entries[0], dict):
                first = next_entries[0]
                snapshot["next"] = {
                    "title": str(first.get("title") or ""),
                    "start": str(first.get("startTime") or ""),
                    "end": str(first.get("endTime") or ""),
                    "type": str(first.get("type") or ""),
                    "index": self._index_of(today, first.get("id")),
                }
        except Exception:
            logger.exception("读取 CW2 课程快照失败")
        return snapshot

    @staticmethod
    def _index_of(today: list[dict], entry_id: Any) -> int:
        if not entry_id:
            return 0
        for item in today:
            if item.get("id") == entry_id:
                return item.get("index", 0)
        return 0

    @staticmethod
    def _mark_today_states(today: list[dict], now: datetime) -> None:
        current_time = now.strftime("%H:%M")
        current_index = None
        for index, item in enumerate(today):
            start, end = item.get("start", ""), item.get("end", "")
            if start and end and start <= current_time < end:
                item["state"] = "current"
                current_index = index
            elif end and end <= current_time:
                item["state"] = "done"
            else:
                item["state"] = "future"
        if current_index is not None:
            for item in today[current_index + 1:]:
                if item.get("type") in {"class", "activity"}:
                    if item.get("state") == "future":
                        item["state"] = "next"
                        break

    # ------------------------------ 视图 ------------------------------
    def _active_snapshot(self, settings: dict) -> tuple[dict, str]:
        role = settings["role"]
        if role == APP_CW2:
            return self._snapshot, "local"
        if self._peer_snapshot and time.time() - self._peer_snapshot_at <= 8.0:
            return self._peer_snapshot, "peer"
        return self._snapshot, "local"

    def view(self) -> dict:
        settings = self.store.snapshot()
        status = self.bridge.status()
        role = settings["role"]
        is_main = role == APP_CW2
        snapshot, source = self._active_snapshot(settings)
        appearance = settings["appearance"]
        features = settings["features"]
        main_only = settings["dispatch_mode"] == "main_only"

        active = {}
        for feature in features:
            active[feature] = bool(settings.get("enabled") and features.get(feature)) and (is_main or not main_only)

        connected = bool(status.get("connected"))
        peer = APP_NAMES.get(status.get("peer") or APP_CI, "ClassIsland")
        peer_version = status.get("peer_version") or ""
        if connected:
            status_text = f"已连接 {peer}" + (f" {peer_version}" if peer_version else "")
        else:
            status_text = f"等待 {peer} 连接"

        current = snapshot.get("current") or None
        next_item = snapshot.get("next") or None
        is_class = snapshot.get("status") == "class"
        show_current = bool(current and is_class)
        lesson_header = "当前课程" if show_current else ("下一节课" if next_item else "当前课程")
        lesson = current if show_current else next_item
        lesson_title = (lesson or {}).get("title") or "暂无课程"
        lesson_time = ""
        if lesson:
            lesson_time = f"{(lesson.get('start') or '')[:5]} - {(lesson.get('end') or '')[:5]}"
        lesson_teacher = (lesson or {}).get("teacher") or ""
        if not show_current and next_item:
            lesson_teacher = ""

        return {
            "connected": connected,
            "statusText": status_text,
            "peer": peer,
            "peerVersion": peer_version,
            "peerExe": status.get("peer_exe") or "",
            "ciWindowVisible": bool(snapshot.get("window_visible")),
            "ciDocking": int(snapshot.get("docking", 1) or 1),
            "role": role,
            "roleLabel": f"主程序：{APP_NAMES.get(role, role)}",
            "isMain": is_main,
            "sideLabel": "主程序" if is_main else "副程序",
            "active": active,
            "showPlaceholder": bool(settings.get("show_placeholder")),
            "enabled": bool(settings.get("enabled")),
            "appearance": appearance,
            "source": source,
            "hasPeerData": bool(self._peer_snapshot and time.time() - self._peer_snapshot_at <= 8.0),
            "time": snapshot.get("time", ""),
            "clock": (snapshot.get("time") or "") if appearance.get("show_seconds") else (snapshot.get("time") or "")[:5],
            "date": snapshot.get("date", ""),
            "weekday": snapshot.get("weekday", ""),
            "week": snapshot.get("week", 0),
            "status": snapshot.get("status", "free"),
            "statusTextNow": snapshot.get("status_text", ""),
            "lessonHeader": lesson_header,
            "lessonTitle": lesson_title,
            "lessonTime": lesson_time,
            "lessonTeacher": lesson_teacher,
            "lessonRemainingText": (lesson or {}).get("remaining_text", "") if show_current else "",
            "lessonProgress": float((lesson or {}).get("progress", 0.0) or 0.0) if show_current else 0.0,
            "showProgress": bool(appearance.get("show_progress")) and show_current,
            "nextTitle": (next_item or {}).get("title", ""),
            "nextTime": (
                f"{(next_item.get('start') or '')[:5]} - {(next_item.get('end') or '')[:5]}" if next_item else ""
            ),
            "today": snapshot.get("today", []),
            "scheduleRows": int(appearance.get("schedule_rows", 6)),
            "compact": bool(appearance.get("compact")),
        }

    # ------------------------------ 指令入口（设置页调用） ------------------------------
    def set_setting(self, dotted: str, value: Any) -> bool:
        try:
            current = self.store.get(dotted)
            if isinstance(current, dict) and isinstance(value, dict):
                value = deep_merge(current, value)
            self.store.update(set_path({}, dotted, value), source=APP_CW2)
            self._apply_settings(self.store.snapshot())
            return True
        except Exception:
            logger.exception("写入共享设置失败：{}", dotted)
            return False

    def reset_settings(self) -> None:
        self.store.reset(source=APP_CW2)
        self._apply_settings(self.store.snapshot())

    def open_data_folder(self) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(data_dir()))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(data_dir())])
        except Exception:
            logger.exception("打开数据目录失败")
