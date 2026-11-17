"""Nonblocking desktop reminders and one-shot audio playback."""

import logging
import shutil
import time

from PyQt6.QtCore import QObject, QProcess, QTimer
from PyQt6.QtDBus import (
    QDBusConnection, QDBusMessage, QDBusPendingCallWatcher, QDBusPendingReply,
    QDBusVariant,
)
from PyQt6.QtWidgets import QMessageBox

from desktop import APP_ID, APP_NAME, RESOURCES, audio_player, in_quiet_hours

SERVICE = "org.freedesktop.Notifications"
OBJECT = "/org/freedesktop/Notifications"
LOG = logging.getLogger(__name__)


class Notifications(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.visual = self.make_process("Desktop notification")
        self.audio = self.make_process("Chime playback")
        self.check = None
        self.last_chime = float("-inf")

    def make_process(self, label):
        process = QProcess(self)
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        deadline = QTimer(process)
        deadline.setSingleShot(True)
        deadline.timeout.connect(process.kill)
        process.started.connect(lambda: deadline.start(5000))
        process.finished.connect(deadline.stop)
        process.finished.connect(
            lambda code, status: LOG.warning("%s exited with code %s", label, code) if code else None)
        process.errorOccurred.connect(
            lambda error: LOG.warning("%s: %s", label, process.errorString()))
        return process

    def send(self, title, body, preferences):
        now = time.localtime()
        if in_quiet_hours(preferences, now.tm_hour * 60 + now.tm_min):
            return False
        notifier = shutil.which("notify-send")
        show = preferences["visual"] and notifier is not None
        sound = preferences["audio"] and audio_player() is not None
        if show and self.visual.state() == QProcess.ProcessState.NotRunning:
            self.visual.start(notifier, [
                f"--app-name={APP_NAME}", "--urgency=normal", "--expire-time=9000",
                f"--icon={RESOURCES / 'desk-rhythm.svg'}",
                f"--hint=string:desktop-entry:{APP_ID}", "--hint=boolean:suppress-sound:true",
                "--", title, body,
            ])
        if sound and self.check is None:
            # Plasma 6.3 publishes its effective Do Not Disturb state here.
            # Skip automatic playback if the server cannot confirm it is off.
            request = QDBusMessage.createMethodCall(
                SERVICE, OBJECT, "org.freedesktop.DBus.Properties", "Get")
            request.setArguments([SERVICE, "Inhibited"])
            connection = QDBusConnection.sessionBus()
            self.check = QDBusPendingCallWatcher(connection.asyncCall(request, 750), self)
            self.check.finished.connect(self.after_inhibition_check)
        return show or sound

    def after_inhibition_check(self, watcher):
        reply = QDBusPendingReply(watcher)
        self.check = None
        watcher.deleteLater()
        if reply.isError():
            LOG.info("Automatic audio skipped: notification inhibition status unavailable")
            return
        value = reply.value()
        if isinstance(value, QDBusVariant):
            value = value.variant()
        if value is False:
            self.play()

    def play(self):
        player = audio_player()
        now = time.monotonic()
        if (player and self.audio.state() == QProcess.ProcessState.NotRunning
                and now - self.last_chime >= 1.2):
            self.last_chime = now
            self.audio.start(player, [
                f"--client-name={APP_NAME}", "--stream-name=Desk Rhythm chime",
                "--property=media.role=event", str(RESOURCES / "chime.wav"),
            ])
            return True
        return False

    def preview(self, parent):
        # This is an explicit playback action. KDE can still mute event audio.
        if not self.play() and not audio_player():
            QMessageBox.information(parent, APP_NAME, "Install pulseaudio-utils to preview the chime.")
