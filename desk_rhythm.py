#!/usr/bin/env python3
"""Desk Rhythm for KDE Plasma on Wayland."""

from __future__ import annotations

import os
import sys
import time

from PyQt6.QtCore import QLockFile, QPointF, Qt, QTimer
from PyQt6.QtGui import QAction, QFontDatabase, QIcon, QKeySequence, QPainter, QPalette, QPen
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QProgressBar, QPushButton, QStackedWidget, QSystemTrayIcon,
    QToolButton, QVBoxLayout, QWidget,
)

from break_overlay import BreakOverlay
from desktop import (
    APP_ID, APP_NAME, APP_VERSION, RESOURCES, autostart_enabled, read_configuration,
    in_quiet_hours, runtime_socket, save_configuration, set_autostart,
)
from notifications import Notifications
from reminder_core import ReminderEngine, countdown
from settings_dialog import SettingsDialog

ICON = RESOURCES / "desk-rhythm.svg"


def label(text, scale=1.0, bold=False, fixed=False):
    widget = QLabel(text)
    font = (QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            if fixed else widget.font())
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    elif font.pixelSize() > 0:
        font.setPixelSize(round(font.pixelSize() * scale))
    font.setBold(bold)
    widget.setFont(font)
    return widget


class CompletionButton(QToolButton):
    """Draw a circled check over a native, keyboard-focusable tool button."""

    def __init__(self, action):
        super().__init__()
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(action)
        self.setToolTip(action)
        button_size = max(32, self.fontMetrics().height() + 14)
        self.setFixedSize(button_size, button_size)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        scale = (self.width() - 14) / 18
        painter.scale(scale, scale)
        pen = QPen(self.palette().color(QPalette.ColorRole.ButtonText), 1.35)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(0, 0), 8, 8)
        painter.drawLine(QPointF(-3.5, 0), QPointF(-1, 2.5))
        painter.drawLine(QPointF(-1, 2.5), QPointF(3.8, -2.7))


class ReminderStatus(QStackedWidget):
    """Keep space for both states, so an expiring reminder does not move either row."""

    def __init__(self, name):
        super().__init__()
        self.remaining = label("240:00", fixed=True)
        self.remaining.setMinimumWidth(self.remaining.sizeHint().width())
        self.remaining.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.remaining.setAccessibleName(f"{name} time remaining")
        self.due = label("Due", bold=True, fixed=True)
        self.due.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.due.setAccessibleName(f"{name} reminder due")
        self.due.setStyleSheet(
            "QLabel { background-color: palette(highlight); "
            "color: palette(highlighted-text); border-radius: 7px; padding: 2px 7px; }"
        )
        self.addWidget(self.remaining)
        self.addWidget(self.due)

    def set_status(self, due, seconds):
        self.remaining.setText(countdown(seconds))
        self.setCurrentWidget(self.due if due else self.remaining)


