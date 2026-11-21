import QtQuick
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme 1.0 as CW

/*!
    CI × CW2 · 联动状态
    显示当前谁是主程序、对端是否已连接；不是主程序时说明重复功能已暂停。
*/
CW.Widget {
    id: root

    readonly property var s: backend && backend.state ? backend.state : ({})
    readonly property bool featureOn: !!(s.active && s.active.link) && s.enabled !== false
    readonly property bool placeholder: !featureOn && s.showPlaceholder === true
    readonly property bool connected: s.connected === true

    visible: featureOn || placeholder
    height: miniMode ? 56 : 100
    text: featureOn ? "CI × CW2 联动" : "CI × CW2"

    RowLayout {
        anchors.fill: parent
        spacing: 10
        visible: root.featureOn

        Rectangle {
            width: 10
            height: 10
            radius: 5
            color: root.connected
                   ? Theme.currentTheme.colors.systemSuccessColor
                   : Theme.currentTheme.colors.systemCautionColor
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            Text {
                Layout.fillWidth: true
                typography: Typography.BodyStrong
                elide: Text.ElideRight
                maximumLineCount: 1
                text: root.s.statusText || "等待连接"
            }

            Text {
                Layout.fillWidth: true
                typography: Typography.Caption
                opacity: 0.6
                elide: Text.ElideRight
                maximumLineCount: 1
                text: (root.s.roleLabel || "") + " · " + (root.s.sideLabel || "")
            }
        }

        Text {
            typography: Typography.Caption
            color: Theme.currentTheme.colors.primaryColor
            text: root.s.sideLabel || ""
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
