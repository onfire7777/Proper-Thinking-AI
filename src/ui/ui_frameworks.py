import html
import re
import logging
from typing import Optional, Dict, Any, List

from ..core.logic_audit_normalize import prepare_audit_result_for_ui

log = logging.getLogger(__name__)
_ASK_SEP = '<div style="border-top:1px solid #d0d0d0;margin:4px 0 2px 0;height:0;"></div>'

# Shared framework content styles (headings, lists, body, context) for UI consistency
_FW_HEADING_STYLE = "margin:12px 0 6px 0; font-size:16px; font-weight:bold; color:#111111;"
_FW_BODY_STYLE = "margin:0 0 6px 0; font-size:13px; color:#444444; line-height:1.4;"

# Two-column tables: label column (grey + bold) vs value column (normal, white).
_FW_TABLE_LABEL_COL = (
    "border:1px solid #bdbdbd; padding:6px 8px; font-size:12px; vertical-align:top; "
    "text-align:left; background:#e8e8e8; color:#222222; font-weight:700;"
)
_FW_TABLE_VALUE_COL = (
    "border:1px solid #bdbdbd; padding:6px 8px; font-size:12px; vertical-align:top; "
    "text-align:left; background:#ffffff; color:#444444; font-weight:400;"
)
_FW_UL_STYLE = "margin:0 0 5px 0; padding-left:22px; list-style-type:disc;"
_FW_LI_STYLE = "margin-bottom:8px; font-size:13px; color:#444444; line-height:1.4;"

# Definitive subsection row (Term / Step N / …) — color on inner <span> so PDF/Qt prints text (not a stray line).
_FW_SUBSECTION_P = "margin:10px 0 6px 0; line-height:1.35;"
_FW_SUBSECTION_SPAN_BY_KIND = {
    "definition": "font-size:16px; font-weight:700; color:#0d47a1;",
    "principle": "font-size:16px; font-weight:700; color:#0d47a1;",
    "step": "font-size:16px; font-weight:700; color:#111111;",
    "warning": "font-size:16px; font-weight:700; color:#e65100;",
    "constraint": "font-size:16px; font-weight:700; color:#1b5e20;",
}
# Epistemic UI size (px). PDF forces 10pt in pdf_export.prepare_framework_body_html only.
_FW_EPISTEMIC_FONT = "11.5px"
_FW_EPISTEMIC_TXT_CLASS = "fw-epistemic-txt"  # PDF prep retargets this + fw-epistemic* divs to 10pt

# Outer FW block: white surface so only the Source row (inside epistemic block) uses light grey #f5f5f5.
_FW_BLOCK_WRAP_STYLE = (
    "margin:14px 0 16px 0;padding:12px 14px 14px 14px;border:1px solid #e0e0e0;border-radius:8px;"
    "background:#ffffff;box-shadow:0 1px 2px rgba(0,0,0,0.04);"
)

from ..core.definitive_style_markers import (
    FW_EPISTEMIC_BEGIN,
    FW_EPISTEMIC_END,
    FW_BLOCK_END,
    RE_FW_BLOCK_OPEN,
    RE_FW_HEADING,
)

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QApplication,
    QScrollArea,
    QFrame,
    QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QShowEvent

from src.api import service

from ..core.book_manager import BookManager
from .styles import (
    FRAMEWORK_ASK_DOC_STYLESHEET,
    FRAMEWORK_AUDIT_VIEW_STYLE,
    FRAMEWORK_CONTENT_VIEW_STYLE,
    MUTED_LABEL_STYLE,
    TEXTEDIT_READONLY_STYLE,
    TEXTEDIT_SMALL_STYLE,
    apply_card_style_table_viewport_style,
    create_header_widget,
    create_section_card,
    create_select_book_row,
    configure_card_style_table,
    configure_tab_scroll_area,
    refresh_scroll_content_margins,
    refresh_section_cards,
    sync_card_style_table_height,
    wire_scroll_content_margins,
    TAB_MARGINS,
    TAB_SPACING,
    BTN_PRIMARY,
    BTN_PRIMARY_SMALL,
    BTN_SECONDARY,
    BTN_SECONDARY_SMALL,
    BTN_DANGER_SMALL,
    INPUT_LINE,
    CURRENT_THEME,
)
from .collapsible import CollapsibleSection
from .docx_export import _split_source_epistemic_label_body, export_framework_to_docx
from .pdf_export import export_framework_to_pdf_file
from ..core.mechanical_audit import definitive_document_for_export


class GenerateFrameworkWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, book_id: int, name: str):
        super().__init__()
        self.book_id = book_id
        self.name = name

    def run(self):
        try:
            result = service.framework_generate(
                self.book_id,
                self.name,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class RegenerateFrameworkWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, book_id: int, framework_id: int):
        super().__init__()
        self.book_id = book_id
        self.framework_id = framework_id

    def run(self):
        try:
            result = service.framework_regenerate(
                self.book_id,
                self.framework_id,
                progress_callback=lambda msg: self.progress.emit(msg),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class FrameworkAskWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, book_id: int, framework_id: int, question: str):
        super().__init__()
        self.book_id = book_id
        self.framework_id = framework_id
        self.question = question

    def run(self):
        try:
            result = service.framework_answer_question(
                self.book_id, self.framework_id, self.question
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class FrameworksTab(QWidget):
    def __init__(self, book_manager: BookManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # Same BookManager as ``service`` after ``MainWindow`` calls ``service.bind_book_manager``.
        self.book_manager = book_manager
        self.selected_book_id: Optional[int] = None
        self.selected_framework: Optional[Dict[str, Any]] = None
        self._generate_worker: Optional[GenerateFrameworkWorker] = None
        self._regenerate_worker: Optional[RegenerateFrameworkWorker] = None
        self._ask_worker: Optional[FrameworkAskWorker] = None
        self._init_ui()
        self._load_books()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        configure_tab_scroll_area(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(*TAB_MARGINS)
        content_layout.setSpacing(TAB_SPACING)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(
            create_header_widget(
                self,
                "Frameworks",
                "Generate, view, and reuse structured frameworks from your books.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        self.empty_state = QLabel(
            "Select a book with embeddings to generate or view frameworks."
        )
        self.empty_state.setStyleSheet(MUTED_LABEL_STYLE)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setWordWrap(True)
        content_layout.addWidget(self.empty_state)

        # Book row + framework UI (hidden when no embeddings); never hide the scroll area or header.
        self._framework_body = QWidget(content)
        _fw_body_layout = QVBoxLayout(self._framework_body)
        _fw_body_layout.setContentsMargins(0, 0, 0, 0)
        _fw_body_layout.setSpacing(TAB_SPACING)

        self._book_label, self.book_combo, self.refresh_btn = create_select_book_row(self)
        self.book_combo.currentIndexChanged.connect(self._on_book_selected)
        self.refresh_btn.clicked.connect(self._load_books)
        book_row = QHBoxLayout()
        book_row.addWidget(self._book_label, 0)
        book_row.addWidget(self.book_combo, 0)
        book_row.addStretch(1)
        # Generate + Refresh controls on the same row
        self.generate_btn = QPushButton("Generate Framework")
        self.generate_btn.setStyleSheet(BTN_PRIMARY_SMALL)
        self.generate_btn.clicked.connect(self._on_generate_clicked)
        book_row.addWidget(self.generate_btn)
        book_row.addWidget(self.refresh_btn)

        # Framework name display (auto: Framework (Selected Book)) — tight to Select Book row
        self.framework_name_label = QLabel("Framework name: (no book selected)")
        self.framework_name_label.setStyleSheet(
            "color: #555555; font-size: 11px;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; font-size: 11px;"
        )
        book_block = QWidget()
        book_block_layout = QVBoxLayout(book_block)
        book_block_layout.setContentsMargins(0, 0, 0, 0)
        book_block_layout.setSpacing(6)
        book_block_layout.addLayout(book_row)
        book_block_layout.addWidget(self.framework_name_label)
        _fw_body_layout.addWidget(book_block)

        saved_section, saved_group_layout = create_section_card(self._framework_body, "Saved frameworks")
        saved_group_layout.setSpacing(4)
        self.framework_table = QTableWidget(0, 2)
        self.framework_table.setHorizontalHeaderLabels(["Framework Name", "Generated"])
        self.framework_table.verticalHeader().setVisible(False)
        self.framework_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.framework_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.framework_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        configure_card_style_table(
            self.framework_table,
            min_empty_viewport_px=100,
            enforce_min_body_when_filled=True,
            max_view_height_px=200,
        )
        # Match Library / Recent uploads card table chrome; keep Generated column fixed width.
        _fw_hh = self.framework_table.horizontalHeader()
        if _fw_hh is not None:
            _fw_hh.setStretchLastSection(False)
        self.framework_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.framework_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.framework_table.setColumnWidth(1, 200)
        self.framework_table.itemSelectionChanged.connect(self._on_framework_selection_changed)
        saved_group_layout.addWidget(self.framework_table)
        saved_btn_row = QHBoxLayout()
        saved_btn_row.setContentsMargins(0, 4, 0, 0)
        saved_btn_row.addStretch()
        self.regen_btn = QPushButton("Regenerate Framework")
        self.regen_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self.regen_btn.clicked.connect(self._on_regenerate_clicked)
        self.regen_btn.setEnabled(False)
        saved_btn_row.addWidget(self.regen_btn)
        self.export_docx_btn = QPushButton("Export as DOCX")
        self.export_docx_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self.export_docx_btn.clicked.connect(self._on_export_docx_clicked)
        self.export_docx_btn.setEnabled(False)
        saved_btn_row.addWidget(self.export_docx_btn)
        self.export_pdf_btn = QPushButton("Export as PDF")
        self.export_pdf_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self.export_pdf_btn.clicked.connect(self._on_export_pdf_clicked)
        self.export_pdf_btn.setEnabled(False)
        saved_btn_row.addWidget(self.export_pdf_btn)
        self.delete_framework_btn = QPushButton("Delete Framework")
        self.delete_framework_btn.setStyleSheet(BTN_DANGER_SMALL)
        self.delete_framework_btn.clicked.connect(self._on_delete_framework_clicked)
        self.delete_framework_btn.setEnabled(False)
        saved_btn_row.addWidget(self.delete_framework_btn)
        saved_group_layout.addLayout(saved_btn_row)
        _fw_body_layout.addWidget(saved_section)

        # Framework View: definitive document (markdown → HTML)
        view_section, view_group_layout = create_section_card(self._framework_body, "Framework Content")
        self.content_view = QTextEdit()
        self.content_view.setReadOnly(True)
        self.content_view.setPlaceholderText(
            "Select a framework to view its definitive document (fixed-structure export)."
        )
        self.content_view.setMinimumHeight(400)
        self.content_view.setStyleSheet(FRAMEWORK_CONTENT_VIEW_STYLE)
        view_group_layout.addWidget(self.content_view)
        _fw_body_layout.addWidget(view_section)

        self.process_section = CollapsibleSection("How this framework was generated", self._framework_body)
        self.process_view = QTextEdit()
        self.process_view.setReadOnly(True)
        self.process_view.setMinimumHeight(180)
        self.process_view.setStyleSheet(TEXTEDIT_SMALL_STYLE)
        self.process_section.content_layout.addWidget(self.process_view)
        self._update_generation_process_view()
        _fw_body_layout.addWidget(self.process_section)

        audit_section, audit_group_layout = create_section_card(self._framework_body, "Quality Audit")
        self.audit_view = QTextEdit()
        self.audit_view.setReadOnly(True)
        self.audit_view.setPlaceholderText(
            "Select a framework to see mechanical checks, critical review items, and judgment summary."
        )
        self.audit_view.setMinimumHeight(120)
        self.audit_view.setMaximumHeight(280)
        self.audit_view.setStyleSheet(FRAMEWORK_AUDIT_VIEW_STYLE)
        audit_group_layout.addWidget(self.audit_view)
        _fw_body_layout.addWidget(audit_section)

        ask_section, ask_layout = create_section_card(self._framework_body, "Ask about this framework")
        ask_row = QHBoxLayout()
        self.ask_input = QLineEdit()
        self.ask_input.setStyleSheet(INPUT_LINE)
        self.ask_input.setPlaceholderText("Ask a question about the selected framework...")
        self.ask_input.returnPressed.connect(self._on_ask_clicked)
        self.ask_input.setEnabled(False)
        ask_row.addWidget(self.ask_input)
        self.ask_btn = QPushButton("Ask")
        self.ask_btn.setStyleSheet(BTN_PRIMARY)
        self.ask_btn.clicked.connect(self._on_ask_clicked)
        self.ask_btn.setEnabled(False)
        ask_row.addWidget(self.ask_btn)
        ask_layout.addLayout(ask_row)
        self.ask_history = QTextEdit()
        self.ask_history.setReadOnly(True)
        self.ask_history.setMinimumHeight(280)
        self.ask_history.setPlaceholderText(
            "Your questions and answers will appear here. Type a question above and click Ask to start the conversation."
        )
        self.ask_history.setStyleSheet(TEXTEDIT_READONLY_STYLE)
        self.ask_history.document().setDefaultStyleSheet(FRAMEWORK_ASK_DOC_STYLESHEET)
        ask_layout.addWidget(self.ask_history)
        _fw_body_layout.addWidget(ask_section)

        content_layout.addWidget(self._framework_body)

        scroll.setWidget(content)
        self.scroll_area = scroll
        self._scroll_content_layout = content_layout

        self._footer_bar = QWidget()
        self._footer_bar.setObjectName("tabPageFooter")
        self._footer_layout = QVBoxLayout(self._footer_bar)
        self._footer_layout.setContentsMargins(22, 6, 22, 8)
        self._footer_layout.setSpacing(0)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(MUTED_LABEL_STYLE)
        self.status_label.setWordWrap(True)
        self._footer_layout.addWidget(self.status_label)

        wire_scroll_content_margins(scroll, content_layout, self._footer_layout)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(self._footer_bar, stretch=0)

    def apply_theme(self) -> None:
        # Theme tokens must be read from styles.* here — module-level `from styles import X`
        # stays bound to the string from first import, so INPUT_LINE/BTN_* would stay wrong
        # after the user switches dark/light until app restart.
        from . import styles as st
        from .styles import (
            apply_card_style_table_viewport_style,
            configure_tab_scroll_area,
            refresh_scroll_content_margins,
            refresh_section_cards,
            select_book_row_label_style,
            sync_card_style_table_height,
        )

        self._book_label.setStyleSheet(select_book_row_label_style())
        self.book_combo.setStyleSheet(st.COMBO_STYLE)
        self.refresh_btn.setStyleSheet(st.BTN_SECONDARY_SMALL)
        self.generate_btn.setStyleSheet(st.BTN_PRIMARY_SMALL)
        self.framework_name_label.setStyleSheet(
            "color: #555555; font-size: 11px;"
            if st.CURRENT_THEME == "light"
            else "color: #9ca3af; font-size: 11px;"
        )
        self.regen_btn.setStyleSheet(st.BTN_SECONDARY_SMALL)
        self.export_docx_btn.setStyleSheet(st.BTN_SECONDARY_SMALL)
        self.export_pdf_btn.setStyleSheet(st.BTN_SECONDARY_SMALL)
        self.delete_framework_btn.setStyleSheet(st.BTN_DANGER_SMALL)
        self.content_view.setStyleSheet(FRAMEWORK_CONTENT_VIEW_STYLE)
        self.process_view.setStyleSheet(st.TEXTEDIT_SMALL_STYLE)
        self.process_section.apply_theme()
        self.audit_view.setStyleSheet(FRAMEWORK_AUDIT_VIEW_STYLE)
        self.ask_input.setStyleSheet(st.INPUT_LINE)
        self.ask_btn.setStyleSheet(st.BTN_PRIMARY)
        self.ask_history.setStyleSheet(st.TEXTEDIT_READONLY_STYLE)
        self.ask_history.document().setDefaultStyleSheet(st.FRAMEWORK_ASK_DOC_STYLESHEET)
        self.status_label.setStyleSheet(st.MUTED_LABEL_STYLE)
        self.empty_state.setStyleSheet(st.MUTED_LABEL_STYLE)
        configure_tab_scroll_area(self.scroll_area)
        refresh_scroll_content_margins(
            self.scroll_area, self._scroll_content_layout, self._footer_layout
        )
        refresh_section_cards(self)
        sync_card_style_table_height(self.framework_table)
        apply_card_style_table_viewport_style(self.framework_table)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self._load_books()

    def _load_books(self):
        current_book = self.selected_book_id
        self.book_combo.clear()
        try:
            all_books = service.list_books()
            with_emb = [b for b in all_books if b.get("embeddings_generated", False)]
            if not with_emb:
                self.empty_state.setVisible(True)
                self._set_framework_section_visible(False)
                self.selected_book_id = None
                self.status_label.setText("No books with embeddings available.")
                return
            self.empty_state.setVisible(False)
            self._set_framework_section_visible(True)
            for b in with_emb:
                self.book_combo.addItem(
                    b.get("title", "Untitled"),
                    b["id"],
                )
            idx = 0
            for i in range(self.book_combo.count()):
                if self.book_combo.itemData(i) == current_book:
                    idx = i
                    break
            self.book_combo.setCurrentIndex(idx)
            self._on_book_selected(idx)
            self.status_label.setText(f"{len(with_emb)} book(s) available.")
        except Exception as exc:
            self.status_label.setText(f"Error loading books: {exc}")
        finally:
            refresh_scroll_content_margins(
            self.scroll_area, self._scroll_content_layout, self._footer_layout
        )

    def _set_framework_section_visible(self, visible: bool) -> None:
        """Show/hide book picker + framework workflow. Header and empty-state stay in the scroll area."""
        self._framework_body.setVisible(visible)

    def _on_book_selected(self, index: int):
        if index < 0:
            self.selected_book_id = None
            self._update_book_dependent_state()
            return
        bid = self.book_combo.itemData(index)
        if bid is None:
            self.selected_book_id = None
        else:
            self.selected_book_id = int(bid)
        self._update_book_dependent_state()
        self._load_frameworks()

    def _update_book_dependent_state(self):
        has_book = self.selected_book_id is not None
        self.generate_btn.setEnabled(has_book)
        # Update framework name label based on selected book
        if has_book:
            title = self.book_combo.currentText().strip() or "Untitled"
            self.framework_name_label.setText(f"Framework name: Framework ({title})")
        else:
            self.framework_name_label.setText("Framework name: (no book selected)")
        if not has_book:
            self.selected_framework = None
            self.framework_table.setRowCount(0)
            self.content_view.clear()
            self.audit_view.clear()
            self.ask_history.clear()
            self.regen_btn.setEnabled(False)
            self.delete_framework_btn.setEnabled(False)
            self.ask_btn.setEnabled(False)
            self.ask_input.setEnabled(False)
            sync_card_style_table_height(self.framework_table)
            apply_card_style_table_viewport_style(self.framework_table)
            refresh_scroll_content_margins(
            self.scroll_area, self._scroll_content_layout, self._footer_layout
        )

    def _load_frameworks(self):
        self.framework_table.setRowCount(0)
        self.content_view.clear()
        self.audit_view.clear()
        self.ask_history.clear()
        self.selected_framework = None
        self.regen_btn.setEnabled(False)
        self.delete_framework_btn.setEnabled(False)
        self.ask_btn.setEnabled(False)
        self.ask_input.setEnabled(False)
        try:
            if self.selected_book_id is None:
                return
            fws = service.framework_list(self.selected_book_id)
            for f in fws:
                row = self.framework_table.rowCount()
                self.framework_table.insertRow(row)
                created = (f.get("created_at") or "")[:19]
                name_item = QTableWidgetItem(f.get("name", ""))
                name_item.setData(Qt.ItemDataRole.UserRole, f)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.framework_table.setItem(row, 0, name_item)
                date_item = QTableWidgetItem(created)
                date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.framework_table.setItem(row, 1, date_item)
            if fws:
                self.status_label.setText(f"{len(fws)} framework(s) for this book.")
            else:
                self.status_label.setText("No frameworks yet. Generate one above.")
        except Exception as exc:
            self.status_label.setText(f"Error loading frameworks: {exc}")
        finally:
            sync_card_style_table_height(self.framework_table)
            apply_card_style_table_viewport_style(self.framework_table)
            refresh_scroll_content_margins(
            self.scroll_area, self._scroll_content_layout, self._footer_layout
        )

    def _on_framework_selection_changed(self):
        rows = self.framework_table.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            self.selected_framework = None
            self.content_view.clear()
            self.audit_view.clear()
            self.ask_history.clear()
            self.regen_btn.setEnabled(False)
            self.export_docx_btn.setEnabled(False)
            self.export_pdf_btn.setEnabled(False)
            self.delete_framework_btn.setEnabled(False)
            self.ask_btn.setEnabled(False)
            self.ask_input.setEnabled(False)
            return
        row = rows[0].row()
        name_item = self.framework_table.item(row, 0)
        if not name_item:
            return
        fw = name_item.data(Qt.ItemDataRole.UserRole)
        if not fw:
            return
        self.selected_framework = fw
        full = service.framework_get(self.selected_book_id, fw["id"])
        self.content_view.setHtml(self._format_framework_content(full))
        self._update_audit_view(full)
        self.ask_history.clear()
        self.regen_btn.setEnabled(True)
        self.export_docx_btn.setEnabled(True)
        self.export_pdf_btn.setEnabled(True)
        self.delete_framework_btn.setEnabled(True)
        self.ask_btn.setEnabled(True)
        self.ask_input.setEnabled(True)
        self.status_label.setText(f"Viewing: {fw['name']}")

    def _on_generate_clicked(self):
        if self.selected_book_id is None:
            QMessageBox.information(self, "No book", "Select a book first.")
            return
        # Auto-generate framework name as \"Framework (Book Title)\"
        title = self.book_combo.currentText().strip() or "Untitled"
        name = f"Framework ({title})"
        self.generate_btn.setEnabled(False)
        self.status_label.setText("Generating framework…")
        QApplication.processEvents()
        self._generate_worker = GenerateFrameworkWorker(self.selected_book_id, name)
        self._generate_worker.finished.connect(self._on_generate_finished)
        self._generate_worker.error.connect(self._on_generate_error)
        self._generate_worker.progress.connect(self._on_framework_progress)
        self._generate_worker.start()

    def _on_generate_finished(self, result: dict):
        self.generate_btn.setEnabled(True)
        self.status_label.setText("Framework generated and saved.")
        self._load_frameworks()
        fid = result.get("framework_id")
        for i in range(self.framework_table.rowCount()):
            item = self.framework_table.item(i, 0)
            if item:
                fw = item.data(Qt.ItemDataRole.UserRole)
                if fw and fw.get("id") == fid:
                    self.framework_table.selectRow(i)
                    break
        if fid is not None:
            bid = int(result.get("book_id") or self.selected_book_id or 0)
            self._update_audit_view(service.framework_get(bid, int(fid)))
        else:
            self._update_audit_view(None)
        QMessageBox.information(
            self,
            "Framework Generated",
            f"Saved as \"{result.get('name', '')}\". You can view it and the Quality Audit below.",
        )

    def _on_generate_error(self, err: str):
        self.generate_btn.setEnabled(True)
        self.status_label.setText("Generate failed.")
        QMessageBox.critical(self, "Generate Framework", err)

    def _on_framework_progress(self, msg: str):
        """Update status label when generate/regenerate pipeline reports progress."""
        self.status_label.setText(msg)
        QApplication.processEvents()

    def _on_regenerate_clicked(self):
        if not self.selected_framework:
            return
        rid = self.selected_framework["id"]
        name = self.selected_framework.get("name", "this framework")
        ok = QMessageBox.question(
            self,
            "Regenerate",
            f"Re-run extraction for \"{name}\"? This overwrites the current content.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        self.regen_btn.setEnabled(False)
        self.status_label.setText("Regenerating framework…")
        QApplication.processEvents()
        self._regenerate_worker = RegenerateFrameworkWorker(self.selected_book_id, rid)
        self._regenerate_worker.finished.connect(self._on_regenerate_finished)
        self._regenerate_worker.error.connect(self._on_regenerate_error)
        self._regenerate_worker.progress.connect(self._on_framework_progress)
        self._regenerate_worker.start()

    def _format_audit_html(self, framework: Optional[Dict[str, Any]]) -> str:
        """Format mechanical audit + Logic Auditor from one framework dict."""
        if not framework:
            return '<p style="color:#777; font-style:italic;">No audit data available.</p>'

        audit_result = framework.get("audit_result")
        mechanical_audit = framework.get("mechanical_audit_result")
        has_definitive = bool((framework.get("definitive_document") or "").strip())
        has_mechanical = bool(mechanical_audit and isinstance(mechanical_audit, dict))
        pending_mechanical = has_definitive and mechanical_audit is None
        has_logic = bool(audit_result and isinstance(audit_result, dict))

        if not has_mechanical and not pending_mechanical and not has_logic:
            return '<p style="color:#777; font-style:italic;">No audit data available.</p>'

        parts: List[str] = []

        if has_mechanical:
            passed = mechanical_audit.get("passed", True)
            checked_at = self._html_escape(str(mechanical_audit.get("checked_at") or ""))
            warn_list = mechanical_audit.get("warnings") or []
            if passed:
                parts.append(
                    '<p style="color:#2e7d32; font-weight:bold; margin:0 0 8px 0;">'
                    "✓ Mechanical audit: no blocking failures.</p>"
                )
                if checked_at:
                    parts.append(
                        f'<p style="margin:0 0 10px 0; font-size:11px; color:#666;">{checked_at}</p>'
                    )
                if warn_list:
                    parts.append(
                        '<p style="margin:0 0 4px 0; font-size:12px; color:#856404;">'
                        "Informational (does not block generation or Phase 4):</p>"
                    )
                    parts.append('<ul style="margin:0 0 12px 0; padding-left:20px; color:#555;">')
                    for w in warn_list[:35]:
                        cid = self._html_escape(str(w.get("check_id") or ""))
                        msg = self._html_escape(str(w.get("message") or ""))
                        det = self._html_escape(str(w.get("detail") or ""))
                        line = f"<li style=\"margin-bottom:4px;\"><b>{cid}</b>: {msg}"
                        if det:
                            line += f' <span style="color:#666;">({det})</span>'
                        line += "</li>"
                        parts.append(line)
                    parts.append("</ul>")
            else:
                parts.append(
                    '<p style="margin:0 0 4px 0; font-size:13px; font-weight:bold; color:#c62828;">'
                    "Mechanical audit: issues found — details below (not embedded in the definitive document).</p>"
                )
                if checked_at:
                    parts.append(
                        f'<p style="margin:0 0 6px 0; font-size:11px; color:#666;">{checked_at}</p>'
                    )
                fl = mechanical_audit.get("failures") or []
                parts.append('<ul style="margin:0 0 12px 0; padding-left:20px; color:#333;">')
                for f in fl[:35]:
                    cid = self._html_escape(str(f.get("check_id") or ""))
                    msg = self._html_escape(str(f.get("message") or ""))
                    det = self._html_escape(str(f.get("detail") or ""))
                    line = f"<li style=\"margin-bottom:4px;\"><b>{cid}</b>: {msg}"
                    if det:
                        line += f' <span style="color:#666;">({det})</span>'
                    line += "</li>"
                    parts.append(line)
                parts.append("</ul>")
            parts.append(
                '<p style="margin:0 0 8px 0; font-size:11px; color:#555;">'
                "Critical review items (graph, framework, hybrid) and judgment follow below.</p>"
            )
            parts.append(
                '<hr style="border:none;border-top:1px solid #e0e0e0;margin:0 0 10px 0;" />'
            )
        elif pending_mechanical:
            parts.append(
                '<p style="margin:0 0 8px 0; font-size:12px; color:#856404; background:#fff8e6; '
                'padding:6px 8px; border-radius:4px;">'
                "Mechanical audit not on file for this saved framework — run <b>Regenerate</b> to record it.</p>"
            )
            parts.append(
                '<hr style="border:none;border-top:1px solid #e0e0e0;margin:0 0 10px 0;" />'
            )
        elif has_logic and not has_mechanical and not pending_mechanical:
            parts.append(
                '<p style="margin:0 0 8px 0; font-size:11px; color:#555;">'
                "Critical review items (graph, framework, hybrid) and judgment below.</p>"
            )
            parts.append(
                '<hr style="border:none;border-top:1px solid #e0e0e0;margin:0 0 10px 0;" />'
            )

        if not has_logic:
            parts.append(
                '<p style="color:#777; font-style:italic;">No Logic Auditor data available.</p>'
            )
            return "".join(parts)

        ar = prepare_audit_result_for_ui(audit_result)
        gc = ar.get("graph_critical_issues") or []
        lc = ar.get("logic_critical_issues") or []
        hc = ar.get("hybrid_critical_issues") or []

        def _bullets(title: str, items: List[Any], color: str) -> None:
            if not items:
                return
            parts.append(
                f'<p style="margin:8px 0 6px 0; font-size:13px; font-weight:bold; color:{color};">{title} ({len(items)})</p>'
            )
            parts.append('<ul style="margin:0 0 8px 0; padding-left:20px; color:#333;">')
            for it in items:
                parts.append(f'<li style="margin-bottom:4px;">{self._html_escape(str(it))}</li>')
            parts.append("</ul>")

        any_critical = bool(gc or lc or hc)
        if not any_critical:
            parts.append(
                '<p style="color:#2e7d32; font-weight:bold;">✓ Review: no critical issues in graph, framework logic, or hybrid categories.</p>'
            )
        else:
            _bullets("Graph — critical", gc, "#6a1b9a")
            _bullets("Framework — critical", lc, "#b45309")
            _bullets("Hybrid — critical", hc, "#c62828")

        p4 = ar.get("phase4") if isinstance(ar.get("phase4"), dict) else None
        if isinstance(p4, dict) and p4:
            ci = p4.get("completed_iterations")
            mi = p4.get("max_iterations")
            lj = p4.get("last_judgment") or {}
            wr = lj.get("warrants_reextract")
            parts.append(
                '<p style="margin:12px 0 6px 0; font-size:13px; font-weight:bold; color:#333;">Judgment check</p>'
            )
            summary_bits: List[str] = []
            try:
                ci_i = int(ci) if ci is not None else None
                mi_i = int(mi) if mi is not None else None
            except (TypeError, ValueError):
                ci_i, mi_i = None, None
            if ci_i is not None and mi_i is not None and mi_i > 0:
                summary_bits.append(
                    f"The automated review ran after generation pass {ci_i} of {mi_i}."
                )
            if wr is True:
                summary_bits.append(
                    "It recommended running another full generation pass to close important gaps."
                )
            elif wr is False:
                summary_bits.append("It did not require another generation pass.")
            if summary_bits:
                parts.append(
                    f'<p style="margin:0 0 8px 0; font-size:12px; color:#444; line-height:1.45;">'
                    f'{" ".join(summary_bits)}</p>'
                )
            findings = lj.get("findings") or []
            if isinstance(findings, list) and findings:
                parts.append(
                    '<p style="margin:0 0 4px 0; font-size:11px; color:#666;">Summary points:</p>'
                )
                parts.append('<ul style="margin:0 0 0 0; padding-left:18px; font-size:12px; color:#333;">')
                for f in findings[:12]:
                    parts.append(f'<li style="margin-bottom:4px;">{self._html_escape(str(f)[:500])}</li>')
                parts.append("</ul>")
        return "".join(parts) if parts else '<p style="color:#777;">No issues reported.</p>'

    def _update_audit_view(self, framework: Optional[Dict[str, Any]]) -> None:
        """Update Quality Audit: mechanical (Phase 3) + Logic Auditor."""
        if hasattr(self, "audit_view"):
            self.audit_view.setHtml(self._format_audit_html(framework))

    def _html_escape(self, text: str) -> str:
        """Escape for safe HTML display."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _format_framework_content(self, full: Dict[str, Any]) -> str:
        """Render the definitive document only (mechanical audit is a separate Quality panel)."""
        definitive = definitive_document_for_export(full).strip()
        if not definitive:
            return (
                '<p style="margin:16px 0; padding:12px 14px; background:#fff8e6; border:1px solid #ffe0a3; '
                'border-radius:6px; color:#5d4200; line-height:1.45;">'
                "<b>No definitive document.</b> Generate or regenerate this framework to build the definitive view and export.</p>"
            )
        return self._format_markdown_to_html(definitive)

    def _format_markdown_to_html(self, markdown: str) -> str:
        """Minimal markdown->HTML converter supporting headings, bullets, paragraphs, and markdown tables."""
        lines = (markdown or "").splitlines()
        html_parts: List[str] = []
        in_list = False

        def close_list() -> None:
            nonlocal in_list
            if in_list:
                html_parts.append("</ul>")
                in_list = False

        def bold_to_html(escaped: str) -> str:
            # Convert **text** to <b>text</b>.
            return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)

        def underscore_italic_to_html(escaped: str, *, blue: bool) -> str:
            if blue:
                return re.sub(
                    r"_([^_<\n]+?)_",
                    r'<i style="color:#5c6bc0;">\1</i>',
                    escaped,
                )
            return re.sub(r"_([^_<\n]+?)_", r"<i>\1</i>", escaped)

        def escape_and_bold(raw: str) -> str:
            escaped = self._html_escape(raw)
            escaped = bold_to_html(escaped)
            return underscore_italic_to_html(escaped, blue=False)

        def split_table_row(r: str) -> List[str]:
            r = r.strip()
            if r.startswith("|"):
                r = r[1:]
            if r.endswith("|"):
                r = r[:-1]
            return [c.strip() for c in r.split("|")]

        i = 0
        pending_heading: Optional[str] = None
        fw_block_depth = 0

        def emit_fw_epistemic(ep_lines: List[str]) -> None:
            """Render Source + ES/EC row + tag justifications (definitive markers)."""
            close_list()
            efs = _FW_EPISTEMIC_FONT

            def fmt_line(raw: str) -> str:
                esc = self._html_escape(raw)
                esc = bold_to_html(esc)
                return underscore_italic_to_html(esc, blue=True)

            def ep_sized(html: str) -> str:
                """Wrap so <b>/<i> use the same font size as body (Qt otherwise looks oversized)."""
                return (
                    f'<span class="{_FW_EPISTEMIC_TXT_CLASS}" style="font-size:{efs};line-height:1.38;">'
                    f"{html}</span>"
                )

            html_parts.append(
                f'<div class="fw-epistemic" style="margin:8px 0 10px 14px;padding:4px 0 4px 12px;'
                f'border-left:3px solid #3949ab;font-size:{efs};line-height:1.38;color:#424242;">'
            )
            for raw in ep_lines:
                s = raw.strip()
                if not s:
                    continue
                if "**Tag justifications:**" in s:
                    ix = s.find("**Tag justifications:**")
                    prefix = s[:ix]
                    rest = s[ix + len("**Tag justifications:**") :].lstrip()
                    inner_parts: List[str] = []
                    if prefix.strip():
                        inner_parts.append(fmt_line(prefix))
                    label = '<b style="color:#6a1b9a;">Tag justifications:</b> '
                    inner_parts.append(label + (fmt_line(rest) if rest else ""))
                    inner = "".join(inner_parts)
                    html_parts.append(
                        f'<div class="fw-epistemic-inner" style="margin:4px 0;font-size:{efs};line-height:1.38;">'
                        f"{ep_sized(inner)}</div>"
                    )
                elif s.startswith("**ES:**"):
                    html_parts.append(
                        f'<div class="fw-epistemic-inner" style="margin:4px 0;padding:4px 6px;'
                        f'background:#ede7f6;border-radius:4px;color:#4a148c;font-size:{efs};line-height:1.38;">'
                        + ep_sized(fmt_line(s))
                        + "</div>"
                    )
                elif s.startswith("**_Source") or s.startswith("**Source"):
                    lab, bod = _split_source_epistemic_label_body(s)
                    if lab and ":" in lab:
                        label_html = (
                            f'<b style="color:#1976d2;">{self._html_escape(lab)}</b>'
                        )
                        body_html = (
                            escape_and_bold(bod).replace("\n", "<br>") if bod else ""
                        )
                        inner_src = label_html + (" " + body_html if body_html else "")
                    else:
                        inner_src = fmt_line(s)
                    html_parts.append(
                        f'<div class="fw-epistemic-inner" style="margin:4px 0;padding:4px 6px;'
                        f'background:#f5f5f5;border-radius:4px;color:#1a1a1a;font-size:{efs};line-height:1.38;">'
                        + ep_sized(inner_src)
                        + "</div>"
                    )
                else:
                    html_parts.append(
                        f'<div class="fw-epistemic-inner" style="margin:3px 0;font-size:{efs};line-height:1.38;">'
                        f"{ep_sized(fmt_line(s))}</div>"
                    )
            html_parts.append("</div>")

        while i < len(lines):
            raw_line = lines[i]
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped:
                close_list()
                i += 1
                continue

            # Horizontal rule (e.g. after Phase 3 mechanical banner)
            if stripped == "---":
                close_list()
                html_parts.append(
                    '<hr style="border:none;border-top:1px solid #ccc;margin:12px 0;" />'
                )
                i += 1
                continue

            # Blockquotes (mechanical audit banner uses leading ">")
            if stripped.startswith(">"):
                close_list()
                quote_lines: List[str] = []
                j = i
                while j < len(lines):
                    s = lines[j].strip()
                    if s.startswith(">"):
                        quote_lines.append(s[1:].lstrip())
                        j += 1
                    elif not s:
                        j += 1
                        break
                    else:
                        break
                inner_parts: List[str] = []
                for ql in quote_lines:
                    if not ql:
                        continue
                    inner_parts.append(escape_and_bold(ql))
                inner = "<br>".join(inner_parts) if inner_parts else ""
                html_parts.append(
                    '<div style="margin:8px 0 12px 0;padding:10px 12px;border-left:4px solid #c62828;'
                    'background:#fff8f8;font-size:12px;color:#333;line-height:1.45;">'
                    + inner
                    + "</div>"
                )
                i = j
                continue

            # Definitive document structure markers (paired with langchain_framework render)
            m_block = RE_FW_BLOCK_OPEN.match(stripped)
            if m_block:
                close_list()
                fw_block_depth += 1
                html_parts.append(f'<div style="{_FW_BLOCK_WRAP_STYLE}">')
                i += 1
                continue
            if stripped == FW_BLOCK_END:
                close_list()
                if fw_block_depth > 0:
                    html_parts.append("</div>")
                    fw_block_depth -= 1
                i += 1
                continue
            mh = RE_FW_HEADING.match(stripped)
            if mh:
                pending_heading = mh.group(1).lower()
                i += 1
                continue
            if stripped == FW_EPISTEMIC_BEGIN:
                close_list()
                j = i + 1
                acc: List[str] = []
                while j < len(lines):
                    sl = lines[j].strip()
                    if sl == FW_EPISTEMIC_END:
                        j += 1
                        break
                    acc.append(lines[j])
                    j += 1
                emit_fw_epistemic(acc)
                i = j
                continue

            # Subsection title (Term / Step N / …) immediately after [[FW:HEADING:…]]
            if pending_heading is not None and stripped.startswith("**"):
                close_list()
                span_style = _FW_SUBSECTION_SPAN_BY_KIND.get(
                    pending_heading, _FW_SUBSECTION_SPAN_BY_KIND["step"]
                )
                safe = escape_and_bold(stripped).replace("\n", "<br>")
                html_parts.append(
                    f'<p class="fw-subhead-kind" style="{_FW_SUBSECTION_P}">'
                    f'<span style="{span_style}">{safe}</span></p>'
                )
                pending_heading = None
                i += 1
                continue

            # Markdown table block: header row + separator row + data rows.
            if stripped.startswith("|") and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("|") and "---" in next_line:
                    table_lines: List[str] = []
                    j = i
                    while j < len(lines) and lines[j].strip().startswith("|"):
                        table_lines.append(lines[j].strip())
                        j += 1
                    close_list()

                    header_cells = split_table_row(table_lines[0])
                    data_rows = table_lines[2:]  # skip separator row
                    num_cols = len(header_cells)

                    def _row_cell_count(row_line: str) -> int:
                        return len(split_table_row(row_line))

                    # Two-column tables: every row is label | value (no <thead> — avoids value cell looking like a header).
                    two_col_ok = num_cols == 2 and all(
                        _row_cell_count(dr) == 2 for dr in data_rows if dr.strip()
                    )

                    html_parts.append(
                        '<table style="border-collapse:collapse; width:100%; margin:6px 0 10px 0;">'
                    )

                    if two_col_ok:
                        all_row_lines = [table_lines[0]] + data_rows
                        html_parts.append("<tbody>")
                        for row_line in all_row_lines:
                            if not row_line.strip():
                                continue
                            cells = split_table_row(row_line)
                            c0, c1 = cells[0], cells[1]
                            html_parts.append("<tr>")
                            html_parts.append(
                                '<td style="' + _FW_TABLE_LABEL_COL + '">' + escape_and_bold(c0) + "</td>"
                            )
                            html_parts.append(
                                '<td style="' + _FW_TABLE_VALUE_COL + '">'
                                + self._html_escape(c1).replace("\n", "<br>")
                                + "</td>"
                            )
                            html_parts.append("</tr>")
                        html_parts.append("</tbody>")
                    else:
                        html_parts.append("<thead><tr>")
                        for hc in header_cells:
                            html_parts.append(
                                '<th style="border:1px solid #bdbdbd; padding:6px 8px; font-size:12px; '
                                'font-weight:700; text-align:left; background:#e8e8e8; color:#222222;">'
                                + escape_and_bold(hc)
                                + "</th>"
                            )
                        html_parts.append("</tr></thead><tbody>")

                        for dr in data_rows:
                            html_parts.append("<tr>")
                            for cell in split_table_row(dr):
                                html_parts.append(
                                    '<td style="border:1px solid #bdbdbd; padding:6px 8px; font-size:12px; '
                                    'vertical-align:top; font-weight:400; text-align:left; background:#ffffff;">'
                                    + escape_and_bold(cell)
                                    + "</td>"
                                )
                            html_parts.append("</tr>")

                        html_parts.append("</tbody>")
                    html_parts.append("</table>")
                    i = j
                    continue

            # Headings
            if stripped.startswith("## "):
                close_list()
                html_parts.append(
                    '<h2 class="fw-section-main" style="'
                    + _FW_HEADING_STYLE
                    + '">'
                    + escape_and_bold(stripped[3:].strip())
                    + "</h2>"
                )
                i += 1
                continue
            if stripped.startswith("### "):
                close_list()
                # Match definition-style emphasis: same body size as "## …" section content, label bold only.
                sub_esc = self._html_escape(stripped[4:].strip()).replace("\n", "<br>")
                sub_esc = bold_to_html(sub_esc)
                sub_esc = underscore_italic_to_html(sub_esc, blue=False)
                html_parts.append(
                    '<p class="fw-subhead-3" style="'
                    + _FW_BODY_STYLE
                    + '"><b>'
                    + sub_esc
                    + "</b></p>"
                )
                i += 1
                continue

            # Bullets
            if stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_parts.append(
                        '<ul class="fw-list" style="' + _FW_UL_STYLE + '">'
                    )
                    in_list = True
                bullet_text = stripped[2:].strip()
                html_parts.append(
                    '<li class="fw-li" style="'
                    + _FW_LI_STYLE
                    + '">'
                    + escape_and_bold(bullet_text).replace("\n", "<br>")
                    + "</li>"
                )
                i += 1
                continue

            # Regular paragraph
            close_list()
            safe = escape_and_bold(stripped).replace("\n", "<br>")
            html_parts.append(
                '<p class="fw-body" style="' + _FW_BODY_STYLE + '">' + safe + "</p>"
            )
            i += 1

        close_list()
        return "".join(html_parts) or "<p></p>"

    def _on_regenerate_finished(self, result: dict):
        self.regen_btn.setEnabled(True)
        self.status_label.setText("Framework regenerated.")
        bid = int(result.get("book_id") or self.selected_book_id or 0)
        full = service.framework_get(bid, int(result["framework_id"]))
        self.content_view.setHtml(self._format_framework_content(full))
        self._update_audit_view(full)
        self.ask_history.clear()
        QMessageBox.information(self, "Regenerate", "Framework updated successfully.")

    def _on_export_docx_clicked(self):
        if not self.selected_framework:
            QMessageBox.information(self, "No framework", "Select a framework to export.")
            return
        fw_full = service.framework_get(
            self.selected_book_id, self.selected_framework["id"]
        )
        name = (fw_full.get("name") or "Framework").strip() or "Framework"
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name)
        default_path = f"{safe_name}.docx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Framework as DOCX",
            default_path,
            "Word Document (*.docx)",
        )
        if not path:
            return
        try:
            export_framework_to_docx(fw_full, path)
            QMessageBox.information(self, "Export as DOCX", f"Framework exported to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export as DOCX", f"Failed to export framework:\n{exc}")

    def _on_export_pdf_clicked(self):
        if not self.selected_framework:
            QMessageBox.information(self, "No framework", "Select a framework to export.")
            return
        fw_full = service.framework_get(
            self.selected_book_id, self.selected_framework["id"]
        )
        name = (fw_full.get("name") or "Framework").strip() or "Framework"
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in name)
        default_path = f"{safe_name}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Framework as PDF",
            default_path,
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        try:
            body_html = self._format_framework_content(fw_full)
            export_framework_to_pdf_file(name, body_html, path)
            QMessageBox.information(self, "Export as PDF", f"Framework exported to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export as PDF", f"Failed to export framework:\n{exc}")

    def _on_regenerate_error(self, err: str):
        self.regen_btn.setEnabled(True)
        self.status_label.setText("Regenerate failed.")
        QMessageBox.critical(self, "Regenerate Framework", err)

    def _on_delete_framework_clicked(self):
        if not self.selected_framework:
            QMessageBox.information(self, "No selection", "Select a framework to delete.")
            return
        fw = self.selected_framework
        name = fw.get("name", "this framework")
        ok = QMessageBox.question(
            self,
            "Delete Framework",
            f"Delete framework \"{name}\"? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            service.framework_delete(self.selected_book_id, fw["id"])
            self.status_label.setText("Framework deleted.")
            self._load_frameworks()
        except Exception as exc:
            QMessageBox.critical(self, "Delete Framework", str(exc))
            self.status_label.setText("Delete failed.")

    def _on_ask_clicked(self):
        if not self.selected_framework or self.selected_book_id is None:
            return
        q = self.ask_input.text().strip()
        if not q:
            return
        self._add_ask_user(q)
        self.ask_input.clear()
        self.ask_input.setEnabled(False)
        self.ask_btn.setEnabled(False)
        self.status_label.setText("Answering...")
        QApplication.processEvents()
        self._ask_worker = FrameworkAskWorker(
            self.selected_book_id,
            self.selected_framework["id"],
            q,
        )
        self._ask_worker.finished.connect(self._on_ask_finished)
        self._ask_worker.error.connect(self._on_ask_error)
        self._ask_worker.start()

    def _add_ask_user(self, text: str):
        safe = html.escape(text) if text else ""
        html_block = f"<b>You:</b> {safe}<br>"
        self.ask_history.append(html_block)
        log.info("[FrameworkAsk] append user, blocks=%d", self.ask_history.document().blockCount())

    def _add_ask_assistant(self, text: str, used_chunks: Optional[list] = None, is_error: bool = False, is_not_supported: bool = False):
        parts = []
        if is_error:
            safe = html.escape(text) if text else ""
            parts.append(f'<span style="color: #b00020;"><b>Error:</b> {safe}</span>')
        elif is_not_supported:
            safe = html.escape(text) if text else ""
            parts.append(f'<span style="color: #b00020;"><b>Assistant:</b> {safe}</span>')
        else:
            if not text or not str(text).strip():
                text = "The model returned an empty response. Please try rephrasing your question."
            safe = html.escape(str(text))
            formatted = safe.replace("\n", "<br>")
            parts.append(f"<b>Assistant:</b><br>{formatted}")
            if used_chunks:
                pages = sorted({c.get("page_number") for c in used_chunks})
                parts.append(f'<span style="color: #555555; font-size: 11px;">Sources: Pages {", ".join(map(str, pages))}</span>')
        parts.append(_ASK_SEP)
        html_block = "".join(parts)
        self.ask_history.append(html_block)
        log.info("[FrameworkAsk] append assistant (single block), blocks=%d", self.ask_history.document().blockCount())

    def _update_generation_process_view(self) -> None:
        content = (
            "<ol style='margin:0; padding-left:20px; font-size: 12px; line-height: 1.4;'>"
            "<li style='margin-bottom: 2px;'><b>Retrieval.</b> Fetch relevant book excerpts for definitions, principles, steps, warnings (multi-bucket retrieval).</li>"
            "<li style='margin-bottom: 2px;'><b>Extraction.</b> Generate structured node tree from excerpts only — no outside knowledge (extraction agent).</li>"
            "<li style='margin-bottom: 2px;'><b>Context excerpts.</b> Validate node types; attach raw book excerpts per node (±500-word window, light normalization; no context-refinement LLM).</li>"
            "<li style='margin-bottom: 2px;'><b>Mindmap.</b> Build relationships between nodes (edge agent + dependency rules).</li>"
            "<li style='margin-bottom: 2px;'><b>Epistemic pass.</b> Label claims as fact, interpretation, or assumption.</li>"
            "<li style='margin-bottom: 2px;'><b>Logic Audit.</b> Flag contradictions, gaps, and assumptions.</li>"
            "<li style='margin-bottom: 2px;'><b>Meta &amp; scope.</b> Infer purpose/assumptions (internal) and extract claimed vs evidenced scope for the definitive Overview.</li>"
            "<li style='margin-bottom: 2px;'><b>Governor.</b> Surface audit result for the Quality Audit section.</li>"
            "<li style='margin-bottom: 2px;'><b>Definitive document.</b> Render fixed-structure markdown from nodes and edges; run mechanical checks.</li>"
            "</ol>"
        )
        self.process_view.setHtml(content)

    def _on_ask_finished(self, result: dict):
        self.ask_input.setEnabled(True)
        self.ask_btn.setEnabled(True)
        self.status_label.setText("")
        status = result.get("status", "ok")
        answer = result.get("answer", "")
        used = result.get("used_chunks", [])
        if status == "not_supported":
            self._add_ask_assistant("Not supported by the source.", is_not_supported=True)
        else:
            self._add_ask_assistant(answer, used)
        self.ask_input.setFocus()

    def _on_ask_error(self, err: str):
        self.ask_input.setEnabled(True)
        self.ask_btn.setEnabled(True)
        self.status_label.setText("Ask failed.")
        self._add_ask_assistant(err, is_error=True)
        self.ask_input.setFocus()
