"""Offscreen Qt tests. Run through dbus-run-session for the inhibition test."""

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QObject, QTimer, pyqtClassInfo, pyqtProperty
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingReply, QDBusVariant
    from PyQt6.QtWidgets import QApplication
except ImportError:
    raise unittest.SkipTest("PyQt6 required") from None

from desk_rhythm import Window
from desktop import DEFAULT_PREFERENCES
from notifications import Notifications, OBJECT, SERVICE
from reminder_core import DEFAULTS
from settings_dialog import SettingsDialog


class FakePlasmaNotifications(QObject):
    pyqtClassInfo("D-Bus Interface", SERVICE)
    muted = False

    @pyqtProperty(bool)
    def Inhibited(self):
        return self.muted


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])

    def test_dashboard_countdown_settings_and_suspend_gap(self):
        with patch("desk_rhythm.read_configuration",
                   return_value=(DEFAULTS, DEFAULT_PREFERENCES.copy())):
            window = Window(self.app)
        window.show()
        settings = SettingsDialog(window)
        self.assertEqual(settings.intervals["sit_minutes"].value(), 30)
        self.assertEqual(window.phase_name.text(), "Sitting")
        window.toggle_pause()
        self.assertFalse(window.timer.isActive())
        window.snooze()
        self.assertGreater(window.engine.position_remaining, 2399)
        window.switch_position()
        self.assertEqual(window.phase_time.text(), "15:00")
        window.toggle_pause()
        window.hide()
        self.assertGreater(window.timer.interval(), 60_000)
        remaining = window.engine.position_remaining
        window.last_tick -= window.scheduled_delay + 121
        window.refresh()
        self.assertEqual(window.engine.position_remaining, remaining)
        window.timer.stop()
        window.tray.hide()

    def test_chime_policy_accepts_only_explicit_false(self):
        alert = Notifications()
        request = QDBusMessage.createMethodCall(
            SERVICE, OBJECT, "org.freedesktop.DBus.Properties", "Get")
        replies = (
            request.createReply(QDBusVariant(False)),
            request.createReply(QDBusVariant(True)),
            request.createErrorReply("org.freedesktop.DBus.Error.UnknownProperty", "Missing"),
        )
        with patch.object(alert, "play") as play:
            for message in replies:
                with patch("notifications.QDBusPendingReply", return_value=QDBusPendingReply(message)):
                    alert.after_inhibition_check(Mock())
            play.assert_called_once()

    def test_automatic_chime_only_when_dbus_reports_dnd_off(self):
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected() or not bus.registerService(SERVICE):
            self.skipTest("Requires a private D-Bus session (dbus-run-session)")
        fake = FakePlasmaNotifications()
        self.assertTrue(bus.registerObject(
            OBJECT, fake, QDBusConnection.RegisterOption.ExportScriptableProperties))
        self.addCleanup(bus.unregisterService, SERVICE)
        self.addCleanup(bus.unregisterObject, OBJECT)
        alert = Notifications()
        preferences = {**DEFAULT_PREFERENCES, "visual": False}

        def send_and_wait():
            self.assertTrue(alert.send("Test", "Body", preferences))
            watcher = alert.check
            self.assertIsNotNone(watcher)
            watcher.finished.connect(self.app.quit)
            QTimer.singleShot(1200, self.app.quit)
            self.app.exec()
            self.assertIsNone(alert.check)

        with patch("notifications.audio_player", return_value="/fake/paplay"), \
                patch.object(alert, "play") as play:
            fake.muted = False
            send_and_wait()
            play.assert_called_once()
            fake.muted = True
            send_and_wait()
            play.assert_called_once()
            bus.unregisterObject(OBJECT)
            send_and_wait()
            play.assert_called_once()
