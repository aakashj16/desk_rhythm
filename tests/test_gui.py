"""Offscreen Qt tests. Run through dbus-run-session for the inhibition test."""

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QObject, Qt, QTimer, pyqtClassInfo, pyqtProperty
    from PyQt6.QtTest import QTest
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

    def test_break_time_warn_snooze_escape_and_completion(self):
        preferences = {**DEFAULT_PREFERENCES, "break_overlay": True, "break_duration": 10}
        with patch("desk_rhythm.read_configuration", return_value=(DEFAULTS, preferences)):
            window = Window(self.app)
        self.addCleanup(lambda: (window.end_break(), window.timer.stop(), window.tray.hide()))

        def advance(seconds):
            window.last_tick -= seconds
            window.scheduled_delay = seconds
            window.refresh()

        with patch.object(window.notifications, "warn_break") as warning:
            window.engine.break_remaining = 61
            advance(2)
            self.assertEqual(warning.call_count, 1)
            warning.call_args.args[1]()
            self.assertGreater(window.engine.break_remaining, 599)
            advance(539)
            self.assertEqual(warning.call_count, 1)
            advance(2)
            self.assertEqual(warning.call_count, 2)
            advance(60)

        overlay = window.break_overlay
        self.assertIsNotNone(overlay)
        self.assertTrue(window.engine.break_due)
        self.assertFalse(window.break_button.isEnabled())
        surface = next(iter(overlay.surfaces.values()))
        self.assertEqual(surface.timer_label.text(), "10:00")
        QTest.keyClick(surface, Qt.Key.Key_Escape)
        self.assertIsNone(window.break_overlay)
        self.assertTrue(window.engine.break_due)
        window.start_break()
        overlay = window.break_overlay
        overlay.deadline = overlay.now()
        overlay.update()
        self.assertIsNone(window.break_overlay)
        self.assertFalse(window.engine.break_due)
        self.assertGreater(window.engine.break_remaining, 3599)

        window.engine.break_remaining = 61
        with patch.object(window.notifications, "warn_break"):
            advance(2)
            advance(60)
        surface = next(iter(window.break_overlay.surfaces.values()))
        window.ack_break()
        self.assertIsNotNone(window.break_overlay)
        self.assertTrue(window.engine.break_due)
        QTest.keyClick(surface, Qt.Key.Key_Escape)
        self.assertTrue(window.break_button.isEnabled())
        self.assertTrue(window.break_taken_action.isVisible())
        window.break_button.click()
        self.assertFalse(window.engine.break_due)
        self.assertGreater(window.engine.break_remaining, 3599)
        self.assertFalse(window.break_button.isEnabled())

    def test_break_preview_does_not_reset_work_countdown(self):
        preferences = {**DEFAULT_PREFERENCES, "start_paused": True}
        with patch("desk_rhythm.read_configuration", return_value=(DEFAULTS, preferences)):
            window = Window(self.app)
        self.addCleanup(lambda: (window.end_break(), window.timer.stop(), window.tray.hide()))
        window.engine.break_remaining = 147
        window.preview_break("strong")
        surface = next(iter(window.preview_overlay.surfaces.values()))
        self.assertEqual(surface.timer_label.text(), "00:05")
        self.assertEqual(round(surface.tint.alphaF() * 100), 65)
        window.end_break()
        self.assertIsNone(window.preview_overlay)
        self.assertEqual(window.engine.break_remaining, 147)

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
