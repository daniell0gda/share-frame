import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.daniell0gda.share-frame"

  readonly property string cli: String(Qt.resolvedUrl("share-frame")).replace(/^file:\/\//, "")
  readonly property string installer: String(Qt.resolvedUrl("install.sh")).replace(/^file:\/\//, "")

  property bool frameShown: false
  property string missingPackages: ""
  property bool portalUnregistered: false
  readonly property bool needsPackages: missingPackages !== ""
  readonly property bool needsPortal: !needsPackages && portalUnregistered

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!statusProcess.running) statusProcess.running = true
  }

  function runCommand(argument) {
    if (commandProcess.running) return
    commandProcess.command = [cli, argument]
    commandProcess.running = true
  }

  function installPackages() {
    if (root.bar) root.bar.run("omarchy-launch-floating-terminal-with-presentation omarchy-pkg-add " + missingPackages)
  }

  function registerPortal() {
    if (!registerProcess.running) registerProcess.running = true
  }

  function tooltip() {
    if (needsPackages) return "Share frame needs: " + missingPackages + " (click to install)"
    if (needsPortal) return "Click to add the share-frame picker to ~/.config/hypr/xdph.conf (a backup is kept)"
    return frameShown
      ? "Share frame shown. Click hides, right click picks a region, middle click edits."
      : "Share frame hidden. Click shows, right click picks a region, middle click edits."
  }

  Process {
    id: installProcess
    command: ["bash", root.installer, "--quiet"]
    running: true
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var match = text.match(/^MISSING: (.+)$/m)
        root.missingPackages = match ? match[1] : ""
        root.portalUnregistered = /^PORTAL: unregistered$/m.test(text)
      }
    }
  }

  Process {
    id: registerProcess
    command: ["bash", root.installer, "--register-portal"]
    onExited: installProcess.running = true
  }

  Process {
    id: watchProcess
    command: [root.cli, "watch"]
    running: true
  }

  Process {
    id: statusProcess
    command: [root.cli, "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.frameShown = text.indexOf(" shown") !== -1
    }
  }

  Process {
    id: commandProcess
    onExited: root.refresh()
  }

  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: ""
    active: root.frameShown && !root.needsPackages && !root.needsPortal
    tooltipText: root.tooltip()
    onPressed: function(b) {
      if (root.needsPackages) root.installPackages()
      else if (root.needsPortal) root.registerPortal()
      else if (b === Qt.RightButton) root.runCommand("pick")
      else if (b === Qt.MiddleButton) root.runCommand("edit")
      else root.runCommand("toggle")
    }
  }
}
