import os
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QFrame,
    QSizePolicy,
    QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer

from ..core.book_manager import BookManager
from .styles import (
    apply_recent_uploads_table_viewport_style,
    create_header_widget,
    create_section_card,
    configure_recent_uploads_table,
    configure_tab_scroll_area,
    drop_area_drag_style,
    drop_area_normal_style,
    DROP_AREA_MIN_HEIGHT_PX,
    refresh_scroll_content_margins,
    refresh_section_cards,
    SECTION_TITLE_STYLE,
    sync_recent_uploads_table_height,
    wire_scroll_content_margins,
    TAB_MARGINS,
    TAB_SPACING,
    BTN_SECONDARY,
    BTN_PRIMARY_SMALL,
    CURRENT_THEME,
)
from .workers import UploadBooksWorker
from .card_table_frame import CardTableFrame


class DropArea(QFrame):
    def __init__(self, on_files_dropped, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._on_files_dropped = on_files_dropped
        self.setObjectName("drop_area")
        self._normal_style = drop_area_normal_style()
        self._drag_style = drop_area_drag_style()
        self.setStyleSheet(self._normal_style)
        self.setAcceptDrops(True)

    def apply_theme(self) -> None:
        self._normal_style = drop_area_normal_style()
        self._drag_style = drop_area_drag_style()
        self.setStyleSheet(self._normal_style)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.toLocalFile().lower().endswith(".pdf") for url in urls):
                self.setStyleSheet(self._drag_style)
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(".pdf")
        ]
        self._on_files_dropped(paths)
        self.setStyleSheet(self._normal_style)
        event.acceptProposedAction()


