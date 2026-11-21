import QtQuick
import QtQuick.Layouts
import RinUI
import ClassWidgets.Theme 1.0 as CW

/*!
    CI × CW2 · 当前课程 / 下一节课
    数据来自「主程序」（ClassIsland 或 Class Widgets 2）：主程序提供快照，
    副程序复用同一份数据，避免两边显示不同课程。
*/
CW.Widget {
    id: root

    readonly property var s: backend && backend.state ? backend.state : ({})
    readonly property bool featureOn: !!(s.active && s.active.lesson) && s.enabled !== false
    readonly property bool placeholder: !featureOn && s.showPlaceholder === true
    readonly property bool isClass: s.status === "class"

    visible: featureOn || placeholder
    height: miniMode ? 56 : 100
    text: featureOn ? (s.lessonHeader || "当前课程") : "CI × CW2"

    ColumnLayout {
        anchors.fill: parent
        spacing: 4
        visible: root.featureOn

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.fillWidth: true
                typography: Typography.Title
                text: root.s.lessonTitle || "暂无课程"
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Text {
                visible: root.s.showProgress === true
                typography: Typography.Caption
                color: Theme.currentTheme.colors.primaryColor
                text: root.s.lessonRemainingText || ""
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                typography: Typography.Body
                opacity: 0.72
                text: root.s.lessonTime || ""
            }

            Text {
                visible: root.s.lessonTeacher !== "" && root.s.lessonTeacher !== undefined
                typography: Typography.Body
                opacity: 0.55
                text: root.s.lessonTeacher ? "· " + root.s.lessonTeacher : ""
            }

            Item { Layout.fillWidth: true }

            Text {
                typography: Typography.Caption
                opacity: 0.55
                text: root.isClass ? (root.s.statusTextNow || "") : (root.s.nextTitle ? "下一节 " + root.s.nextTitle : "")
            }
        }

        CW.ProgressBar {
            Layout.fillWidth: true
            Layout.preferredHeight: 4
            visible: root.s.showProgress === true
            value: Number(root.s.lessonProgress || 0)
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
