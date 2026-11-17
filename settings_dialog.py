"""Native Qt controls for intervals, notifications, and startup."""

from PyQt6.QtCore import QTime
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QSpinBox, QTabWidget, QTimeEdit, QVBoxLayout, QWidget,
)

from desktop import APP_NAME, BASE, audio_player, autostart_enabled, desktop_path


class SettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Desk Rhythm Settings")
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        intervals = self.tab(tabs, "Intervals")
        self.intervals = {}
        for key, caption in (
            ("sit_minutes", "Sitting"), ("stand_minutes", "Standing"),
            ("water_minutes", "Water"), ("break_minutes", "Screen break"),
        ):
            spin = QSpinBox()
            spin.setRange(1, 240)
            spin.setSuffix(" min")
            spin.setValue(window.engine.settings[key])
            intervals.addRow(caption, spin)
            self.intervals[key] = spin
        info = QLabel("Changing an interval restarts all countdowns and clears due reminders.")
        info.setWordWrap(True)
        intervals.addRow(info)

        alerts = self.tab(tabs, "Notifications")
        self.checks = {}
        self.add_check(alerts, "visual", "Show desktop notifications")
        self.add_check(alerts, "audio", "Play the gentle chime")
        self.add_check(alerts, "quiet_enabled", "Mute reminders during quiet hours")
        self.times = {}
        for key, caption in (("quiet_start", "From"), ("quiet_end", "Until")):
            value = window.preferences[key]
            field = QTimeEdit(QTime(*divmod(value, 60)))
            field.setEnabled(self.checks["quiet_enabled"].isChecked())
            self.checks["quiet_enabled"].toggled.connect(field.setEnabled)
            alerts.addRow(caption, field)
            self.times[key] = field

        actions = QHBoxLayout()
        preview = QPushButton("Preview chime")
        preview.clicked.connect(lambda: window.notifications.preview(self))
        preview.setEnabled(bool(audio_player()))
        actions.addWidget(preview)
        test = QPushButton("Test notification")
        test.clicked.connect(self.test_notification)
        actions.addWidget(test)
        alerts.addRow(actions)
        if not audio_player():
            note = QLabel("Install pulseaudio-utils to enable chime playback.")
            note.setWordWrap(True)
            alerts.addRow(note)

        behavior = self.tab(tabs, "Behavior")
        self.login = QCheckBox("Launch on login")
        self.login.setChecked(autostart_enabled())
        entry = desktop_path()
        self.login.setEnabled(entry.is_file() and BASE == (entry.parent.parent / "desk-rhythm").resolve())
        if not self.login.isEnabled():
            self.login.setToolTip("Available when running the installed application.")
        behavior.addRow(self.login)
        self.add_check(behavior, "close_to_tray", "Keep reminders running in the tray on close")
        self.add_check(behavior, "start_paused", "Start with reminders paused")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def tab(tabs, name):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(16, 16, 16, 16)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        tabs.addTab(page, name)
        return form

    def add_check(self, form, key, label):
        check = QCheckBox(label)
        check.setChecked(self.window.preferences[key])
        form.addRow(check)
        self.checks[key] = check

    def preferences(self):
        values = {key: check.isChecked() for key, check in self.checks.items()}
        for key, field in self.times.items():
            value = field.time()
            values[key] = value.hour() * 60 + value.minute()
        return values

    def test_notification(self):
        preferences = self.preferences()
        if not self.window.notifications.send(
            "Desk Rhythm test", "Reminder notifications are ready.",
            preferences,
        ):
            QMessageBox.information(
                self, APP_NAME, "Turn on desktop notifications or sound, and check quiet hours."
            )

    def save(self):
        intervals = {key: spin.value() for key, spin in self.intervals.items()}
        try:
            self.window.apply_settings(intervals, self.preferences(), self.login.isChecked())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, APP_NAME, str(error))
            return
        self.accept()
