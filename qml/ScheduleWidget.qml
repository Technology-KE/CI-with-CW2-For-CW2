import QtQuick
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme 1.0 as CW

/*!
    CI × CW2 · 全量课表
    一次展示主程序今天的完整课程安排（含课间），当前课程高亮。
    行数由共享设置 appearance.schedule_rows 控制。
*/
CW.Widget {
    id: root

    readonly property var s: backend && backend.state ? backend.state : ({})
    readonly property bool featureOn: !!(s.active && s.active.schedule) && s.enabled !== false
    readonly property bool placeholder: !featureOn && s.showPlaceholder === true
    readonly property var rows: {
        var list = (s.today || []).slice(0, Math.max(1, Number(s.scheduleRows || 6)))
        return list
    }

    visible: featureOn || placeholder
    height: miniMode ? 56
            : Math.max(120, Math.min(300, 74 + rows.length * 22))
    text: featureOn ? "今日课表" : "CI × CW2"

    ColumnLayout {
        anchors.fill: parent
        spacing: 1
        visible: root.featureOn

        Repeater {
            model: root.rows

            delegate: RowLayout {
                Layout.fillWidth: true
                spacing: 8

                property string state: modelData.state || "future"

                Text {
                    Layout.preferredWidth: 78
                    typography: Typography.Caption
                    opacity: state === "done" ? 0.4 : 0.65
                    text: (modelData.start || "").slice(0, 5) + " - " + (modelData.end || "").slice(0, 5)
                }

                Text {
                    Layout.fillWidth: true
                    typography: state === "current" ? Typography.BodyStrong : Typography.Body
                    color: state === "current"
                           ? Theme.currentTheme.colors.primaryColor
                           : (state === "done"
                              ? Theme.currentTheme.colors.textSecondaryColor
                              : Theme.currentTheme.colors.textColor)
                    opacity: state === "done" ? 0.45 : 1
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    text: modelData.title || ""
                }

                Text {
                    visible: state === "current"
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.primaryColor
                    text: "进行中"
                }
            }
        }

        Text {
            visible: root.rows.length === 0
            typography: Typography.Body
            opacity: 0.5
            text: "今天没有课程"
        }
    }

    Text {
        anchors.centerIn: parent
        visible: root.placeholder
        typography: Typography.Body
        opacity: 0.5
        text: "由" + (root.s.roleLabel || "主程序") + "显示"
    }
}
