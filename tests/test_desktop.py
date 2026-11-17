"""Regression checks for v0.2 configuration migration and audio quiet hours."""

import json
import tempfile
import unittest
from pathlib import Path

from desktop import DEFAULT_PREFERENCES, in_quiet_hours, read_configuration, save_configuration
from reminder_core import DEFAULTS, load_settings


class PreferencesTests(unittest.TestCase):
    def test_legacy_and_extended_settings_round_trip(self):
        intervals = {**DEFAULTS, "sit_minutes": 49}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps(intervals))
            self.assertEqual(read_configuration(path), (intervals, DEFAULT_PREFERENCES))
            preferences = {**DEFAULT_PREFERENCES, "start_paused": True, "audio": False}
            save_configuration(intervals, preferences, path)
            self.assertEqual(read_configuration(path), (intervals, preferences))
            self.assertEqual(load_settings(path), intervals)

    def test_quiet_hours_across_midnight_and_during_day(self):
        preferences = {**DEFAULT_PREFERENCES, "quiet_enabled": True}
        self.assertTrue(in_quiet_hours(preferences, 22 * 60))
        self.assertTrue(in_quiet_hours(preferences, 7 * 60 + 59))
        self.assertFalse(in_quiet_hours(preferences, 8 * 60))
        self.assertFalse(in_quiet_hours(preferences, 21 * 60 + 59))
        preferences.update(quiet_start=60, quiet_end=120)
        self.assertTrue(in_quiet_hours(preferences, 90))
        self.assertFalse(in_quiet_hours(preferences, 120))

    def test_equal_quiet_time_rejected_without_overwriting_settings(self):
        preferences = {**DEFAULT_PREFERENCES, "quiet_enabled": True,
                       "quiet_end": DEFAULT_PREFERENCES["quiet_start"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_configuration(DEFAULTS, DEFAULT_PREFERENCES, path)
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                save_configuration(DEFAULTS, preferences, path)
            self.assertEqual(path.read_bytes(), original)
