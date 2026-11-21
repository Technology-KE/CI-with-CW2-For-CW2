"""共享设置模型与读写。

设置文件由 CI 端与 CW2 端共同维护：
- 任意一端修改后 revision + 1，写入 updated_at / updated_by；
- 另一端轮询文件指纹（mtime + size），发现变化就整体重载并通知界面；
- 写入使用 临时文件 + os.replace，避免读到半截 JSON。
"""

from __future__ import annotations

import copy
import secrets
import threading
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from ciwc_common import (
    APP_CW2,
    CW2_ANCHORS,
    FEATURE_IDS,
    as_bool,
    as_float,
    as_int,
    clamp_text,
    deep_merge,
    file_fingerprint,
    now_ms,
    read_json,
    set_path,
    settings_path,
    write_json_atomic,
)

SCHEMA_VERSION = 1


def default_settings() -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "revision": 0,
        "updated_at": now_ms(),
        "updated_by": "",
        # 主程序："ci" 或 "cw2"（默认让 Class Widgets 2 保持现状为主程序）
        "role": "cw2",
        "enabled": True,
        # main_only：只有主程序渲染（副程序的重复功能不占用资源）
        # both：两端都渲染
        "dispatch_mode": "main_only",
        "features": {feature: True for feature in FEATURE_IDS},
        "show_placeholder": False,
        "appearance": {
            "show_seconds": True,
            "compact": False,
            "schedule_rows": 6,
            "show_progress": True,
            "show_teacher": True,
            "show_weekday": True,
        },
        "cw2_layout": {
            "apply": False,
            "anchor": "top_center",
            "offset_x": 0,
            "offset_y": 24,
            "scale_factor": 1.0,
        },
        "ci_layout": {
            "apply": False,
            "docking": 1,
            "offset_x": 0,
            "offset_y": 0,
            "opacity": 0.5,
            "scale": 1.0,
        },
        "dedupe": {
            "enable": True,
            "ci_disable_notifications": True,
            "ci_disable_automation": False,
            "cw2_disable_notifications": True,
        },
        "process": {
            "auto_launch_peer": False,
            "cw2_path": "",
            "ci_path": "",
        },
        "network": {
            "port": 39741,
            "token": secrets.token_hex(8),
            "heartbeat_sec": 3,
        },
    }


def normalize_settings(raw: Any) -> dict:
    """把任意来源的 dict 收敛成完整、类型正确的设置。"""
    defaults = default_settings()
    if not isinstance(raw, dict):
        return defaults

    data = deep_merge(defaults, raw)

    data["schema"] = SCHEMA_VERSION
    data["revision"] = as_int(data.get("revision"), 0, 0)
    data["updated_at"] = as_int(data.get("updated_at"), now_ms(), 0)
    data["updated_by"] = clamp_text(data.get("updated_by"), 16)

    role = str(data.get("role") or "cw2").strip().lower()
    data["role"] = role if role in {"ci", "cw2"} else "cw2"
    data["enabled"] = as_bool(data.get("enabled"), True)

    mode = str(data.get("dispatch_mode") or "main_only").strip().lower()
    data["dispatch_mode"] = mode if mode in {"main_only", "both"} else "main_only"
    data["show_placeholder"] = as_bool(data.get("show_placeholder"), False)

    raw_features = data.get("features")
    raw_features = raw_features if isinstance(raw_features, dict) else {}
    data["features"] = {feature: as_bool(raw_features.get(feature), True) for feature in FEATURE_IDS}

    appearance = data.get("appearance") if isinstance(data.get("appearance"), dict) else {}
    data["appearance"] = {
        "show_seconds": as_bool(appearance.get("show_seconds"), True),
        "compact": as_bool(appearance.get("compact"), False),
        "schedule_rows": as_int(appearance.get("schedule_rows"), 6, 1, 12),
        "show_progress": as_bool(appearance.get("show_progress"), True),
        "show_teacher": as_bool(appearance.get("show_teacher"), True),
        "show_weekday": as_bool(appearance.get("show_weekday"), True),
    }

    layout = data.get("cw2_layout") if isinstance(data.get("cw2_layout"), dict) else {}
    anchor = str(layout.get("anchor") or "top_center").strip().lower()
    data["cw2_layout"] = {
        "apply": as_bool(layout.get("apply"), False),
        "anchor": anchor if anchor in CW2_ANCHORS else "top_center",
        "offset_x": as_int(layout.get("offset_x"), 0, -2000, 2000),
        "offset_y": as_int(layout.get("offset_y"), 24, -2000, 2000),
        "scale_factor": round(as_float(layout.get("scale_factor"), 1.0, 0.5, 2.0), 2),
    }

    ci_layout = data.get("ci_layout") if isinstance(data.get("ci_layout"), dict) else {}
    data["ci_layout"] = {
        "apply": as_bool(ci_layout.get("apply"), False),
        "docking": as_int(ci_layout.get("docking"), 1, 0, 5),
        "offset_x": as_int(ci_layout.get("offset_x"), 0, -4000, 4000),
        "offset_y": as_int(ci_layout.get("offset_y"), 0, -4000, 4000),
        "opacity": round(as_float(ci_layout.get("opacity"), 0.5, 0.05, 1.0), 2),
        "scale": round(as_float(ci_layout.get("scale"), 1.0, 0.3, 3.0), 2),
    }

    dedupe = data.get("dedupe") if isinstance(data.get("dedupe"), dict) else {}
    data["dedupe"] = {
        "enable": as_bool(dedupe.get("enable"), True),
        "ci_disable_notifications": as_bool(dedupe.get("ci_disable_notifications"), True),
        "ci_disable_automation": as_bool(dedupe.get("ci_disable_automation"), False),
        "cw2_disable_notifications": as_bool(dedupe.get("cw2_disable_notifications"), True),
    }

    process = data.get("process") if isinstance(data.get("process"), dict) else {}
    data["process"] = {
        "auto_launch_peer": as_bool(process.get("auto_launch_peer"), False),
        "cw2_path": clamp_text(process.get("cw2_path"), 1024),
        "ci_path": clamp_text(process.get("ci_path"), 1024),
    }

    network = data.get("network") if isinstance(data.get("network"), dict) else {}
    token = clamp_text(network.get("token"), 64).strip()
    data["network"] = {
        "port": as_int(network.get("port"), 39741, 1024, 65535),
        "token": token or secrets.token_hex(8),
        "heartbeat_sec": as_int(network.get("heartbeat_sec"), 3, 1, 30),
    }
    return data


