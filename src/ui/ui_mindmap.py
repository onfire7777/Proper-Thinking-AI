"""Mindmap tab: Obsidian-style force graph (QWebEngineView + vis-network). Full-page graph view."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QSizePolicy,
)

from src.api import service

from ..core.book_manager import BookManager
from .mindmap_graph_payload import build_graph_payload
from .styles import (
    BTN_SECONDARY_SMALL,
    MINDMAP_WEB_VIEW_MIN_HEIGHT,
    TAB_MARGINS,
    TAB_SPACING,
    configure_tab_scroll_area,
    create_header_widget,
    create_select_book_row,
    wire_scroll_content_margins,
)

log = logging.getLogger(__name__)

_MINDMAP_HTML_PATH = Path(__file__).resolve().parent / "resources" / "mindmap_graph" / "index.html"

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None  # type: ignore[misc, assignment]
    _WEBENGINE_AVAILABLE = False


class MindmapTab(QWidget):
    """Mindmap tab: select book, view framework graph in embedded WebEngine (vis-network)."""

    def __init__(self, book_manager: BookManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # Same BookManager as ``service`` after ``MainWindow`` calls ``service.bind_book_manager``.
        self.book_manager = book_manager
        self.selected_book_id: Optional[int] = None
        self._last_graph_payload: Dict[str, Any] = {"version": 1, "nodes": [], "edges": []}
        self._graph_page_ready = False
        self._web_view: Optional[Any] = None
        self._init_ui()
        self._load_books()

    def _init_ui(self):
        # Read theme after run_gui's set_theme() — module-level CURRENT_THEME imports are stale.
        from .styles import CURRENT_THEME

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea(self)
        configure_tab_scroll_area(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(*TAB_MARGINS)
        content_layout.setSpacing(TAB_SPACING)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(
            create_header_widget(
                self,
                "Mindmap",
                "Interactive graph of framework relationships (force layout). Select a book with a framework.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        self._book_label, self.book_combo, self.refresh_btn = create_select_book_row(self)
        self.refresh_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self.book_combo.currentIndexChanged.connect(self._on_book_selected)
        self.refresh_btn.clicked.connect(self._load_books)
        book_row = QHBoxLayout()
        book_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        book_row.addWidget(self._book_label, 0)
        book_row.addWidget(self.book_combo, 0)
        book_row.addStretch(1)
        book_row.addWidget(self.refresh_btn, 0)
        content_layout.addLayout(book_row)

        mindmap_frame = QFrame()
        self._mindmap_frame = mindmap_frame
        mindmap_frame.setStyleSheet(
            "QFrame { border: 1px solid #c0c0c0; border-radius: 6px; background: #000000; }"
            if CURRENT_THEME == "light"
            else "QFrame { border: 1px solid #444c56; border-radius: 6px; background: #000000; }"
        )
        mindmap_frame_layout = QVBoxLayout(mindmap_frame)
        mindmap_frame_layout.setContentsMargins(2, 2, 2, 2)
        mindmap_frame_layout.setSpacing(0)

        if not _WEBENGINE_AVAILABLE or QWebEngineView is None:
            err = QLabel(
                "PyQt6-WebEngine is not installed. Install with:\n"
                "  pip install PyQt6-WebEngine\n"
                "Then restart the application."
            )
            err.setWordWrap(True)
            err.setStyleSheet(
                "color: #b71c1c; padding: 16px; background: #fff;"
                if CURRENT_THEME == "light"
                else "color: #f85149; padding: 16px; background: #161B22;"
            )
            mindmap_frame_layout.addWidget(err)
        elif not _MINDMAP_HTML_PATH.is_file():
            err = QLabel(f"Mindmap graph asset missing: {_MINDMAP_HTML_PATH}")
            err.setWordWrap(True)
            err.setStyleSheet(
                "color: #b71c1c; padding: 16px; background: #fff;"
                if CURRENT_THEME == "light"
                else "color: #f85149; padding: 16px; background: #161B22;"
            )
            mindmap_frame_layout.addWidget(err)
        else:
            self._web_view = QWebEngineView(mindmap_frame)
            self._web_view.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self._web_view.setMinimumHeight(MINDMAP_WEB_VIEW_MIN_HEIGHT)
            self._web_view.setStyleSheet("background: #000000; border: none;")
            s = self._web_view.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            self._web_view.loadFinished.connect(self._on_graph_page_loaded)
            url = QUrl.fromLocalFile(str(_MINDMAP_HTML_PATH.resolve()))
            self._web_view.load(url)
            mindmap_frame_layout.addWidget(self._web_view, stretch=1)

        content_layout.addWidget(mindmap_frame, stretch=1)
        scroll.setWidget(content)
        self._scroll_area = scroll
        wire_scroll_content_margins(scroll, content_layout)
        layout.addWidget(scroll, stretch=1)
        self.apply_theme()

    def apply_theme(self) -> None:
        from .styles import (
            COMBO_STYLE,
            CURRENT_THEME,
            configure_tab_scroll_area,
            refresh_scroll_content_margins,
            select_book_row_label_style,
        )

        self._book_label.setStyleSheet(select_book_row_label_style())
        self._book_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.book_combo.setStyleSheet(COMBO_STYLE)
        self.refresh_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self._mindmap_frame.setStyleSheet(
            "QFrame { border: 1px solid #c0c0c0; border-radius: 6px; background: #000000; }"
            if CURRENT_THEME == "light"
            else "QFrame { border: 1px solid #444c56; border-radius: 6px; background: #000000; }"
        )
        configure_tab_scroll_area(self._scroll_area)
        # scroll content layout — need ref; wire_scroll uses internal filter
        sl = self._scroll_area.widget().layout()
        if isinstance(sl, QVBoxLayout):
            refresh_scroll_content_margins(self._scroll_area, sl)

    def _on_graph_page_loaded(self, ok: bool):
        if not ok:
            log.warning("Mindmap graph page failed to load: %s", _MINDMAP_HTML_PATH)
            return
        self._graph_page_ready = True
        self._inject_graph_payload(self._last_graph_payload)

    def _inject_graph_payload(self, payload: Dict[str, Any]) -> None:
        if not self._web_view or not self._graph_page_ready:
            return
        try:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            b64 = base64.b64encode(raw).decode("ascii")
            js = f"window.setGraphDataFromB64({json.dumps(b64)});"
            self._web_view.page().runJavaScript(js)
        except Exception as exc:
            log.exception("Mindmap inject failed: %s", exc)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_books()

    def _load_books(self):
        try:
            all_books = service.list_books()
            with_emb = [b for b in all_books if b.get("embeddings_generated", False)]
            current_book = self.selected_book_id
            self.book_combo.clear()
            for b in with_emb:
                self.book_combo.addItem(b.get("title", "Untitled"), b["id"])
            idx = 0
            for i in range(self.book_combo.count()):
                if self.book_combo.itemData(i) == current_book:
                    idx = i
                    break
            self.book_combo.setCurrentIndex(idx)
            self._on_book_selected(idx)
        except Exception as exc:
            log.warning("Mindmap _load_books: %s", exc)

    def _on_book_selected(self, index: int):
        if index < 0:
            self.selected_book_id = None
            self._render_mindmap(None)
            return
        bid = self.book_combo.itemData(index)
        self.selected_book_id = int(bid) if bid is not None else None
        if self.selected_book_id is None:
            self._render_mindmap(None)
            return
        try:
            fws = service.framework_list(self.selected_book_id)
            if not fws:
                self._render_mindmap(None)
                return
            fw = fws[0]
            full = service.framework_get(self.selected_book_id, int(fw["id"]))
            self._render_mindmap(full)
        except Exception as exc:
            log.exception("Mindmap load failed")
            self._render_mindmap(None)

    def _render_mindmap(self, full: Optional[Dict[str, Any]]) -> None:
        self._last_graph_payload = build_graph_payload(full)
        if self._web_view and self._graph_page_ready:
            self._inject_graph_payload(self._last_graph_payload)
