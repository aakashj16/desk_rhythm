"""Pure reminder logic and settings for Desk Rhythm (no GUI dependencies)."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Literal

DEFAULTS: dict[str, int] = {
    "sit_minutes": 30,
    "stand_minutes": 15,
    "water_minutes": 60,
    "break_minutes": 60,
}


def config_path() -> Path:
    home = Path(os.environ.get("XDG_CONFIG_HOME", ""))
    if not home.is_absolute():
        home = Path.home() / ".config"
    return home / "desk-rhythm" / "settings.json"


def validate_settings(data: object) -> dict[str, int]:
    result = DEFAULTS.copy()
    if isinstance(data, dict):
        for key in result:
            value = data.get(key)
            if type(value) is int and 1 <= value <= 240:
                result[key] = value
    return result


def load_settings(path: Path | None = None) -> dict[str, int]:
    path = path or config_path()
    try:
        return validate_settings(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError):
        return DEFAULTS.copy()


def save_settings(settings: dict[str, int], path: Path | None = None) -> None:
    """Atomic write; reject invalid settings rather than silently correcting them."""
    if (set(settings) != set(DEFAULTS) or
            any(type(settings[key]) is not int or not 1 <= settings[key] <= 240
                for key in DEFAULTS)):
        raise ValueError("All intervals must be whole minutes from 1 to 240")
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(path, json.dumps(settings, indent=2) + "\n")


def atomic_text(path: Path, content: str, mode: int = 0o600) -> None:
    """Replace a file from a unique temporary file on the same filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".desk-rhythm-", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def countdown(seconds: float) -> str:
    whole = max(0, math.ceil(seconds))
    return f"{whole // 60:02d}:{whole % 60:02d}"


Reminder = Literal["position", "water", "break"]


class ReminderEngine:
    """Tracks active-time countdowns; time comes from GUI or tests.

    Only one notice per type is emitted per `advance` call. Water and break
    reminders latch until acknowledged, avoiding notification spam.
    """

    def __init__(self, settings: dict[str, int]):
        self.settings = validate_settings(settings)
        self.phase: Literal["sitting", "standing"] = "sitting"
        self.paused = False
        self.position_remaining = self.settings["sit_minutes"] * 60.0
        self.water_remaining = self.settings["water_minutes"] * 60.0
        self.break_remaining = self.settings["break_minutes"] * 60.0
        self.water_due = False
        self.break_due = False

    def duration_for_phase(self) -> int:
        key = "stand_minutes" if self.phase == "standing" else "sit_minutes"
        return self.settings[key] * 60

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def switch_position(self) -> None:
        self.phase = "standing" if self.phase == "sitting" else "sitting"
        self.position_remaining = float(self.duration_for_phase())

    def snooze_position(self, minutes: int = 10) -> None:
        if minutes <= 0:
            raise ValueError("Snooze minutes must be positive")
        self.position_remaining += minutes * 60

    def acknowledge_water(self) -> None:
        self.water_due = False
        self.water_remaining = self.settings["water_minutes"] * 60.0

    def acknowledge_break(self) -> None:
        self.break_due = False
        self.break_remaining = self.settings["break_minutes"] * 60.0

    def snooze_break(self) -> None:
        self.break_due = False
        self.break_remaining = 600.0

    def update_settings(self, settings: dict[str, int]) -> None:
        validated = validate_settings(settings)
        if validated != settings:
            raise ValueError("Invalid intervals")
        self.settings = validated
        self.position_remaining = float(self.duration_for_phase())
        self.acknowledge_water()
        self.acknowledge_break()

    def advance(self, elapsed_seconds: float) -> list[Reminder]:
        if elapsed_seconds <= 0 or self.paused:
            return []
        due: list[Reminder] = []
        self.position_remaining -= elapsed_seconds
        if self.position_remaining <= 0:
            self.switch_position()
            due.append("position")
        if not self.water_due:
            self.water_remaining -= elapsed_seconds
            if self.water_remaining <= 0:
                self.water_remaining = 0
                self.water_due = True
                due.append("water")
        if not self.break_due:
            self.break_remaining -= elapsed_seconds
            if self.break_remaining <= 0:
                self.break_remaining = 0
                self.break_due = True
                due.append("break")
        return due
