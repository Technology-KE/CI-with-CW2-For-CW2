"""CI × CW2 联动 —— QML 后端。

组件与设置页都通过这一个 QObject 读取状态、写入共享设置。
视图数据整体放在一个 QVariantMap 里（Property + 单一 notify），
QML 里直接写 backend.state.lessonTitle 即可，新增字段不用改后端签名。
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot


class LinkBackend(QObject):
    stateChanged = Signal()
    settingsReloaded = Signal()

    def __init__(self, service, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._state: dict = {}
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        service.changed.connect(self._refresh)
        service.settingsReloaded.connect(self.settingsReloaded.emit)
        self._refresh()

    # ------------------------------ 属性 ------------------------------
    def _get_state(self) -> dict:
        return self._state

    state = Property("QVariantMap", _get_state, notify=stateChanged)

    def _refresh(self) -> None:
        try:
            state = self._service.view()
        except Exception:
            logger.exception("刷新联动视图失败")
            return
        if state != self._state:
            self._state = state
            self.stateChanged.emit()

    # ------------------------------ 设置 ------------------------------
    @Slot(result="QVariantMap")
    def getSettings(self) -> dict:
        return self._service.store.snapshot()

    @Slot(str, "QVariant", result=bool)
    def setSetting(self, path: str, value) -> bool:
        return self._service.set_setting(path, value)

    @Slot(str, bool, result=bool)
    def setFeature(self, feature: str, enabled: bool) -> bool:
        return self._service.set_setting(f"features.{feature}", bool(enabled))

    @Slot(result=bool)
    def resetSettings(self) -> bool:
        try:
            self._service.reset_settings()
            return True
        except Exception:
            logger.exception("恢复默认设置失败")
            return False

    # ------------------------------ 操作 ------------------------------
    @Slot(result=bool)
    def launchPeer(self) -> bool:
        return self._service.launch_peer()

    @Slot()
    def quitPeer(self) -> None:
        self._service.quit_peer()

    @Slot()
    def openDataFolder(self) -> None:
        self._service.open_data_folder()

    @Slot(result=str)
    def statusSummary(self) -> str:
        return str(self._state.get("statusText", ""))

    @Slot(result="QVariantList")
    def lessonRows(self) -> list:
        return list(self._state.get("today") or [])

    @Slot(result=str)
    def pluginVersion(self) -> str:
        return str(getattr(self._service, "version", ""))
