# Desk Rhythm

Desk Rhythm is a lightweight KDE Plasma tray app for sit–stand, water, and screen-break reminders. It runs locally and uses desktop notifications and a short chime.

**Current version: v0.4.1.** The initial target is Debian 13 (Trixie) with KDE Plasma on Wayland. This setup was used on ARIA for everyday testing. See [TESTING.md](TESTING.md) for the test coverage and remaining desktop checks.

## Download and install

[Download the source ZIP](https://github.com/aakashj16/desk_rhythm/archive/refs/heads/main.zip)
and extract it, or clone the repository:

```bash
git clone https://github.com/aakashj16/desk_rhythm.git
cd desk_rhythm
```

Run the steps below from the extracted or cloned source directory.
The installer uses the same user-local launcher as v0.3.1.

1. If you're setting up a new system, install the runtime dependencies:

   ```bash
   sudo apt update
   sudo apt install python3-pyqt6 qt6-wayland libnotify-bin pulseaudio-utils
   ```

   KDE's optional backdrop blur uses `libkf6windowsystem6`, normally installed
   with KDE Plasma. The overlay still dims the screen when blur is unavailable.
2. Preview the install with `sh install.sh --plan`.
3. Quit the running copy from the Desk Rhythm tray menu, then run `sh install.sh`
   as your regular user. The installer preserves settings and managed autostart.
   Keep the `Backup:` path.
4. Open **Desk Rhythm** from the KDE Application Launcher. In **Settings →
   Break Time**, enable the overlay and choose your work interval and break
   duration. Preview the overlay for five seconds and test Esc before saving.
   The overlay is off for existing and new installations until you enable it.

## Break Time

- Work interval is adjustable from 1 to 240 minutes. Break duration is adjustable
  from 1 to 120 minutes. For example, 50 minutes of work and 10 minutes of break
  make a 60-minute cycle.
- One minute before the overlay appears, the desktop notification offers
  **Snooze 10 min**. A snooze schedules a new warning nine minutes later and
  another break one minute after that. The tray also offers snooze when the
  break is due or within a minute. Snooze affects only Break Time.
- When the overlay has keyboard focus, **Esc** restores the screen immediately.
  Ending early leaves the break due. Use the dashboard checkmark to mark it
  complete and start a fresh work interval, or start or snooze it from the tray.
  While the overlay is active, the checkmark stays disabled. Completing the
  countdown starts a fresh work interval automatically.
- **Soft**, **Medium**, and **Strong** set the tint to 35%, 50%, and 65%.
  KDE's compositor sets the actual blur radius. Without native blur, the
  overlay still uses the selected tint. **Preview overlay** uses the same
  rendering without resetting the working countdown.
- If Esc has no effect, use **End Break Time early** in the tray. For a
  keyboard fallback independent of overlay focus, set a KDE global command
  shortcut to `~/.local/bin/desk-rhythm --end-break` (use the full path in
  KDE Settings). Test that shortcut in your session before relying on it.
- Actionable warnings follow visual notification preferences and may be suppressed
  by KDE Do Not Disturb. Desk Rhythm's quiet hours prevent automatic overlays.
  Snooze before screen sharing if you need uninterrupted presentation time.
  Verify fullscreen stacking, Esc focus, and notification actions on your KDE
  session.

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

## v0.4.1 changes

- Break Time adds an optional fullscreen work/break cycle with a one-minute warning and ten-minute snooze.
- After Esc dismisses the overlay, the checkmark becomes available to clear a due break.
- v0.4.1 was confirmed working on ARIA (Debian 13 with KDE Plasma on Wayland).

## v0.3.1 changes

- Renamed Movement break to Screen break and added keyboard-accessible circled completion controls.
- Added accent-colored Due badges and kept reminder rows in place through status changes.
- Increased the chime by 6 dB and made the paused state clearer.

See [ENGINEERING.md](ENGINEERING.md) for the desktop integration and timer design. To run the tests from the source folder, use a separate D-Bus session:

```bash
dbus-run-session -- /usr/bin/python3 -B -m unittest discover -s tests -v
```

## License

Desk Rhythm source code is licensed under the [GNU General Public License v3.0](LICENSE). The bundled chime and icons have separate [asset licensing](resources/LICENSE.md).