class UploadTab(QWidget):
    def __init__(self, book_manager: BookManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.book_manager = book_manager
        self.selected_files: List[str] = []
        self._upload_worker: Optional[UploadBooksWorker] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        configure_tab_scroll_area(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(*TAB_MARGINS)
        content_layout.setSpacing(16)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(
            create_header_widget(
                self,
                "Upload Book",
                "Upload one or more PDF books. Each is parsed page by page, chunked, and stored as an isolated knowledge base.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        upload_section, upload_inner = create_section_card(content, "Upload and Process Books")
        upload_inner.setSpacing(4)

        drop_area = DropArea(self._on_files_dropped)
        self._drop_area = drop_area
        drop_area.setMinimumHeight(DROP_AREA_MIN_HEIGHT_PX)
        drop_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        drop_area_layout = QVBoxLayout(drop_area)
        drop_area_layout.setContentsMargins(14, 14, 14, 14)
        drop_area_layout.setSpacing(6)
        drop_area_layout.addStretch()

        self.browse_button = QPushButton("Browse PDF...")
        self.browse_button.setStyleSheet(BTN_SECONDARY)
        self.browse_button.clicked.connect(self._on_browse_clicked)
        drop_area_layout.addWidget(self.browse_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self._drop_hint_label = QLabel("Drag & drop or browse books")
        self._drop_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drop_hint_label.setStyleSheet(
            "color: #666666; background-color: transparent; border: none;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; background-color: transparent; border: none;"
        )
        drop_area_layout.addWidget(self._drop_hint_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.selected_files_label = QLabel("No files selected")
        self.selected_files_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.selected_files_label.setStyleSheet(
            "color: #777777; background-color: transparent; border: none;"
            if CURRENT_THEME == "light"
            else "color: #8b949e; background-color: transparent; border: none;"
        )
        self.selected_files_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_files_label.setMaximumWidth(520)
        drop_area_layout.addWidget(self.selected_files_label, alignment=Qt.AlignmentFlag.AlignCenter)
        drop_area_layout.addStretch()
        upload_inner.addWidget(drop_area, 1)
        upload_row = QHBoxLayout()
        upload_row.setContentsMargins(0, 4, 0, 0)
        upload_row.addStretch()
        self.upload_button = QPushButton("Upload and Process")
        self.upload_button.setEnabled(False)
        self.upload_button.setStyleSheet(BTN_PRIMARY_SMALL)
        self.upload_button.clicked.connect(self._on_upload_clicked)
        upload_row.addWidget(self.upload_button)
        upload_row.addStretch()
        upload_inner.addLayout(upload_row)
        self.status_label = QLabel("")
        self.status_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.status_label.setStyleSheet(
            "color: #555555; background-color: transparent;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; background-color: transparent;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setVisible(False)
        upload_inner.addWidget(self.status_label)
        self.error_label = QLabel("")
        self.error_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.error_label.setStyleSheet("color: #b00020; background-color: transparent;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setVisible(False)
        upload_inner.addWidget(self.error_label)
        content_layout.addWidget(upload_section)

        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(["No", "Title", "Filename", "Pages", "Chunks"])
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.result_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        configure_recent_uploads_table(self.result_table)
        header = self.result_table.horizontalHeader()
        # configure_card_style_table sets stretchLastSection(True) → last column (Chunks) swallowed width; turn off.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Interactive + default width: ResizeToContents made Filename too narrow for short names.
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.result_table.setColumnWidth(0, 48)
        self.result_table.setColumnWidth(1, 250)
        self.result_table.setColumnWidth(2, 260)
        self.result_table.setColumnWidth(3, 72)
        self.result_table.setColumnWidth(4, 72)

        recent_block = QWidget()
        recent_col = QVBoxLayout(recent_block)
        recent_col.setContentsMargins(0, 0, 0, 0)
        recent_col.setSpacing(6)
        recent_title = QLabel("Recent uploads")
        recent_title.setObjectName("sectionCardTitle")
        recent_title.setStyleSheet(SECTION_TITLE_STYLE)
        recent_col.addWidget(recent_title)
        self._recent_uploads_frame = CardTableFrame(
            self.result_table,
            "No uploads yet.\nUpload a PDF above to see it listed here.",
        )
        recent_col.addWidget(self._recent_uploads_frame)
        content_layout.addWidget(recent_block)

        scroll.setWidget(content)
        self._scroll_area = scroll
        self._scroll_content_layout = content_layout
        wire_scroll_content_margins(scroll, content_layout)
        layout.addWidget(scroll, stretch=1)

    def apply_theme(self) -> None:
        from .styles import (
            configure_tab_scroll_area,
            refresh_scroll_content_margins,
            sync_recent_uploads_table_height,
        )

        self.browse_button.setStyleSheet(BTN_SECONDARY)
        self.upload_button.setStyleSheet(BTN_PRIMARY_SMALL)
        self._drop_area.apply_theme()
        muted = (
            "color: #666666; background-color: transparent; border: none;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; background-color: transparent; border: none;"
        )
        files_muted = (
            "color: #777777; background-color: transparent; border: none;"
            if CURRENT_THEME == "light"
            else "color: #8b949e; background-color: transparent; border: none;"
        )
        stat_muted = (
            "color: #555555; background-color: transparent;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; background-color: transparent;"
        )
        self._drop_hint_label.setStyleSheet(muted)
        self.selected_files_label.setStyleSheet(files_muted)
        self.status_label.setStyleSheet(stat_muted)
        self.error_label.setStyleSheet("color: #b00020; background-color: transparent;")
        configure_tab_scroll_area(self._scroll_area)
        refresh_scroll_content_margins(self._scroll_area, self._scroll_content_layout)
        refresh_section_cards(self)
        self._recent_uploads_frame.apply_empty_style()
        sync_recent_uploads_table_height(self.result_table)
        apply_recent_uploads_table_viewport_style(self.result_table)

    def _on_browse_clicked(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF books", "", "PDF Files (*.pdf)"
        )
        if not paths:
            return

        self._set_selected_files(paths)

    def _on_files_dropped(self, paths: List[str]):
        if not paths:
            self.error_label.setText("Please drop PDF files only.")
            self.error_label.setVisible(True)
            self.status_label.setVisible(False)
            return
        self._set_selected_files(paths)

    def _set_selected_files(self, paths: List[str]):
        self.selected_files = paths
        n = len(paths)
        self.selected_files_label.setText(f"{n} file(s) selected")
        self.selected_files_label.setToolTip("\n".join(paths))
        self.status_label.setText("")
        self.error_label.setText("")
        self.status_label.setVisible(False)
        self.error_label.setVisible(False)
        self.upload_button.setEnabled(True)

    def _on_upload_clicked(self):
        if not self.selected_files:
            self.error_label.setText("Please select one or more PDF files first.")
            return
        if self._upload_worker and self._upload_worker.isRunning():
            return

        self.upload_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        n = len(self.selected_files)
        self.status_label.setText(f"Processing {n} book(s), please wait..." if n > 1 else "Processing book, please wait...")
        self.status_label.setVisible(True)
        self.error_label.setText("")
        self.error_label.setVisible(False)

        self._upload_worker = UploadBooksWorker(self.book_manager, self.selected_files)
        self._upload_worker.finished.connect(self._on_upload_finished)
        self._upload_worker.error.connect(self._on_upload_error)
        self._upload_worker.start()

    def _on_upload_finished(self, result: dict):
        results = result.get("results", [])
        errors = result.get("errors", [])

        # Append each batch — do not clear; multiple uploads in one session stack as rows.
        for r in results:
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.result_table.setItem(row, 1, QTableWidgetItem(r.get("title", "")))
            self.result_table.setItem(row, 2, QTableWidgetItem(r.get("filename", "")))
            self.result_table.setItem(row, 3, QTableWidgetItem(str(r.get("total_pages", ""))))
            self.result_table.setItem(row, 4, QTableWidgetItem(str(r.get("chunk_count", ""))))

        n, m = len(results), len(errors)
        if m == 0:
            self.status_label.setText(f"{n} book(s) uploaded successfully.")
            self.error_label.setText("")
            self.status_label.setVisible(True)
            self.error_label.setVisible(False)
        else:
            self.status_label.setText(f"{n} succeeded, {m} failed.")
            parts = [os.path.basename(e["path"]) + ": " + e["message"] for e in errors]
            self.error_label.setText("Failed: " + "; ".join(parts[:3]) + ("..." if len(parts) > 3 else ""))
            self.status_label.setVisible(True)
            self.error_label.setVisible(True)

        self.selected_files = []
        self.selected_files_label.setText("No files selected")
        self.selected_files_label.setToolTip("")
        self.upload_button.setEnabled(False)
        self.browse_button.setEnabled(True)
        sync_recent_uploads_table_height(self.result_table)
        apply_recent_uploads_table_viewport_style(self.result_table)
        QTimer.singleShot(0, self._recent_uploads_frame.refresh_empty_overlay)
        refresh_scroll_content_margins(self._scroll_area, self._scroll_content_layout)

    def _on_upload_error(self, msg: str):
        self.error_label.setText(msg)
        self.error_label.setVisible(True)
        self.status_label.setText("Upload failed.")
        self.status_label.setVisible(True)
        self.selected_files = []
        self.selected_files_label.setText("No files selected")
        self.selected_files_label.setToolTip("")
        self.upload_button.setEnabled(False)
        self.browse_button.setEnabled(True)
