<div align="center">

<img src="icon.png" height="120" alt="CI × CW2 联动">

<h1>CI × CW2 联动（Class Widgets 2 端）</h1>

<p>让 ClassIsland 与 Class Widgets 2 以一个主程序、一个副程序的方式联动。</p>

[![版本](https://img.shields.io/badge/版本-1.0.0-blue?style=for-the-badge)](/releases)
[![星标](https://img.shields.io/github/stars/Kryon2025/CI-with-CW2-For-CW2?style=for-the-badge&label=%E6%98%9F%E6%A0%87)](https://github.com/Kryon2025/CI-with-CW2-For-CW2)
[![开源许可](https://img.shields.io/badge/开源许可-MIT-purple?style=for-the-badge)](LICENSE)

</div>

> [!NOTE]
> 当前版本 **1.0.0**，要求 Class Widgets 2 的插件 API `~=0.7.0`。
> 需要同时安装 [ClassIsland 端插件](https://github.com/Kryon2025/CI-with-CW2-For-CI)。

## 功能

- **一个主程序、一个副程序**：在任意一端的设置页选择主程序，另一端自动切换为副程序。课程数据以主程序为准，副程序通过本机 TCP 连接实时复用。
- **四种联动小组件**：当前课程 / 下一节课、全量课表、时钟日期、联动状态，按 CW2 现有小组件机制排布。
- **副程序精简**：副程序默认不再重复主程序的提醒（可关闭），切回主程序时自动恢复原来的通知开关。
- **展示方式 1 / 2 / 3**：1 = CW2 在上、CI 在下；2 = CI 在上、CW2 在下；3 = 自定义。选 1/2 时保持可调间距；一旦手动改动位置，自动变为 3 自定义，不再被挪动。CW2 隐藏或恢复时，ClassIsland 跟随同步。
- **通知分工**：只由主程序播放通知；副程序在联动期间暂停自身通知，断开或切回主程序后自动恢复。
- **两端设置实时同步**：CW2 与 ClassIsland 读写同一份 `link.json`，在任意一端修改后，另一端约 1 秒内自动应用。
- **统一显示位置**：可从这里统一设置 CW2 的小组件锚点、偏移、缩放，以及 ClassIsland 主窗口的停靠位置与不透明度。
- **进程联动**：可选让 CW2 启动时自动拉起 ClassIsland，也可以在设置页手动启动 / 关闭对端。

## 设置页

设置 → 插件 → **CI × CW2 联动**。页内所有修改立即写入共享设置并生效，不需要重启。

- **主程序**：ClassIsland / Class Widgets 2
- **副程序中的重复显示**：只有主程序显示 / 两端都显示；副程序可留一行「由主程序显示」的占位提示
- **启用的联动显示**：四种小组件分别开关
- **显示外观**：秒、紧凑、课表行数、进度条、教师、星期
- **显示位置**：CW2 小组件锚点 / 偏移 / 缩放；ClassIsland 主窗口停靠 / 偏移 / 不透明度 / 缩放
- **副程序精简**：通知与自动化的暂停策略
- **进程与连接**：自动启动对端、ClassIsland 路径、本地端口

## 显示位置是怎么工作的

CW2 的小组件共用一条横向排布，位置由 `preferences.widgets_anchor`（六种锚点）与偏移、缩放决定；本插件在设置里统一控制这些值，效果与「设置 → 通用 → 小组件 → 位置」一致，因此可以把联动小组件放在屏幕任意一角。

ClassIsland 端的组件位置由 ClassIsland 自己的组件编辑器决定；本插件额外提供主窗口停靠位置、偏移、不透明度与缩放的统一控制。

## 安装

1. 在 Class Widgets 2 的插件广场导入本插件，或把 `.cwplugin` 拖进「插件」页面。
2. 安装 ClassIsland 端插件（`.cipx`）。
3. 打开任意一端的设置页，选择主程序即可。

两端设置共用 `%LOCALAPPDATA%\CIWithCW2\link.json`；删除它即可恢复默认。

## 通信

- 只监听 `127.0.0.1`，默认端口 `39741`，用共享设置里的随机令牌握手。
- 一行一个 UTF-8 JSON；每秒推送一次课程快照，支持命令（启动 / 关闭对端）。
- 不依赖任何第三方库，插件自带实现。

## 构建

```bash
cw-plugin-pack
```

## 许可

MIT
