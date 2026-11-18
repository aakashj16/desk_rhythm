"""User-local install, uninstall, and rollback with a scoped file inventory."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from desktop import APP_ID, APP_VERSION, BASE, MARKER, xdg
from reminder_core import atomic_text

PROJECT_FILES = (
    "desk_rhythm.py", "reminder_core.py", "desktop.py", "notifications.py",
    "settings_dialog.py", "break_overlay.py", "resources/desk-rhythm.svg",
    "resources/coffee.svg", "resources/chime.wav",
    "resources/LICENSE.md",
)
LEGACY = "desk-rhythm.desktop"
ICON = "desk-rhythm.svg"


def desktop_exec(path: Path) -> str:
    # Exec quoting is interpreted after desktop-entry string unescaping.
    text = str(path)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("The installation path contains a control character.")
    return '"' + "".join(
        "\\\\" + char if char in ('"', '`', '$') else
        "\\\\\\\\" if char == "\\" else "%%" if char == "%" else char
        for char in text
    ) + '"'


class Install:
    def __init__(self):
        self.data = xdg("XDG_DATA_HOME", ".local/share").resolve()
        self.config = xdg("XDG_CONFIG_HOME", ".config").resolve()
        self.bin = (Path.home() / ".local/bin").resolve()
        self.app = self.data / "desk-rhythm"
        self.entry = self.data / "applications" / f"{APP_ID}.desktop"
        self.old_entry = self.data / "applications" / LEGACY
        self.auto = self.config / "autostart" / self.entry.name
        self.old_auto = self.config / "autostart" / LEGACY
        self.launcher = self.bin / "desk-rhythm"
        self.icon = self.data / "icons/hicolor/scalable/apps" / f"{APP_ID}.svg"
        self.old_icon = self.icon.with_name(ICON)
        self.settings = self.config / "desk-rhythm/settings.json"
        self.state = xdg("XDG_STATE_HOME", ".local/state").resolve()
        self.backups = self.state / "desk-rhythm/backups"
        self.roots = (self.data, self.config, self.bin)
        self.payload = {self.app / name: BASE / name for name in PROJECT_FILES}
        self.managed = [
            *self.payload, self.entry, self.old_entry, self.auto, self.old_auto,
            self.launcher, self.icon, self.old_icon,
        ]

    def check_path(self, path):
        for root in self.roots:
            if path.is_relative_to(root):
                break
        else:
            raise OSError(f"Unexpected path: {path}")
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                raise OSError(f"Refusing symlink directory: {parent}")
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise OSError(f"Expected a regular file: {path}")

    @staticmethod
    def marked(path):
        if not path.is_file():
            return False
        rows = path.read_text(encoding="utf-8").splitlines()
        return MARKER in rows or "# " + MARKER in rows

    def legacy_installed(self):
        return (self.old_entry.is_file() and self.launcher.is_file()
                and "Name=Desk Rhythm" in self.old_entry.read_text().splitlines()
                and 'exec /usr/bin/python3 "$DATA_HOME/desk-rhythm/desk_rhythm.py" "$@"'
                in self.launcher.read_text().splitlines())

    def plan(self, action, purge=False):
        for path in [*self.managed, self.settings]:
            self.check_path(path)
        legacy = self.legacy_installed()
        current = self.marked(self.entry) or self.marked(self.launcher)
        if self.entry.exists() and not self.marked(self.entry):
            raise OSError(f"Another launcher exists at {self.entry}")
        if action == "install":
            if self.launcher.exists() and not (legacy or self.marked(self.launcher)):
                raise OSError(f"Another launcher exists at {self.launcher}")
            if not (legacy or current):
                for path in [*self.payload, self.icon]:
                    if path.exists():
                        raise OSError(f"Existing file has no Desk Rhythm launcher: {path}")
            if self.old_entry.exists() and not legacy:
                raise OSError(f"Cannot verify that this is a v0.2 launcher: {self.old_entry}")
            return [*self.payload, self.launcher, self.icon, self.entry,
                    *(p for p in (self.old_entry, self.old_icon) if legacy and p.exists()),
                    *(p for p in (self.old_auto,) if self.marked(p)),
                    *(p for p in (self.auto,) if self.marked(self.old_auto)
                      and not self.auto.exists()
                      and "hidden=true" not in self.old_auto.read_text().lower().splitlines())]
        paths = []
        if current or legacy:
            files = list(self.payload) if current else [
                self.app / name for name in ("desk_rhythm.py", "reminder_core.py", "resources/desk-rhythm.svg")]
            paths += [p for p in files if p.exists()]
            paths += [p for p in (self.launcher,) if legacy or self.marked(p)]
            if self.marked(self.entry):
                paths.append(self.entry)
            if current and self.icon.exists():
                paths.append(self.icon)
            if legacy:
                paths += [p for p in (self.old_entry, self.old_icon) if p.exists()]
        paths += [p for p in (self.auto, self.old_auto) if self.marked(p)]
        if purge and self.settings.exists():
            paths.append(self.settings)
        return paths

    def snapshot(self, paths):
        folder = Path(tempfile.mkdtemp(prefix="backup-", dir=self.backups))
        items = []
        for index, path in enumerate(dict.fromkeys(paths)):
            if path.exists():
                name = str(index)
                (folder / name).write_bytes(path.read_bytes())
                items.append([str(path), name, stat.S_IMODE(path.stat().st_mode)])
            else:
                items.append([str(path), None, None])
        atomic_text(folder / "manifest.json", json.dumps(items, indent=2) + "\n")
        return folder

    @staticmethod
    def write(path, content, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".desk-rhythm-",
                                         delete=False) as handle:
            tmp = Path(handle.name)
            try:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                os.chmod(tmp, mode)
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)

    def restore(self, folder, restore_settings=False):
        folder = folder.resolve()
        if folder.parent != self.backups.resolve():
            raise OSError("Choose a backup created by this installation.")
        items = json.loads((folder / "manifest.json").read_text())
        entries = []
        for filename, content, mode in items:
            path = Path(filename)
            if path == self.settings and not restore_settings:
                continue
            if path not in [*self.managed, self.settings]:
                raise OSError(f"Unexpected backup target: {path}")
            self.check_path(path)
            if content is not None and (not content.isdecimal() or not 0 <= mode <= 0o777):
                raise OSError("Invalid backup manifest.")
            entries.append((path, None if content is None else (folder / content).read_bytes(), mode))
        for path, data, mode in entries:
            if data is None:
                path.unlink(missing_ok=True)
            else:
                self.write(path, data, mode)

    def install(self, paths):
        launcher = (
            f"#!/bin/sh\n# {MARKER}\n"
            'DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}\n'
            'case "$DATA_HOME" in /*) ;; *) DATA_HOME="$HOME/.local/share";; esac\n'
            'exec /usr/bin/python3 -B "$DATA_HOME/desk-rhythm/desk_rhythm.py" "$@"\n')
        entry = f"""[Desktop Entry]
