# Desk Rhythm verification

## v0.4.1

The offscreen regression test confirms that Esc re-enables the completion
checkmark on a due break. The checkmark resets the work interval and remains
disabled during an active fullscreen break.

## v0.4.0 preflight

The offscreen Qt suite checks the one-minute warning, 10-minute snooze,
repeated warning, Esc dismissal, timer completion, and preview behavior.
The install package was exercised in a temporary home and XDG environment
with an existing v0.3.1 install and rollback snapshot. A live KDE Wayland
session was unavailable. Native blur, full-screen stacking, focus,
notification actions, and the optional KDE command shortcut need on-device checks.

## v0.3.1 milestone checks

- Offscreen Qt tests and manual checks verified mouse/keyboard completion, Due badge transitions, stable row geometry and pause/resume. The live session-bus test was skipped.
- The revised 0.88-second PCM chime measured +6 dB with no clipping. The user confirmed the revised chime was clear on ARIA.
- The v0.3 to v0.3.1 upgrade and rollback were exercised in temporary HOME/XDG directories, with settings and an existing autostart entry preserved.

The remaining sections record baseline v0.3 verification.

## Completed in the build environment

| Check | Result |
| --- | --- |
| Original v0.2 reminder suite | 7 of 7 passed before changes and again on v0.3. |
| v0.3 tests on Debian 13 using Python 3.13 and PyQt6 6.9.0 | 12 passed, one skipped. Covers v0.2 settings migration, preferences, midnight quiet hours, dashboard controls, long wake gaps and Qt D-Bus reply handling. |
| Offscreen visual inspection | Dashboard and settings dialog rendered and were visually reviewed. The dashboard was about 420 × 317 logical pixels under the test style. The SVG rendered with transparency at 16, 24, 32, 48 and 64 px. |
| Installer lifecycle in temporary HOME and XDG directories | Fresh install, reinstall, upgrade from the original v0.2 installer, enabled autostart migration, precise restoration of v0.2 files, both rollback settings modes, and uninstall with settings preserved or explicitly purged. Verified an unrelated user file survived and tested paths containing spaces. |
| Launcher and icon | `desktop-file-validate` accepted the launcher and migrated autostart entry. The installed shell launcher started the offscreen app from `/` after its development directory was moved. |
| Static and packaging checks | Python compilation, POSIX shell syntax, WAV format, executable script modes, and ZIP integrity. |

A five-second hidden offscreen sample used 8.50 ms of process CPU and 48.4 MiB peak
RSS, including Qt runtime initialization in the peak. This measures one short sample
in the build environment. Use KDE System Monitor on ARIA for desktop-session numbers.

## Still to verify on ARIA

The build environment prevented starting a local D-Bus broker. The private-bus
integration test was skipped, but the Qt reply-handling test passed. The installed
app rendered offscreen with its IPC socket unavailable, so launcher reactivation
still needs a desktop test.

On a clean Debian 13 Plasma Wayland session, check native Wayland taskbar grouping and icon, tray
actions and close behavior, visual notification delivery, audible output and DND,
real suspend/resume, Breeze light and dark, and a future login with autostart enabled.
The packaged chime was verified as PCM audio. A live audio sink was unavailable
during the build. No tests were run on ARIA and no changes were made there.
