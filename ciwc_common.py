"""CI × CW2 联动 —— 两端共享的常量与文件工具。

主程序 / 副程序的设置放在同一个 JSON 文件里（%LOCALAPPDATA%\\CIWithCW2\\link.json），
ClassIsland 端与 Class Widgets 2 端都读写它，因此任意一端修改设置，
另一端都会立刻看到 —— 这就是"主程序副程序可以互相修改所有可修改的设置"。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

APP_CW2 = "cw2"
APP_CI = "ci"

APP_NAMES = {
    APP_CW2: "Class Widgets 2",
    APP_CI: "ClassIsland",
}

APP_SHORT_NAMES = {
    APP_CW2: "CW2",
    APP_CI: "CI",
}

CW2_ANCHORS = [
    "top_left",
    "top_center",
    "top_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
]

CW2_ANCHOR_LABELS = {
    "top_left": "左上",
    "top_center": "顶部居中",
    "top_right": "右上",
    "bottom_left": "左下",
    "bottom_center": "底部居中",
    "bottom_right": "右下",
}

# ClassIsland 的 WindowDockingLocation：0-2 顶部左/中/右，3-5 底部左/中/右。
CI_DOCKING_LABELS = {
    0: "左上",
    1: "顶部居中",
    2: "右上",
    3: "左下",
    4: "底部居中",
    5: "右下",
}

FEATURE_IDS = ["lesson", "schedule", "clock", "link"]


def data_dir() -> Path:
    """共享数据目录。可用环境变量 CIWITHCW2_DATA_DIR 覆盖（测试/便携场景）。"""
    override = os.environ.get("CIWITHCW2_DATA_DIR", "").strip()
    if override:
        path = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        path = Path(local) / "CIWithCW2" if local else Path.home() / ".ciwithcw2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return data_dir() / "link.json"


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default
    except Exception:
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    """原子写入：先写同目录临时文件，再 os.replace，避免读到半个 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except OSError:
            pass


def file_fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def now_ms() -> int:
    return int(time.time() * 1000)


def as_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return fallback


def as_int(value: Any, fallback: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        result = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def as_float(value: Any, fallback: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def clamp_text(value: Any, maximum: int = 512) -> str:
    if value is None:
        return ""
    text = str(value)
    return text[:maximum]


def deep_merge(base: dict, patch: dict) -> dict:
    """把 patch 合并进 base 的拷贝（dict 递归合并，其它类型直接覆盖）。"""
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_path(data: dict, dotted: str, default: Any = None) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set_path(data: dict, dotted: str, value: Any) -> dict:
    """返回带修改的新 dict（不就地改）。"""
    parts = [part for part in dotted.split(".") if part]
    if not parts:
        return data
    root = dict(data)
    node = root
    for part in parts[:-1]:
        child = node.get(part)
        child = dict(child) if isinstance(child, dict) else {}
        node[part] = child
        node = child
    node[parts[-1]] = value
    return root