class SettingsStore:
    """线程安全的共享设置容器，带文件变化检测。"""

    def __init__(self, path: Path | None = None, source: str = APP_CW2) -> None:
        self.path = path or settings_path()
        self.source = source
        self._lock = threading.RLock()
        self._listeners: list[Callable[[dict], None]] = []
        self._fingerprint: tuple[int, int] | None = None
        self._data: dict = default_settings()
        self._load_or_create()

    # ------------------------------ 读 ------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.snapshot()
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    # ------------------------------ 写 ------------------------------
    def update(self, changes: dict, source: str | None = None) -> dict:
        """合并 changes 并立即原子落盘。"""
        with self._lock:
            current = copy.deepcopy(self._data)
            merged = normalize_settings(deep_merge(current, changes or {}))
            merged["revision"] = int(current.get("revision", 0)) + 1
            merged["updated_at"] = now_ms()
            merged["updated_by"] = source or self.source
            write_json_atomic(self.path, merged)
            self._data = merged
            self._fingerprint = file_fingerprint(self.path)
            listeners = list(self._listeners)
        _notify(listeners, merged)
        return merged

    def set_value(self, dotted: str, value: Any, source: str | None = None) -> dict:
        return self.update(set_path({}, dotted, value), source=source)

    def reset(self, source: str | None = None) -> dict:
        fresh = default_settings()
        fresh["network"]["token"] = self.get("network.token") or fresh["network"]["token"]
        with self._lock:
            current = self._data
            fresh["revision"] = int(current.get("revision", 0)) + 1
            fresh["updated_at"] = now_ms()
            fresh["updated_by"] = source or self.source
            write_json_atomic(self.path, fresh)
            self._data = fresh
            self._fingerprint = file_fingerprint(self.path)
            listeners = list(self._listeners)
        _notify(listeners, fresh)
        return fresh

    # --------------------------- 文件监听 ---------------------------
    def reload_if_changed(self) -> bool:
        fingerprint = file_fingerprint(self.path)
        with self._lock:
            if fingerprint is None or fingerprint == self._fingerprint:
                return False
            raw = read_json(self.path, None)
            if not isinstance(raw, dict):
                return False
            normalized = normalize_settings(raw)
            if normalized == self._data:
                self._fingerprint = fingerprint
                return False
            self._data = normalized
            self._fingerprint = fingerprint
            listeners = list(self._listeners)
        logger.debug("共享设置已被另一端修改：revision={} by={}", normalized.get("revision"), normalized.get("updated_by"))
        _notify(listeners, normalized)
        return True

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._listeners.append(callback)

    # ------------------------------ 内部 ------------------------------
    def _load_or_create(self) -> None:
        raw = read_json(self.path, None)
        if not isinstance(raw, dict):
            data = default_settings()
            write_json_atomic(self.path, data)
            self._data = data
            self._fingerprint = file_fingerprint(self.path)
            logger.info("已创建共享设置文件：{}", self.path)
            return

        data = normalize_settings(raw)
        if data != raw:
            write_json_atomic(self.path, data)
        self._data = data
        self._fingerprint = file_fingerprint(self.path)
        logger.info("已加载共享设置：{}（revision={}）", self.path, data.get("revision"))


def _notify(listeners: list[Callable[[dict], None]], data: dict) -> None:
    for listener in listeners:
        try:
            listener(data)
        except Exception:
            logger.exception("共享设置监听器执行失败")
