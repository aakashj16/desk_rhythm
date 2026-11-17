"""Run with: python3 -m unittest discover -s tests -v"""

import tempfile
import unittest
from pathlib import Path

from reminder_core import DEFAULTS, ReminderEngine, countdown, load_settings, save_settings, validate_settings


class ReminderCoreTests(unittest.TestCase):
    def test_defaults_and_corrupt_settings(self):
        self.assertEqual(validate_settings({"sit_minutes": 45, "water_minutes": -3})["sit_minutes"], 45)
        self.assertEqual(validate_settings({"water_minutes": -3})["water_minutes"], 60)
        self.assertEqual(validate_settings({"sit_minutes": True})["sit_minutes"], 30)
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "settings.json"
            file.write_text("invalid json")
            self.assertEqual(load_settings(file), DEFAULTS)

    def test_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "settings.json"
            settings = {**DEFAULTS, "sit_minutes": 25}
            save_settings(settings, file)
            self.assertEqual(load_settings(file), settings)

    def test_countdown(self):
        self.assertEqual(countdown(60), "01:00")
        self.assertEqual(countdown(1.1), "00:02")
        self.assertEqual(countdown(-5), "00:00")

    def test_position_cycle(self):
        engine = ReminderEngine({**DEFAULTS, "sit_minutes": 1, "stand_minutes": 1})
        self.assertEqual(engine.advance(61), ["position"])
        self.assertEqual(engine.phase, "standing")
        self.assertEqual(engine.advance(61), ["position"])
        self.assertEqual(engine.phase, "sitting")

    def test_water_break_ack(self):
        engine = ReminderEngine({key: 1 for key in DEFAULTS})
        self.assertEqual(engine.advance(61), ["position", "water", "break"])
        self.assertTrue(engine.water_due)
        self.assertTrue(engine.break_due)
        self.assertEqual(engine.advance(60), ["position"])
        engine.acknowledge_water()
        engine.acknowledge_break()
        self.assertEqual(engine.advance(61), ["position", "water", "break"])

    def test_pause_and_snooze(self):
        engine = ReminderEngine(DEFAULTS)
        engine.toggle_pause()
        self.assertEqual(engine.advance(3600), [])
        self.assertEqual(engine.position_remaining, 1800)
        engine.toggle_pause()
        engine.snooze_position(10)
        self.assertEqual(engine.position_remaining, 2400)
        engine.switch_position()
        self.assertEqual(engine.position_remaining, 900)

    def test_update_settings_keeps_phase_and_clears_due(self):
        engine = ReminderEngine({key: 1 for key in DEFAULTS})
        engine.advance(61)
        engine.update_settings(DEFAULTS)
        self.assertEqual(engine.phase, "standing")
        self.assertEqual(engine.position_remaining, 900)
        self.assertFalse(engine.water_due)
        self.assertFalse(engine.break_due)


if __name__ == "__main__":
    unittest.main()