class Window(QMainWindow):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        intervals, self.preferences = read_configuration()
        self.engine = ReminderEngine(intervals)
        self.engine.paused = self.preferences["start_paused"]
        self.phase_span = self.engine.duration_for_phase()
        self.last_tick = time.monotonic()
        self.scheduled_delay = 0.0
        self.settings_dialog = None
        self.break_overlay = None
        self.preview_overlay = None
        self.break_warned = False
        self.setWindowTitle(APP_NAME)
        self.tray = QSystemTrayIcon(QIcon(str(ICON)), self)
        self.notifications = Notifications(self)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.refresh)
        self.make_ui()
        self.make_tray()
        self.refresh()

    def make_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.setSpacing(15)

        header = QHBoxLayout()
        header.addWidget(label("Current posture"))
        header.addStretch()
        settings = QToolButton()
        settings.setText("Settings")
        settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        settings.setIcon(QIcon.fromTheme("configure"))
        settings.clicked.connect(self.open_settings)
        header.addWidget(settings)
        layout.addLayout(header)
        settings_shortcut = QAction("Settings", self)
        settings_shortcut.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_shortcut.triggered.connect(self.open_settings)
        self.addAction(settings_shortcut)
        quit_shortcut = QAction("Quit", self)
        quit_shortcut.setShortcut(QKeySequence.StandardKey.Quit)
        quit_shortcut.triggered.connect(self.quit_app)
        self.addAction(quit_shortcut)

        posture = QVBoxLayout()
        posture.setSpacing(5)
        self.phase_name = label("", 1.45, bold=True)
        self.phase_time = label("", 3.25, bold=True, fixed=True)
        self.phase_time.setAccessibleName("Posture time remaining")
        self.next_label = label("")
        for item in (self.phase_name, self.phase_time, self.next_label):
            posture.addWidget(item, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(posture)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName("Posture interval elapsed")
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        actions = QHBoxLayout()
        self.pause_button = QPushButton("&Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        actions.addWidget(self.pause_button)
        for name, action in (("&Switch now", self.switch_position), ("S&nooze 10 min", self.snooze)):
            button = QPushButton(name)
            button.clicked.connect(action)
            actions.addWidget(button)
        layout.addLayout(actions)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(rule)
        reminders = QGridLayout()
        reminders.setHorizontalSpacing(16)
        reminders.setVerticalSpacing(8)
        reminders.setColumnStretch(0, 1)
        self.water_time, _ = self.add_reminder(reminders, 0, "Water", "Mark water as complete", self.ack_water)
        self.break_time, self.break_button = self.add_reminder(reminders, 1, "Screen break", "Mark screen break as complete", self.ack_break)
        layout.addLayout(reminders)
        layout.addStretch()
        self.adjustSize()
        self.resize(max(420, self.sizeHint().width()), self.sizeHint().height())

    def add_reminder(self, grid, row, name, action, slot):
        grid.addWidget(label(name, bold=True), row, 0)
        status = ReminderStatus(name)
        grid.addWidget(status, row, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        button = CompletionButton(action)
        button.clicked.connect(slot)
        grid.addWidget(button, row, 2)
        return status, button

    def make_tray(self):
        self.menu = QMenu(self)
        self.menu.addAction("Open Desk Rhythm", self.open_window)
        self.menu.addSeparator()
        self.pause_action = self.menu.addAction("Pause reminders", self.toggle_pause)
        self.resume_action = self.menu.addAction("Resume reminders", self.toggle_pause)
        self.menu.addAction("Switch now", self.switch_position)
        self.menu.addAction("Snooze 10 minutes", self.snooze)
        self.menu.addSeparator()
        self.menu.addAction("I drank water", self.ack_water)
        self.break_taken_action = self.menu.addAction("Screen break taken", self.ack_break)
        self.break_start_action = self.menu.addAction("Start Break Time", self.start_break)
        self.break_snooze_action = self.menu.addAction("Snooze Break Time 10 min", self.snooze_break)
        self.break_end_action = self.menu.addAction("End Break Time early", self.end_break)
        self.menu.addSeparator()
        self.menu.addAction("Settings", self.open_settings)
        self.menu.addAction("Quit Desk Rhythm", self.quit_app)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def advance(self):
        now = time.monotonic()
        elapsed = now - self.last_tick
        self.last_tick = now
        # Linux monotonic time excludes suspend. Also discard unusually late
        # wakes from an application stall, while allowing planned long waits.
        if elapsed > self.scheduled_delay + 120:
            return
        engine = self.engine
        events = engine.advance(elapsed)
        if self.preferences["break_overlay"] and not engine.paused and not engine.break_due:
            if engine.break_remaining <= 60 and not self.break_warned:
                self.break_warned = True
                self.notifications.warn_break(self.preferences, self.snooze_break)
        if not events:
            return
        messages = []
        for event in events:
            if event == "position":
                self.phase_span = engine.duration_for_phase()
                messages.append(("Time to stand or move", "Stand or take a short walk.")
                                if engine.phase == "standing"
                                else ("Time to sit", "Return to your seated position."))
            elif event == "water":
                messages.append(("Time to sip water", "Mark it done when you are ready."))
            elif self.preferences["break_overlay"] and self.break_warned and not self.quiet_now():
                self.start_break()
            else:
                messages.append(("Take a screen break", "Look away from the screen or step away for a moment."))
        if not messages:
            return
        title, body = (messages[0] if len(messages) == 1 else
                       ("Time for a break", "\n".join(item[0] for item in messages)))
        self.notifications.send(title, body, self.preferences)

    def refresh(self):
        self.advance()
        engine = self.engine
        self.phase_name.setText(engine.phase.capitalize())
        self.phase_time.setText(countdown(engine.position_remaining))
        next_phase = "Sit" if engine.phase == "standing" else "Stand or move"
        self.next_label.setText("All reminders paused" if engine.paused else f"Next: {next_phase}")
        status_font = self.next_label.font()
        if status_font.bold() != engine.paused:
            status_font.setBold(engine.paused)
            self.next_label.setFont(status_font)
        self.progress.setEnabled(not engine.paused)
        self.progress.setValue(round(1000 * (1 - engine.position_remaining / self.phase_span)))
        self.water_time.set_status(engine.water_due, engine.water_remaining)
        running_break = self.break_overlay is not None
        overlay_mode = self.preferences["break_overlay"]
        self.break_time.set_status(engine.break_due, engine.break_remaining)
        can_complete = self.can_acknowledge_break()
        self.break_button.setEnabled(can_complete)
        self.break_taken_action.setVisible(can_complete)
        self.break_start_action.setVisible(overlay_mode)
        self.break_start_action.setEnabled(engine.break_due and not running_break and not engine.paused)
        self.break_snooze_action.setVisible(overlay_mode)
        self.break_snooze_action.setEnabled(not running_break and not engine.paused
                                           and (engine.break_due or engine.break_remaining <= 60))
        self.break_end_action.setVisible(running_break or self.preview_overlay is not None)
        self.pause_button.setText("&Resume" if engine.paused else "&Pause")
        self.pause_action.setEnabled(not engine.paused)
        self.resume_action.setEnabled(engine.paused)
        status = " · Paused" if engine.paused else ""
        self.tray.setToolTip(f"{APP_NAME} · {engine.phase.capitalize()}{status}")
        self.timer.stop()
        self.scheduled_delay = 0.0
        if not engine.paused:
            remaining = [engine.position_remaining]
            if not engine.water_due:
                remaining.append(engine.water_remaining)
            if not engine.break_due:
                remaining.append(engine.break_remaining)
                if overlay_mode and not self.break_warned and engine.break_remaining > 60:
                    remaining.append(engine.break_remaining - 60)
            visible = self.isVisible() and not self.isMinimized()
            self.scheduled_delay = min([1.0, *remaining] if visible else remaining)
            # QTimer takes a signed 32-bit millisecond interval.
            self.timer.start(max(1, min(2147483647, round(1000 * self.scheduled_delay))))

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.refresh()

    def toggle_pause(self):
        self.advance()
        if self.engine.toggle_pause():
            self.clear_break_warning()
            self.end_break()
        self.refresh()

    def switch_position(self):
        self.advance()
        self.engine.switch_position()
        self.phase_span = self.engine.duration_for_phase()
        self.refresh()

    def snooze(self):
        self.advance()
        self.engine.snooze_position(10)
        self.phase_span += 600
        self.refresh()

    def ack_water(self):
        self.advance()
        self.engine.acknowledge_water()
        self.refresh()

    def can_acknowledge_break(self):
        return self.break_overlay is None and (
            not self.preferences["break_overlay"] or self.engine.break_due
        )

    def ack_break(self):
        self.advance()
        if self.can_acknowledge_break():
            self.clear_break_warning()
            self.engine.acknowledge_break()
        self.refresh()

    def quiet_now(self):
        local = time.localtime()
        return in_quiet_hours(self.preferences, local.tm_hour * 60 + local.tm_min)

    def clear_break_warning(self):
        self.break_warned = False
        self.notifications.clear_break_warning()

    def snooze_break(self):
        if (self.preferences["break_overlay"] and not self.engine.paused
                and self.break_overlay is None):
            self.engine.snooze_break()
            self.last_tick = time.monotonic()
            self.clear_break_warning()
            self.refresh()

    def start_break(self):
        if (not self.preferences["break_overlay"] or self.break_overlay is not None
                or not self.engine.break_due or self.engine.paused):
            return
        self.clear_break_warning()
        if self.preview_overlay is not None:
            self.preview_overlay.dismiss()
        self.break_overlay = BreakOverlay(
            self.app, self.preferences["break_duration"] * 60,
            self.preferences["overlay_strength"], self.break_finished,
        )
        self.break_overlay.start()

    def break_finished(self, completed):
        self.break_overlay = None
        if completed:
            self.engine.acknowledge_break()
        self.refresh()

    def preview_break(self, strength):
        if self.break_overlay is not None or self.preview_overlay is not None:
            return
        self.preview_overlay = BreakOverlay(self.app, 5, strength, self.preview_finished)
        self.preview_overlay.start()
        self.refresh()

    def preview_finished(self, completed):
        self.preview_overlay = None
        self.refresh()

    def end_break(self):
        if self.break_overlay is not None:
            self.break_overlay.dismiss()
        if self.preview_overlay is not None:
            self.preview_overlay.dismiss()

    def apply_settings(self, intervals, preferences, login):
        if preferences["quiet_enabled"] and preferences["quiet_start"] == preferences["quiet_end"]:
            raise ValueError("Choose different start and end times for quiet hours.")
        previous_login = autostart_enabled()
        if login != previous_login:
            set_autostart(login)
        try:
            save_configuration(intervals, preferences)
        except (OSError, ValueError):
            if login != previous_login:
                set_autostart(previous_login)
            raise
        self.advance()
        if intervals != self.engine.settings or preferences["break_overlay"] != self.preferences["break_overlay"]:
            self.clear_break_warning()
            self.end_break()
            self.engine.update_settings(intervals)
            self.phase_span = self.engine.duration_for_phase()
        self.preferences = preferences
        self.refresh()

    def open_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.activateWindow()
            return
        self.open_window()
        dialog = SettingsDialog(self)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.settings_dialog = dialog
        try:
            dialog.exec()
        finally:
            self.settings_dialog = None
            dialog.deleteLater()

    def open_window(self):
        if self.settings_dialog is not None:
            self.settings_dialog.activateWindow()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_window()

    def quit_app(self):
        self.clear_break_warning()
        self.end_break()
        self.tray.hide()
        self.app.quit()

    def closeEvent(self, event):
        if self.preferences["close_to_tray"] and self.tray.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(ICON)))
    app.setQuitOnLastWindowClosed(False)

    background = "--background" in sys.argv
    end_break = "--end-break" in sys.argv
    endpoint = runtime_socket()
    endpoint.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(endpoint) + ".lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock():
        if background:
            return 0
        client = QLocalSocket()
        client.connectToServer(str(endpoint))
        if client.waitForConnected(750):
            client.write(b"end-break\n" if end_break else b"open\n")
            return 0 if client.waitForBytesWritten(750) else 1
        print("Desk Rhythm is starting or its instance cannot be reached.", file=sys.stderr)
        return 1

    if end_break:
        lock.unlock()
        return 0

    server = QLocalServer(app)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    QLocalServer.removeServer(str(endpoint))
    if not server.listen(str(endpoint)):
        print(f"Desk Rhythm could not enable launcher reactivation: {server.errorString()}",
              file=sys.stderr)

    window = Window(app)

    def handle_message(peer):
        if not peer.canReadLine():
            return
        message = bytes(peer.readLine(32))
        if message == b"end-break\n":
            window.end_break()
        elif message == b"open\n":
            window.open_window()
        peer.disconnectFromServer()

    def receive_connection():
        while server.hasPendingConnections():
            peer = server.nextPendingConnection()
            peer.readyRead.connect(lambda peer=peer: handle_message(peer))
            peer.disconnected.connect(peer.deleteLater)
            handle_message(peer)

    server.newConnection.connect(receive_connection)
    if not background or not window.tray.isSystemTrayAvailable():
        window.show()
    try:
        return app.exec()
    finally:
        server.close()
        lock.unlock()


if __name__ == "__main__":
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    raise SystemExit(main())
