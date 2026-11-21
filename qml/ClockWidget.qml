import QtQuick
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme 1.0 as CW

/*!
    CI × CW2 · 时钟日期
    与主程序同一时钟（副程序跟随主程序快照），可切换显示秒。
*/
CW.Widget {
    id: root

    readonly property var s: backend && backend.state ? backend.state : ({})
    readonly property bool featureOn: !!(s.active && s.active.clock) && s.enabled !== false
    readonly property bool placeholder: !featureOn && s.showPlaceholder === true

    visible: featureOn || placeholder
    height: miniMode ? 56 : 100
    text: featureOn ? "时间" : "CI × CW2"

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 0
        visible: root.featureOn

        Text {
            Layout.alignment: Qt.AlignHCenter
            font.pixelSize: 34
            font.weight: Font.DemiBold
            font.family: Utils.fontFamily
            color: Theme.currentTheme.colors.textColor
            text: root.s.clock || ""
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8

            Text {
                typography: Typography.Caption
                opacity: 0.66
                text: root.s.date || ""
            }
            Text {
                visible: root.s.appearance && root.s.appearance.show_weekday === true
                typography: Typography.Caption
                opacity: 0.66
                text: root.s.weekday || ""
            }
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
