"""Wraps a card-style QTableWidget: centered empty-state message over the body when rowCount is 0."""

from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QFrame, QLabel, QTableWidget, QVBoxLayout, QSizePolicy, QWidget

from .styles import MUTED_LABEL_STYLE, apply_card_style_table_viewport_style


class CardTableFrame(QFrame):
    """Table + overlay empty message (no fake rows). Parent table must use configure_card_style_table."""

    def __init__(
        self,
        table: QTableWidget,
        empty_message: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._table = table
        self._empty = QLabel(empty_message, self)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(MUTED_LABEL_STYLE + " background-color: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(table)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._empty.raise_()
        m = table.model()
        if m is not None:
            m.rowsInserted.connect(self._on_model_rows_changed)
            m.rowsRemoved.connect(self._on_model_rows_changed)
            m.modelReset.connect(self._on_model_rows_changed)
        self._on_model_rows_changed()
        QTimer.singleShot(0, self._position_empty)

    def _on_model_rows_changed(self, *args) -> None:
        self._empty.setVisible(self._table.rowCount() == 0)
        apply_card_style_table_viewport_style(self._table)
        self._position_empty()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_empty()

    def showEvent(self, event):
        super().showEvent(event)
        apply_card_style_table_viewport_style(self._table)
        QTimer.singleShot(0, self._position_empty)
        QTimer.singleShot(0, lambda: apply_card_style_table_viewport_style(self._table))

    def apply_empty_style(self) -> None:
        self._empty.setStyleSheet(MUTED_LABEL_STYLE + " background-color: transparent;")

    def refresh_empty_overlay(self) -> None:
        self._position_empty()

    def _position_empty(self) -> None:
        if not self._empty.isVisible():
            return
        hdr = self._table.horizontalHeader()
        if hdr is None:
            return
        header_h = hdr.height() if hdr.isVisible() and hdr.height() > 0 else int(hdr.sizeHint().height())
        self._empty.setGeometry(0, header_h, self.width(), max(0, self.height() - header_h))
        self._empty.raise_()
