from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget, QFrame
from PyQt6.QtCore import Qt


def _collapsible_toggle_color() -> str:
    from .styles import CURRENT_THEME

    return "#e6edf3" if CURRENT_THEME == "dark" else "#1a1a1a"


class CollapsibleSection(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setStyleSheet(
            f"QToolButton {{ border: none; font-weight: bold; color: {_collapsible_toggle_color()}; }}"
        )
        self.toggle_button.toggled.connect(self._on_toggled)

        self.content_area = QFrame()
        self.content_area.setVisible(False)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 6, 10, 8)
        self.content_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)

    def apply_theme(self) -> None:
        c = _collapsible_toggle_color()
        self.toggle_button.setStyleSheet(f"QToolButton {{ border: none; font-weight: bold; color: {c}; }}")

    def _on_toggled(self, checked: bool) -> None:
        self.content_area.setVisible(checked)
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
