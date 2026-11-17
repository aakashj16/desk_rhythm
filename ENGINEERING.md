# Desk Rhythm v0.3 engineering notes

## Source assessment

The supplied Markdown handoff contained all seven v0.2 files. The original tests
passed after extraction. The pure engine separates three countdowns, latches the
water and screen-break reminders, and supports pause, snooze, switch, and acknowledgement.
v0.3 retains that engine and the interval keys and bounds. Atomic writes now use
unique temporary files, and countdown formatting rounds fractions up consistently.

The original window mixed configuration and operation. Its synchronous `notify-send`
call could block the UI for up to three seconds. The v0.2 desktop launcher already set
`Terminal=false`, and Qt already used the matching short desktop filename.
The supplied source alone cannot establish why ARIA displayed `python3`. A bare source
launch, missing desktop entry, an obsolete pin, or different session platform can
affect association. v0.3 gives application metadata, desktop files, icon IDs and
notification hints the same stable ID and selects the Wayland Qt plugin in a Wayland
session. Qt uses the desktop filename as the app ID for xdg-shell surfaces.

## Design and module boundaries

| Area | Decision |
| --- | --- |
| Dashboard | Center the posture, countdown, and next transition. Use one thin progress bar, three equal-priority controls, and two compact reminder rows. |
| Typography and theme | Relative font sizing and a fixed-width countdown. Native Qt widgets derive colors and controls from the active Qt style, with keyboard mnemonics, accessible names and no forced palette. |
| Settings | Native dialog with Intervals, Notifications, and Behavior tabs. Validate and save explicitly, with in-dialog testing for the selected alert settings. |
| Icon | A white upright figure and mint circular motion arrow on a deep teal tile with transparent outer corners. The single scalable SVG serves launcher, tray and notices. |
| `reminder_core.py` | Existing pure model and interval compatibility. |
| `desk_rhythm.py` | Dashboard, tray, Qt app identity, active-time scheduling and per-user instance lock/socket. |
| `settings_dialog.py`, `desktop.py` | Dialog and persisted preferences, quiet-hour logic and XDG desktop helpers. |
| `notifications.py` | Asynchronous visual notices, D-Bus inhibition query and short-lived audio process with overlap protection. |
| `lifecycle.py` | Scoped file inventory, dry run, snapshots, migration and rollback shared by shell entry points. |

The chime is an original 0.88-second mono WAV synthesized from two gently decaying
notes. Playback uses `paplay` from Debian's `pulseaudio-utils`. It works through
the desktop's PulseAudio protocol, including PipeWire with `pipewire-pulse`.
This avoids loading Qt Multimedia or running a playback service. The automatic
check uses the Plasma 6.3 notification server's read-only `Inhibited` property,
which the notification applet binds to its effective inhibition state. Very rapid
changes in desktop inhibition can race any client-side check, so the playback
stream is also tagged with the desktop event role. The app sends a normal-urgency
notification and requests no separate notification-server sound.

The release uses the supplied source handoff and the reported v0.2 behavior.
The v0.2 screenshots were not included in that handoff.

## Verification

See [TESTING.md](TESTING.md) for completed checks and explicit gaps.

## References

- [Qt Wayland application identity](https://codebrowser.dev/qt6/qtbase/src/plugins/platforms/wayland/qwaylandwindow.cpp.html)
- [Debian Trixie Plasma Workspace 6.3.6 source](https://deb.debian.org/debian/pool/main/p/plasma-workspace/plasma-workspace_6.3.6.orig.tar.xz), particularly `libnotificationmanager/dbus/org.freedesktop.Notifications.xml` and `applets/notifications/package/contents/ui/global/Globals.qml`
- [Debian Trixie pulseaudio-utils](https://packages.debian.org/trixie/amd64/pulseaudio-utils)
- [Desktop Notifications specification](https://specifications.freedesktop.org/notification/latest-single/)
