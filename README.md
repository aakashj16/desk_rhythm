# Desk Rhythm

Desk Rhythm is a lightweight KDE Plasma tray app for sit–stand, water, and screen-break reminders. It runs locally and uses desktop notifications and a short chime.

**Current version: v0.3.1.** The initial target is Debian 13 (Trixie) with KDE Plasma on Wayland. This setup was used on ARIA for everyday testing. See [TESTING.md](TESTING.md) for the test coverage and remaining desktop checks.

## Download and install

[Download the source ZIP](https://github.com/aakashj16/desk_rhythm/archive/refs/heads/main.zip), then extract it. Alternatively, clone the repository with Git:

```bash
git clone https://github.com/aakashj16/desk_rhythm.git
cd desk_rhythm
```

From a KDE Plasma Wayland session, install the Debian dependencies:

```bash
sudo apt update
sudo apt install python3-pyqt6 qt6-wayland libnotify-bin pulseaudio-utils
```

`libnotify-bin` provides desktop notifications. `pulseaudio-utils` provides `paplay` for the chime and uses the session’s existing PulseAudio-compatible audio service.

Open a terminal in the extracted `desk_rhythm-main` folder or the cloned `desk_rhythm` folder. Preview the changes, then install as your regular user:

```bash
sh install.sh --plan
sh install.sh
```

Open **Desk Rhythm** from the KDE Application Launcher. Go to **Settings → Notifications → Preview chime** to check audio. **Settings → Behavior** controls launch on login and close-to-tray behavior.

## Using Desk Rhythm

- The default timers are 30 minutes sitting, 15 minutes standing, and 60 minutes each for water and screen breaks. Change the intervals in **Settings**.
- **Pause** stops all countdowns. **Switch now** changes posture immediately. **Snooze 10 min** adds ten minutes to the posture timer.
- A circled checkmark restarts its own water or screen-break timer. A **Due** badge marks an expired reminder until you acknowledge it.
- Automatic chimes respect quiet hours and require Plasma to report that notification inhibition is off. Visual and audio reminders can be disabled independently.
- Use **Quit Desk Rhythm** from the tray menu to stop the app completely.

Desk Rhythm does not require an account and does not collect telemetry.

## Upgrade, roll back, or uninstall

**Upgrade.** Download the current ZIP again or update your clone. Quit the running app from the tray, then run `sh install.sh` from the new source folder. The installer preserves user settings and managed autostart and prints a `Backup:` path.

**Rollback.** Quit the app and run this from the source folder used for the upgrade. Replace the example path with the exact `Backup:` path printed by the installer:

```bash
/usr/bin/python3 -B lifecycle.py rollback "/path/from/the/Backup-line"
```

This restores the backed-up application and launcher files and keeps current settings by default. Add `--restore-settings` to restore the settings snapshot too.

**Uninstall.** Quit the app, then preview and remove the managed files from the source folder:

```bash
sh uninstall.sh --plan
sh uninstall.sh
```

Settings are kept unless you run `sh uninstall.sh --purge-settings`. The installer uses user-local XDG directories. The default settings file is `~/.config/desk-rhythm/settings.json`, and backups go under `~/.local/state/desk-rhythm/backups/`.

## v0.3.1 changes

- Renamed Movement break to Screen break and added keyboard-accessible circled completion controls.
- Added accent-colored Due badges and kept reminder rows in place through status changes.
- Increased the chime by 6 dB and made the paused state clearer.

See [ENGINEERING.md](ENGINEERING.md) for the desktop integration and timer design. To run the tests from the source folder, use a separate D-Bus session:

```bash
dbus-run-session -- /usr/bin/python3 -B -m unittest discover -s tests -v
```

## License

Desk Rhythm source code is licensed under the [GNU General Public License v3.0](LICENSE). The bundled chime and icon have separate [asset licensing](resources/LICENSE.md).
