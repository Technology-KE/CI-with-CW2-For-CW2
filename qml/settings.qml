import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import RinUI
import ClassWidgets.Plugins

/*!
    CI × CW2 联动设置页（CW2 端）。

    所有设置与 ClassIsland 端共用同一个文件（%LOCALAPPDATA%\CIWithCW2\link.json），
    因此在这里改 = 在 ClassIsland 的设置页里改；另一端会立刻收到并应用。
*/
PluginPage {
    id: page
    pluginId: "com.kryon.ciwithcw2"
    title: "CI × CW2 联动"

    property var settings: ({})
    property bool ready: false
    property string statusText: "正在读取……"
    property string savedHint: ""
    property bool connected: false

    readonly property var roleOptions: ["ci", "cw2"]
    readonly property var roleLabels: ["ClassIsland 主程序", "Class Widgets 2 主程序"]
    readonly property var anchorOptions: ["top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right"]
    readonly property var anchorLabels: ["左上", "顶部居中", "右上", "左下", "底部居中", "右下"]
    readonly property var dockLabels: ["左上", "顶部居中", "右上", "左下", "底部居中", "右下"]

    function loadSettings() {
        if (!backend) return
        settings = backend.getSettings()
        ready = true
        refreshStatus()
    }

    function refreshStatus() {
        if (!backend) return
        statusText = backend.statusSummary()
        connected = backend.state ? backend.state.connected === true : false
    }

    function save(path, value) {
        if (!backend) return
        if (backend.setSetting(path, value)) {
            settings = backend.getSettings()
            savedHint = "已同步到 ClassIsland 端"
            savedTimer.restart()
        }
    }

    function selectMode(mode) {
        if (!backend) return
        if (mode !== "custom")
            page.save("cw2_layout", { anchor: "top_center" })
        page.save("layout", { mode: mode })
    }

    function saveFeature(feature, value) {
        if (!backend) return
        page.save("features." + feature, value)
    }

    function adjust(path, field, delta, lo, hi) {
        var current = Number(settings[path] ? settings[path][field] : 0)
        var next = Math.max(lo, Math.min(hi, current + delta))
        var patch = {}
        patch[field] = next
        save(path, patch)
    }

    function valueOf(path, field, fallback) {
        var group = settings[path]
        if (!group || group[field] === undefined) return fallback
        return group[field]
    }

    Component.onCompleted: loadSettings()

    Connections {
        target: backend
        function onSettingsReloaded() { page.loadSettings() }
        function onStateChanged() { page.refreshStatus() }
    }

    Timer {
        id: savedTimer
        interval: 2500
        repeat: false
        onTriggered: page.savedHint = ""
    }

    FileDialog {
        id: ciPathDialog
        title: "选择 ClassIsland 主程序（ClassIsland.exe）"
        nameFilters: ["ClassIsland 主程序 (ClassIsland.exe)", "可执行文件 (*.exe)", "所有文件 (*)"]
        onAccepted: page.savePath("process.ci_path", ciPathDialog.selectedFile)
    }

    function savePath(path, value) {
        if (!backend) return
        var parts = path.split(".")
        var patch = {}
        patch[parts[1]] = value
        page.save(parts[0], patch)
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        // ── 状态 ─────────────────────────────────────────────
        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_plug_connected_20_regular"
            title: "联动状态"
            description: page.statusText

            RowLayout {
                spacing: 8
                Button {
                    text: page.connected ? "已连接，无需启动" : "启动 ClassIsland"
                    enabled: !page.connected
                    onClicked: if (backend) backend.launchPeer()
                }
                Button {
                    text: "关闭对端"
                    onClicked: if (backend) backend.quitPeer()
                }
                Button {
                    text: "打开共享设置目录"
                    onClicked: if (backend) backend.openDataFolder()
                }
            }
        }

        Text { text: "主程序与分工"; font.bold: true; opacity: 0.75 }
        Text {
            Layout.fillWidth: true
            typography: Typography.Caption
            opacity: 0.6
            wrapMode: Text.WordWrap
            text: "两个程序共用同一份课程数据，只让其中一个「主程序」负责提醒与显示。"
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_apps_20_regular"
            title: "主程序"
            description: "决定课程数据以哪一方为准。切换后两端都会自动更新。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    spacing: 8
                    Repeater {
                        model: page.roleLabels
                        Button {
                            text: modelData
                            highlighted: page.settings.role === page.roleOptions[index]
                            onClicked: page.save("role", page.roleOptions[index])
                        }
                    }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_split_horizontal_20_regular"
            title: "副程序中的重复显示"
            description: "默认只有主程序渲染这些组件；选「两端都显示」可以同时用两边的小组件位置摆多份。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8
                RowLayout {
                    spacing: 8
                    Button {
                        text: "只有主程序显示"
                        highlighted: page.settings.dispatch_mode === "main_only"
                        onClicked: page.save("dispatch_mode", "main_only")
                    }
                    Button {
                        text: "两端都显示"
                        highlighted: page.settings.dispatch_mode === "both"
                        onClicked: page.save("dispatch_mode", "both")
                    }
                }
                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.settings.show_placeholder === true
                        onClicked: page.save("show_placeholder", checked)
                    }
                    Text { typography: Typography.Body; text: "副程序不显示组件时，留一个「由主程序显示」的提示" }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_puzzle_piece_20_regular"
            title: "启用的联动显示"
            description: "这些显示在 CW2 里是小组件，在 ClassIsland 里是对应的组件。"

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 24
                rowSpacing: 6

                Repeater {
                    model: [
                        { key: "lesson", label: "当前课程 / 下一节课" },
                        { key: "schedule", label: "全量课表" },
                        { key: "clock", label: "时钟日期" },
                        { key: "link", label: "联动状态" }
                    ]
                    delegate: RowLayout {
                        spacing: 8
                        Switch {
                            checked: page.settings.features && page.settings.features[modelData.key] !== false
                            onClicked: page.saveFeature(modelData.key, checked)
                        }
                        Text { typography: Typography.Body; text: modelData.label }
                    }
                }
            }
        }

        Text { text: "显示外观"; font.bold: true; opacity: 0.75 }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_text_effects_20_regular"
            title: "外观选项"
            description: "两端的课程 / 课表 / 时钟共用这些选项。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("appearance", "show_seconds", true)
                        onClicked: page.save("appearance", { show_seconds: checked })
                    }
                    Text { typography: Typography.Body; text: "时钟显示秒" }

                    Item { Layout.preferredWidth: 16 }
                    Switch {
                        checked: page.valueOf("appearance", "compact", false)
                        onClicked: page.save("appearance", { compact: checked })
                    }
                    Text { typography: Typography.Body; text: "紧凑模式" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("appearance", "show_progress", true)
                        onClicked: page.save("appearance", { show_progress: checked })
                    }
                    Text { typography: Typography.Body; text: "当前课程显示进度条" }

                    Item { Layout.preferredWidth: 16 }
                    Switch {
                        checked: page.valueOf("appearance", "show_teacher", true)
                        onClicked: page.save("appearance", { show_teacher: checked })
                    }
                    Text { typography: Typography.Body; text: "显示教师" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("appearance", "show_weekday", true)
                        onClicked: page.save("appearance", { show_weekday: checked })
                    }
                    Text { typography: Typography.Body; text: "显示星期" }

                    Item { Layout.preferredWidth: 16 }
                    Text { typography: Typography.Body; text: "课表显示行数" }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("appearance", "schedule_rows", -1, 1, 12) }
                    Text { typography: Typography.Body; text: String(page.valueOf("appearance", "schedule_rows", 6)) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("appearance", "schedule_rows", 1, 1, 12) }
                }
            }
        }

        Text { text: "显示位置"; font.bold: true; opacity: 0.75 }
        Text {
            Layout.fillWidth: true
            typography: Typography.Caption
            opacity: 0.6
            wrapMode: Text.WordWrap
            text: "CW2 的小组件共用一条横向排列，位置由下面的「小组件位置」决定；ClassIsland 的主窗口同样可以在这里统一摆放。"
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_position_to_back_20_regular"
            title: "Class Widgets 2 小组件位置"
            description: "打开后会把下面的位置写进 CW2 的偏好设置（与「设置 → 通用 → 小组件」一致）。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("cw2_layout", "apply", false)
                        onClicked: page.save("cw2_layout", { apply: checked })
                    }
                    Text { typography: Typography.Body; text: "由联动统一控制" }

                }

                Text {
                    typography: Typography.Body
                    text: "展示方式"
                }

                RowLayout {
                    spacing: 12

                    Repeater {
                        model: [
                            { mode: "cw2_top", label: "1  CW2 在上 / CI 在下" },
                            { mode: "ci_top", label: "2  CI 在上 / CW2 在下" },
                            { mode: "custom", label: "3  自定义" }
                        ]

                        delegate: ColumnLayout {
                            spacing: 4
                            readonly property bool selected: page.valueOf("layout", "mode", "cw2_top") === modelData.mode

                            Rectangle {
                                width: 168
                                height: 68
                                radius: 8
                                color: Theme.currentTheme.colors.controlColor
                                border.width: selected ? 2 : 1
                                border.color: selected
                                              ? Theme.currentTheme.colors.primaryColor
                                              : Theme.currentTheme.colors.controlBorderColor

                                // 预览：两条窗口示意
                                Rectangle {
                                    x: 10; y: 8; height: 18; radius: 6
                                    color: modelData.mode === "ci_top"
                                           ? Theme.currentTheme.colors.textSecondaryColor
                                           : Theme.currentTheme.colors.primaryColor
                                    opacity: modelData.mode === "custom" ? 0.85 : 0.9
                                    width: modelData.mode === "custom" ? 66 : 148
                                }
                                Rectangle {
                                    x: modelData.mode === "custom" ? 70 : 10
                                    y: modelData.mode === "custom" ? 34 : 34
                                    width: modelData.mode === "custom" ? 78 : 148
                                    height: 18; radius: 6
                                    color: modelData.mode === "ci_top"
                                           ? Theme.currentTheme.colors.primaryColor
                                           : Theme.currentTheme.colors.textSecondaryColor
                                    opacity: 0.6
                                }

                                TapHandler {
                                    onTapped: page.selectMode(modelData.mode)
                                }
                            }

                            RowLayout {
                                spacing: 6
                                Rectangle {
                                    width: 14; height: 14; radius: 7
                                    color: "transparent"
                                    border.width: 2
                                    border.color: selected
                                                  ? Theme.currentTheme.colors.primaryColor
                                                  : Theme.currentTheme.colors.controlBorderColor
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: selected ? 7 : 0
                                        height: selected ? 7 : 0
                                        radius: 3.5
                                        color: Theme.currentTheme.colors.primaryColor
                                    }
                                }
                                Text { typography: Typography.Caption; text: modelData.label }
                            }
                        }
                    }
                }

                RowLayout {
                    spacing: 8
                    Text {
                        typography: Typography.Caption
                        opacity: 0.65
                        text: "间距 " + page.valueOf("layout", "gap", 12) + " px（仅 1 / 2 生效）"
                    }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("layout", "gap", -4, 0, 200) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("layout", "gap", 4, 0, 200) }
                }

                RowLayout {
                    spacing: 8
                    Text { typography: Typography.Body; text: "对齐" }
                    ComboBox {
                        Layout.preferredWidth: 150
                        model: page.anchorLabels
                        currentIndex: Math.max(0, page.anchorOptions.indexOf(page.valueOf("cw2_layout", "anchor", "top_center")))
                        onActivated: page.save("cw2_layout", { anchor: page.anchorOptions[currentIndex] })
                    }
                    Text {
                        typography: Typography.Caption
                        opacity: 0.6
                        text: "水平偏移 " + page.valueOf("cw2_layout", "offset_x", 0)
                    }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "offset_x", -8, -2000, 2000) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "offset_x", 8, -2000, 2000) }
                    Text {
                        typography: Typography.Caption
                        opacity: 0.6
                        text: "垂直偏移 " + page.valueOf("cw2_layout", "offset_y", 24)
                    }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "offset_y", -8, -2000, 2000) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "offset_y", 8, -2000, 2000) }
                }

                RowLayout {
                    spacing: 8
                    Text { typography: Typography.Body; text: "缩放 " + Number(page.valueOf("cw2_layout", "scale_factor", 1)).toFixed(2) + "×" }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "scale_factor", -0.05, 0.5, 2.0) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("cw2_layout", "scale_factor", 0.05, 0.5, 2.0) }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_desktop_20_regular"
            title: "ClassIsland 主窗口位置"
            description: "由 ClassIsland 端应用：停靠位置、偏移、不透明度与缩放。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("ci_layout", "apply", false)
                        onClicked: page.save("ci_layout", { apply: checked })
                    }
                    Text { typography: Typography.Body; text: "由联动统一控制" }
                }

                RowLayout {
                    spacing: 8
                    Text { typography: Typography.Body; text: "停靠" }
                    ComboBox {
                        Layout.preferredWidth: 130
                        model: page.dockLabels
                        currentIndex: Math.max(0, Math.min(5, Number(page.valueOf("ci_layout", "docking", 1))))
                        onActivated: page.save("ci_layout", { docking: currentIndex })
                    }
                    Text {
                        typography: Typography.Caption
                        opacity: 0.6
                        text: "偏移 " + page.valueOf("ci_layout", "offset_x", 0) + ", " + page.valueOf("ci_layout", "offset_y", 0)
                    }
                    Button { text: "X−"; implicitWidth: 34; implicitHeight: 28; onClicked: page.adjust("ci_layout", "offset_x", -8, -4000, 4000) }
                    Button { text: "X+"; implicitWidth: 34; implicitHeight: 28; onClicked: page.adjust("ci_layout", "offset_x", 8, -4000, 4000) }
                    Button { text: "Y−"; implicitWidth: 34; implicitHeight: 28; onClicked: page.adjust("ci_layout", "offset_y", -8, -4000, 4000) }
                    Button { text: "Y+"; implicitWidth: 34; implicitHeight: 28; onClicked: page.adjust("ci_layout", "offset_y", 8, -4000, 4000) }
                }

                RowLayout {
                    spacing: 8
                    Text {
                        typography: Typography.Body
                        text: "不透明度 " + Number(page.valueOf("ci_layout", "opacity", 0.5)).toFixed(2)
                    }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("ci_layout", "opacity", -0.05, 0.05, 1.0) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("ci_layout", "opacity", 0.05, 0.05, 1.0) }
                    Text {
                        typography: Typography.Body
                        text: "缩放 " + Number(page.valueOf("ci_layout", "scale", 1)).toFixed(2) + "×"
                    }
                    Button { text: "−"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("ci_layout", "scale", -0.05, 0.3, 3.0) }
                    Button { text: "+"; implicitWidth: 30; implicitHeight: 28; onClicked: page.adjust("ci_layout", "scale", 0.05, 0.3, 3.0) }
                }
            }
        }

        Text { text: "副程序精简"; font.bold: true; opacity: 0.75 }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_battery_saver_20_regular"
            title: "副程序暂停重复功能"
            description: "副程序不再重复主程序的提醒，减少后台开销；切回主程序时会自动恢复原来的开关。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "enable", true)
                        onClicked: page.save("dedupe", { enable: checked })
                    }
                    Text { typography: Typography.Body; text: "启用副程序精简" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "cw2_disable_notifications", true)
                        onClicked: page.save("dedupe", { cw2_disable_notifications: checked })
                    }
                    Text { typography: Typography.Body; text: "CW2 是副程序时暂停自身通知" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "ci_disable_notifications", true)
                        onClicked: page.save("dedupe", { ci_disable_notifications: checked })
                    }
                    Text { typography: Typography.Body; text: "ClassIsland 是副程序时暂停通知" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "ci_disable_automation", false)
                        onClicked: page.save("dedupe", { ci_disable_automation: checked })
                    }
                    Text { typography: Typography.Body; text: "ClassIsland 是副程序时暂停自动化" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "ci_hide_main_window", false)
                        onClicked: page.save("dedupe", { ci_hide_main_window: checked })
                    }
                    Text { typography: Typography.Body; text: "ClassIsland 是副程序时隐藏其主界面（避免与 CW2 重叠）" }
                }

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("dedupe", "ci_follow_cw2_visibility", true)
                        onClicked: page.save("dedupe", { ci_follow_cw2_visibility: checked })
                    }
                    Text { typography: Typography.Body; text: "CW2 隐藏 / 恢复时，ClassIsland 主界面一起隐藏 / 恢复" }
                }
            }
        }

        Text { text: "进程与连接"; font.bold: true; opacity: 0.75 }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_rocket_20_regular"
            title: "启动 ClassIsland"
            description: "CW2 启动时如果 ClassIsland 没在运行，可以自动把它拉起来。"

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                RowLayout {
                    spacing: 8
                    Switch {
                        checked: page.valueOf("process", "auto_launch_peer", false)
                        onClicked: page.save("process", { auto_launch_peer: checked })
                    }
                    Text { typography: Typography.Body; text: "CW2 启动后自动启动 ClassIsland" }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text { typography: Typography.Body; text: "ClassIsland.exe" }
                    TextField {
                        Layout.fillWidth: true
                        text: page.valueOf("process", "ci_path", "")
                        placeholderText: "留空则自动查找常见安装位置"
                        onEditingFinished: page.save("process", { ci_path: text })
                    }
                    Button {
                        text: "浏览…"
                        onClicked: ciPathDialog.open()
                    }
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_wifi_20_regular"
            title: "本地连接"
            description: "只监听 127.0.0.1；端口与令牌由两端共享。修改端口后两端都会自动重连。"

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text { typography: Typography.Body; text: "端口" }
                TextField {
                    Layout.preferredWidth: 120
                    text: String(page.valueOf("network", "port", 39741))
                    onEditingFinished: {
                        var value = parseInt(text, 10)
                        if (!isNaN(value) && value >= 1024 && value <= 65535)
                            page.save("network", { port: value })
                        else
                            text = String(page.valueOf("network", "port", 39741))
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.primaryColor
                    text: page.savedHint
                }
            }
        }

        SettingCard {
            Layout.fillWidth: true
            icon.name: "ic_fluent_arrow_reset_20_regular"
            title: "恢复默认"
            description: "只重置联动设置，不会影响两端的课程表与主题。"

            Button {
                text: "恢复默认设置"
                onClicked: {
                    if (!backend) return
                    backend.resetSettings()
                    page.loadSettings()
                }
            }
        }
    }
}