Type=Application
Name=Desk Rhythm
GenericName=Posture and wellness reminders
Comment=Track sitting, standing, water and screen breaks
Exec={desktop_exec(self.launcher)}
Icon={APP_ID}
Terminal=false
Categories=Utility;
StartupNotify=true
{MARKER}
"""
        payload = {path: (source.read_bytes(), 0o644) for path, source in self.payload.items()}
        payload.update({
            self.launcher: (launcher.encode(), 0o755),
            self.icon: ((BASE / "resources" / ICON).read_bytes(), 0o644),
            self.entry: (entry.encode(), 0o644),
        })
        if self.auto in paths:
            startup = entry.replace(f"Exec={desktop_exec(self.launcher)}",
                                    f"Exec={desktop_exec(self.launcher)} --background")
            payload[self.auto] = (startup.encode(), 0o644)
        for path in paths:
            if path in payload:
                self.write(path, *payload[path])
            else:
                path.unlink(missing_ok=True)

    def prune(self):
        for path in (self.app / "resources", self.app):
            try:
                path.rmdir()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("install").add_argument("--plan", action="store_true")
    uninstall = commands.add_parser("uninstall")
    uninstall.add_argument("--plan", action="store_true")
    uninstall.add_argument("--purge-settings", action="store_true")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("backup", type=Path)
    rollback.add_argument("--restore-settings", action="store_true")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Run as your regular desktop user.")
    install = Install()
    if BASE == install.app or BASE.is_relative_to(install.app):
        parser.error("Run this script from the development or extracted source folder.")
    try:
        if getattr(args, "plan", False):
            paths = install.plan(args.action, getattr(args, "purge_settings", False))
            for path in paths:
                print(path, "[exists]" if path.exists() else "[new]")
            if args.action == "install":
                print(f"Settings kept: {install.settings}")
            print(f"Backups: {install.backups}")
            return 0
        install.backups.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = install.backups / ".operation.lock"
        with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if args.action == "rollback":
                for path in [*install.managed, install.settings]:
                    install.check_path(path)
                paths = install.managed
            else:
                paths = install.plan(args.action, getattr(args, "purge_settings", False))
            backup_paths = [*paths, install.settings]
            if args.action == "install" and (not install.auto.exists() or install.marked(install.auto)):
                backup_paths.append(install.auto)
            backup = install.snapshot(backup_paths)
            print(f"Backup: {backup}", flush=True)
            try:
                if args.action == "install":
                    install.install(paths)
                elif args.action == "uninstall":
                    for path in paths:
                        path.unlink(missing_ok=True)
                else:
                    install.restore(args.backup, args.restore_settings)
            except (OSError, ValueError, TypeError):
                install.restore(backup, restore_settings=True)
                raise
            if args.action in ("uninstall", "rollback"):
                install.prune()
        print({"install": f"Installed Desk Rhythm v{APP_VERSION}.", "uninstall": "Desk Rhythm removed.",
               "rollback": "Backup restored."}[args.action])
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(f"Desk Rhythm: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
