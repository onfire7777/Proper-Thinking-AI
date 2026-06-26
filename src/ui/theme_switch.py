"""Navbar dark/light control: compact pill track + thumb + label in one widget (reliable hit-testing)."""

from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen, QTextOption
from PyQt6.QtWidgets import QSizePolicy, QWidget

from . import styles as _styles


# Compact to match nav row height (~nav vertical padding + line)
TRACK_W = 34
TRACK_H = 18
THUMB_D = 14
TRACK_LABEL_SPACING = 6


class ThemeSwitch(QWidget):
    """Binary toggle: checked means dark mode (same semantics as the old QCheckBox)."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("themeToggle")
        self._checked = False
        self._hover = False

        # Match QPushButton[navLink="true"] in build_app_stylesheet: 14px, weight 500
        f = QFont()
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.Medium)
        self.setFont(f)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Dark mode")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QFontMetrics

        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance("Dark mode")
        w = TRACK_W + TRACK_LABEL_SPACING + text_w + 2
        h = max(TRACK_H + 2, fm.height())
        return QSize(w, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def _toggle(self) -> None:
        self.setChecked(not self._checked, emit=True)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, *, emit: bool = False) -> None:
        c = bool(checked)
        if c == self._checked:
            return
        self._checked = c
        self.update()
        if emit:
            self.toggled.emit(c)

    def setCheckedSilently(self, checked: bool) -> None:
        c = bool(checked)
        if c == self._checked:
            return
        self._checked = c
        self.update()

    def paintEvent(self, event) -> None:
        del event
        p = QPainter(self)
        p.setFont(self.font())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        dark = _styles.CURRENT_THEME == "dark"
        if dark:
            off_bg = QColor("#3d444d")
            on_bg = QColor("#238636")
            thumb = QColor("#f0f6fc")
            border = QColor("#484f58")
        else:
            off_bg = QColor("#e2e8f0")
            on_bg = QColor("#2563eb")
            thumb = QColor("#ffffff")
            border = QColor("#cbd5e1")

        bg = on_bg if self._checked else off_bg
        if self._hover:
            bg = QColor(bg.lighter(108))

        h = self.height()
        ty = max(0, (h - TRACK_H) // 2)
        tx = 0
        pad = 1
        rr = TRACK_H // 2
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(tx + pad, ty + pad, TRACK_W - 2 * pad, TRACK_H - 2 * pad, rr - 1, rr - 1)

        margin = 3
        y = ty + (TRACK_H - THUMB_D) // 2
        if self._checked:
            x = tx + TRACK_W - margin - THUMB_D
        else:
            x = tx + margin
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(thumb)
        p.drawEllipse(x, y, THUMB_D, THUMB_D)

        label_x = TRACK_W + TRACK_LABEL_SPACING
        text_color = QColor(_styles.NAV_TEXT)
        p.setPen(text_color)
        tr = QRect(label_x, 0, max(1, self.width() - label_x), h)
        opt = QTextOption(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        p.drawText(QRectF(tr), "Dark mode", opt)
