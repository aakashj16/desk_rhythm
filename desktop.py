"""Preferences and desktop services for the Qt application."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from reminder_core import atomic_text, config_path, validate_settings

APP_ID = "io.github.deskrhythm.DeskRhythm"
APP_NAME = "Desk Rhythm"
APP_VERSION = "0.4.1"
BASE = Path(__file__).resolve().parent
RESOURCES = BASE / "resources"
MARKER = "X-DeskRhythm-Managed=true"
DEFAULT_PREFERENCES = {
    "visual": True,
    "audio": True,
    "close_to_tray": True,
    "start_paused": False,
    "quiet_enabled": False,
    "break_overlay": False,
    "break_duration": 10,
    "overlay_strength": "medium",
    "quiet_start": 22 * 60,
    "quiet_end": 8 * 60,
}


def xdg(variable: str, fallback: str) -> Path:
    candidate = Path(os.environ.get(variable, ""))
    return candidate if candidate.is_absolute() else Path.home() / fallback


def autostart_path() -> Path:
    return xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{APP_ID}.desktop"


def desktop_path() -> Path:
    return xdg("XDG_DATA_HOME", ".local/share") / "applications" / f"{APP_ID}.desktop"


def read_configuration(path: Path | None = None) -> tuple[dict, dict]:
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    raw = data.get("preferences") if isinstance(data, dict) else None
    return validate_settings(data), validate_preferences(raw)


def validate_preferences(raw: object) -> dict:
    result = DEFAULT_PREFERENCES.copy()
    if isinstance(raw, dict):
        for key, default in DEFAULT_PREFERENCES.items():
            value = raw.get(key)
            if key == "overlay_strength":
                valid = isinstance(value, str) and value in ("soft", "medium", "strong")
            elif key == "break_duration":
                valid = type(value) is int and 1 <= value <= 120
            else:
                valid = type(value) is type(default) and (type(default) is bool or 0 <= value < 1440)
            if valid:
                result[key] = value
    if result["quiet_start"] == result["quiet_end"]:
        result["quiet_enabled"] = False
    return result


def save_configuration(intervals: dict, preferences: dict, path: Path | None = None) -> None:
    if validate_settings(intervals) != intervals or validate_preferences(preferences) != preferences:
        raise ValueError("Use valid intervals, a break duration from 1 to 120 minutes, and distinct quiet hours.")
    atomic_text(path or config_path(),
                json.dumps({**intervals, "preferences": preferences}, indent=2) + "\n")


def autostart_enabled() -> bool:
    try:
        rows = autostart_path().read_text(encoding="utf-8").splitlines()
        return MARKER in rows and not any(
            row.lower() == "hidden=true" for row in rows)
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    target = autostart_path()
    if target.is_symlink():
        raise OSError("Autostart points to another file.")
    if target.exists() and MARKER not in target.read_text(encoding="utf-8").splitlines():
        raise OSError("A different application owns this autostart entry.")
    if not enabled:
        target.unlink(missing_ok=True)
        return
    source = desktop_path()
    if BASE != (source.parent.parent / "desk-rhythm").resolve() or not source.is_file():
        raise OSError("Launch on login is available from the installed application.")
    rows = source.read_text(encoding="utf-8").splitlines()
    if not any(row.startswith("Exec=") for row in rows):
        raise OSError("The installed launcher has no Exec command.")
    rows = [row + " --background" if row.startswith("Exec=") else row for row in rows]
    atomic_text(target, "\n".join(rows) + "\n", 0o644)


def in_quiet_hours(preferences: dict, minute: int) -> bool:
    if not preferences["quiet_enabled"]:
        return False
    start, end = preferences["quiet_start"], preferences["quiet_end"]
    return start <= minute < end if start < end else minute >= start or minute < end


def audio_player() -> str | None:
    """paplay works with PulseAudio and PipeWire's PulseAudio compatibility server."""
    return shutil.which("paplay")


def runtime_socket() -> Path:
    return xdg("XDG_RUNTIME_DIR", ".cache") / APP_ID
