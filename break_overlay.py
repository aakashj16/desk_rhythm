"""Fullscreen break surfaces, with optional KWin backdrop blur."""

import ctypes
import math
import time

from PyQt6 import sip
from PyQt6.QtCore import QLibraryInfo, QRectF, Qt, QTimer, QT_VERSION_STR, pyqtSignal, qVersion
from PyQt6.QtGui import QColor, QFontDatabase, QIcon, QPainter, QRegion
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop import RESOURCES
from reminder_core import countdown

OVERLAY_OPACITY = {"soft": 35, "medium": 50, "strong": 65}


def request_kwin_blur(window):
    """Use the Debian KF6 window-effects API with Debian's system Qt."""
    if QApplication.platformName() != "wayland":
        return
    library_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.LibrariesPath)
    if not library_path.startswith("/usr/lib/") or qVersion() != QT_VERSION_STR:
        return
    try:
        library = ctypes.CDLL("libKF6WindowSystem.so.6")
        available = library._ZN14KWindowEffects17isEffectAvailableENS_6EffectE
        available.argtypes = [ctypes.c_int]
        available.restype = ctypes.c_bool
        enable = library._ZN14KWindowEffects16enableBlurBehindEP7QWindowbRK7QRegion
        enable.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p]
        enable.restype = None
        if available(7):  # KWindowEffects::BlurBehind
            full_window = QRegion()
            enable(sip.unwrapinstance(window), True, sip.unwrapinstance(full_window))
    except (OSError, AttributeError):
        # The tint remains usable when the optional native effect is unavailable.
        return


class BreakSurface(QWidget):
    dismissed = pyqtSignal()

    def __init__(self, strength):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Desk Rhythm — Break Time")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.tint = QColor(9, 15, 23, round(255 * OVERLAY_OPACITY[strength] / 100))
        outer = QVBoxLayout(self)
        panel = QWidget()
        panel.setObjectName("breakPanel")
        panel.setStyleSheet("""
            #breakPanel { background: #25303b; border-radius: 16px; }
            QLabel { color: #f2f6fb; background: transparent; }
            QLabel#breakHint { color: #c2d0dd; }
        """)
        panel.setMaximumWidth(350)
        contents = QVBoxLayout(panel)
        contents.setContentsMargins(38, 24, 38, 24)
        title = QLabel("Break Time")
        icon = QLabel()
        icon.setPixmap(QIcon(str(RESOURCES / "coffee.svg")).pixmap(22, 22))
        heading = QHBoxLayout()
        heading.addWidget(icon)
        heading.addWidget(title)
        contents.addLayout(heading)
        contents.setAlignment(heading, Qt.AlignmentFlag.AlignHCenter)
        font = title.font()
        font.setPointSizeF(max(13, font.pointSizeF() * 1.3))
        font.setBold(True)
        title.setFont(font)
        self.timer_label = QLabel()
        self.timer_label.setAccessibleName("Break time remaining")
        timer_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        timer_font.setPointSize(48)
        timer_font.setBold(True)
        self.timer_label.setFont(timer_font)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contents.addWidget(self.timer_label)
        hint = QLabel("Press Esc to end early.")
        hint.setObjectName("breakHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contents.addWidget(hint)
        outer.addWidget(panel, alignment=Qt.AlignmentFlag.AlignCenter)
        self.finished = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(QRectF(self.rect()), self.tint)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.dismissed.emit()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.accept()
        if not self.finished:
            self.dismissed.emit()


class BreakOverlay:
    """One timed break with a synchronized surface on each available screen."""

    def __init__(self, app, seconds, strength, completed, now=time.monotonic):
        self.app = app
        self.strength = strength
        self.completed = completed
        self.now = now
        self.deadline = now() + seconds
        self.surfaces = {}
        self.tick = QTimer()
        self.tick.setInterval(200)
        self.tick.timeout.connect(self.update)
        self.app.screenAdded.connect(self.show_screen)
        self.app.screenRemoved.connect(self.remove_screen)

    def start(self):
        screens = self.app.screens()
        if not screens:
            self.finish(False)
            return
        for screen in screens:
            self.show_screen(screen)
        surface = self.surfaces.get(self.app.primaryScreen())
        if surface is not None:
            surface.activateWindow()
            surface.setFocus()
        self.tick.start()

    def show_screen(self, screen):
        surface = BreakSurface(self.strength)
        surface.dismissed.connect(self.dismiss)
        self.surfaces[screen] = surface
        surface.winId()
        window = surface.windowHandle()
        window.setScreen(screen)
        surface.timer_label.setText(countdown(self.deadline - self.now()))
        surface.showFullScreen()
        request_kwin_blur(window)

    def remove_screen(self, screen):
        surface = self.surfaces.pop(screen, None)
        if surface is not None:
            self.close_surface(surface)
        if not self.surfaces:
            self.finish(False)

    def update(self):
        seconds = math.ceil(self.deadline - self.now())
        if seconds <= 0:
            self.finish(True)
            return
        text = countdown(seconds)
        for surface in self.surfaces.values():
            if surface.timer_label.text() != text:
                surface.timer_label.setText(text)

    def dismiss(self):
        self.finish(False)

    def finish(self, completed):
        callback, self.completed = self.completed, None
        if callback is None:
            return
        self.tick.stop()
        self.app.screenAdded.disconnect(self.show_screen)
        self.app.screenRemoved.disconnect(self.remove_screen)
        for surface in self.surfaces.values():
            self.close_surface(surface)
        self.surfaces.clear()
        callback(completed)

    @staticmethod
    def close_surface(surface):
        surface.finished = True
        surface.close()
        surface.deleteLater()
