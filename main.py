"""CI × CW2 联动（Class Widgets 2 端）。

以 ClassIsland 或 Class Widgets 2 之一作为主程序：
- 主程序提供课程数据、负责提醒；
- 副程序复用主程序数据，自动暂停自身重复提醒（可在设置里关掉）；
- 两端共享同一份设置，任意一端都能修改全部可修改项；
- 提供「当前课程 / 全量课表 / 时钟 / 联动状态」四种小组件，位置跟随 CW2 的小组件锚点。
"""

from __future__ import annotations

from pathlib import Path

from ClassWidgets.SDK import CW2Plugin, PluginAPI
from loguru import logger

from ciwc_backend import LinkBackend
from ciwc_service import LinkService

VERSION = "1.0.0"
WIDGET_PREFIX = "com.kryon.ciwithcw2"


class Plugin(CW2Plugin):
    def __init__(self, api: PluginAPI) -> None:
        super().__init__(api)
        self.service: LinkService | None = None
        self.backend: LinkBackend | None = None
        self.provider = None

    def on_load(self) -> None:
        super().on_load()
        base = Path(__file__).resolve().parent
        qml = base / "qml"

        self.service = LinkService(self.api, base, VERSION)
        self.backend = LinkBackend(self.service)

        widgets = [
            ("lesson", "CI × CW2 · 当前课程", "LessonWidget.qml"),
            ("schedule", "CI × CW2 · 全量课表", "ScheduleWidget.qml"),
            ("clock", "CI × CW2 · 时钟日期", "ClockWidget.qml"),
            ("link", "CI × CW2 · 联动状态", "LinkWidget.qml"),
        ]
        for key, name, filename in widgets:
            self.api.widgets.register(
                widget_id=f"{WIDGET_PREFIX}.{key}",
                name=name,
                qml_path=qml / filename,
                backend_obj=self.backend,
                default_settings={},
            )

        self.api.ui.register_settings_page(
            qml / "settings.qml",
            title="CI × CW2 联动",
            icon="ic_fluent_link_20_regular",
        )

        try:
            self.provider = self.api.notification.register_provider(
                WIDGET_PREFIX,
                "CI × CW2 联动",
                icon=base / "icon.png",
                use_system_notify=False,
            )
        except Exception:
            logger.exception("注册联动通知提供者失败")

        self.service.start()
        logger.info("CI × CW2 联动（CW2 端）加载完成")

    def on_unload(self) -> None:
        if self.service:
            self.service.stop()
        logger.info("CI × CW2 联动（CW2 端）已卸载")
