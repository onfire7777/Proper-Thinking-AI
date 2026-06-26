from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QScrollArea,
    QHeaderView,
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QObject

from ..core.book_manager import BookManager
from .styles import (
    create_header_widget,
    configure_card_style_table,
    configure_tab_scroll_area,
    refresh_section_cards,
    apply_card_style_table_viewport_style,
    sync_card_style_table_height,
    SCROLL_CONTENT_MARGINS_NO_VSCROLL,
    SCROLL_CONTENT_MARGINS_VSCROLL,
    TAB_SPACING,
    BTN_PRIMARY,
    BTN_SECONDARY,
    BTN_SECONDARY_SMALL,
    BTN_DANGER,
    CURRENT_THEME,
    SECTION_TITLE_STYLE,
)
from .card_table_frame import CardTableFrame
from .workers import GenerateEmbeddingsWorker


class _LibraryScrollMarginFilter(QObject):
    """Viewport resize → sync scroll + footer margins (footer pinned below scroll)."""

    def __init__(self, tab: "LibraryTab"):
        super().__init__(tab._scroll_area)
        self._tab = tab

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.Resize:
            self._tab._refresh_library_scroll_margins()
        return False


class LibraryTab(QWidget):
    def __init__(self, book_manager: BookManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.book_manager = book_manager
        self._embed_worker: Optional[GenerateEmbeddingsWorker] = None
        self._init_ui()
        self._load_books()

    def refresh_books(self):
        """Reload book list from database (call when tab becomes visible or after upload)."""
        self._load_books()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        configure_tab_scroll_area(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        # Margins set by _refresh_library_scroll_margins (bottom stays 0; footer has outer bottom).
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(TAB_SPACING)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(
            create_header_widget(
                self,
                "Library",
                "View and manage uploaded books. Generate embeddings, view info, or delete.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        books_row = QHBoxLayout()
        manage_title = QLabel("Manage Books")
        manage_title.setObjectName("sectionCardTitle")
        manage_title.setStyleSheet(SECTION_TITLE_STYLE)
        books_row.addWidget(manage_title)
        books_row.addStretch()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet(BTN_SECONDARY_SMALL)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        books_row.addWidget(self.refresh_button)
        content_layout.addLayout(books_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["No", "Title", "Pages", "Chunks", "Embedded", "Upload Date"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setVisible(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table._pta_no_internal_vscroll = True
        configure_card_style_table(self.table)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()
        # configure_card_style_table sets stretchLastSection(True) → Upload Date column stretched; Title should grow.
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 48)
        self._books_table_frame = CardTableFrame(
            self.table,
            "No books yet.\nUpload PDFs from the Upload tab to see them listed here.",
        )
        content_layout.addWidget(self._books_table_frame, 0)

        scroll.setWidget(content)
        self._scroll_area = scroll
        self._scroll_content_layout = content_layout

        # Pinned to bottom of the tab viewport (not directly under the table in the scroll area).
        footer = QWidget()
        bottom_bar = QHBoxLayout(footer)
        self._footer_layout = bottom_bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #666666; font-size: 14px; font-weight: 500;"
        )
        bottom_bar.addWidget(self.status_label)
        bottom_bar.addStretch()
        self.info_button = QPushButton("View Info")
        self.info_button.setStyleSheet(BTN_SECONDARY)
        self.info_button.clicked.connect(self._on_view_info_clicked)
        bottom_bar.addWidget(self.info_button)
        self.delete_button = QPushButton("Delete Book")
        self.delete_button.setStyleSheet(BTN_DANGER)
        self.delete_button.clicked.connect(self._on_delete_book_clicked)
        bottom_bar.addWidget(self.delete_button)
        self.embed_button = QPushButton("Generate Embeddings")
        self.embed_button.setStyleSheet(BTN_PRIMARY)
        self.embed_button.clicked.connect(self._on_generate_embeddings_clicked)
        bottom_bar.addWidget(self.embed_button)
        self._wire_library_scroll_margins()
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(footer, stretch=0)

    def _refresh_library_scroll_margins(self) -> None:
        vsb = self._scroll_area.verticalScrollBar()
        m = (
            SCROLL_CONTENT_MARGINS_VSCROLL
            if vsb.maximum() > 0
            else SCROLL_CONTENT_MARGINS_NO_VSCROLL
        )
        self._scroll_content_layout.setContentsMargins(m[0], m[1], m[2], 0)
        self._footer_layout.setContentsMargins(m[0], TAB_SPACING, m[2], m[3])

    def _wire_library_scroll_margins(self) -> None:
        self._refresh_library_scroll_margins()
        self._scroll_area.verticalScrollBar().rangeChanged.connect(
            lambda *_: self._refresh_library_scroll_margins()
        )
        filt = _LibraryScrollMarginFilter(self)
        self._scroll_area.viewport().installEventFilter(filt)
        self._scroll_area._pta_scroll_margin_filter = filt  # noqa: SLF001 — keep QObject alive
        QTimer.singleShot(0, self._refresh_library_scroll_margins)
        QTimer.singleShot(80, self._refresh_library_scroll_margins)

    def apply_theme(self) -> None:
        from .styles import configure_tab_scroll_area

        self.refresh_button.setStyleSheet(BTN_SECONDARY_SMALL)
        self.info_button.setStyleSheet(BTN_SECONDARY)
        self.delete_button.setStyleSheet(BTN_DANGER)
        self.embed_button.setStyleSheet(BTN_PRIMARY)
        st = (
            "color: #666666; font-size: 14px; font-weight: 500;"
            if CURRENT_THEME == "light"
            else "color: #9ca3af; font-size: 14px; font-weight: 500;"
        )
        self.status_label.setStyleSheet(st)
        configure_tab_scroll_area(self._scroll_area)
        self._refresh_library_scroll_margins()
        refresh_section_cards(self)
        self._books_table_frame.apply_empty_style()
        sync_card_style_table_height(self.table)
        apply_card_style_table_viewport_style(self.table)

    # Load books from database into the table
    def _load_books(self):
        self.table.setRowCount(0)
        try:
            books = self.book_manager.list_books()
            books.sort(key=lambda x: x.get('id', 0))
        except Exception as exc:
            self.status_label.setText(str(exc))
            sync_card_style_table_height(self.table)
            apply_card_style_table_viewport_style(self.table)
            QTimer.singleShot(0, self._books_table_frame.refresh_empty_overlay)
            self._refresh_library_scroll_margins()
            return

        for book in books:
            row = self.table.rowCount()
            self.table.insertRow(row)
            no_item = QTableWidgetItem(str(row + 1))
            no_item.setData(Qt.ItemDataRole.UserRole, book.get("id"))
            self.table.setItem(row, 0, no_item)
            
            title_item = QTableWidgetItem(book.get("title", ""))
            self.table.setItem(row, 1, title_item)
            
            pages_item = QTableWidgetItem(str(book.get("total_pages", "")))
            self.table.setItem(row, 2, pages_item)
            
            chunks_item = QTableWidgetItem(str(book.get("chunk_count", "")))
            self.table.setItem(row, 3, chunks_item)
            
            embedded_flag = "Yes" if book.get("embeddings_generated") else "No"
            embedded_item = QTableWidgetItem(embedded_flag)
            self.table.setItem(row, 4, embedded_item)
            
            upload_date = book.get("upload_date", "")
            upload_item = QTableWidgetItem(upload_date[:19] if upload_date else "")
            self.table.setItem(row, 5, upload_item)
        
        if books:
            self.status_label.setText(f"{len(books)} book(s) loaded.")
        else:
            self.status_label.setText("No books uploaded yet.")
        sync_card_style_table_height(self.table)
        apply_card_style_table_viewport_style(self.table)
        QTimer.singleShot(0, self._books_table_frame.refresh_empty_overlay)
        self._refresh_library_scroll_margins()

    # Handle refresh button click
    def _on_refresh_clicked(self):
        self._load_books()
    
    # Get currently selected book ID from the table
    def _get_selected_book_id(self) -> Optional[int]:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return None
        book_id = item.data(Qt.ItemDataRole.UserRole)
        return int(book_id) if book_id is not None else None
    
    # Handle view info button click
    def _on_view_info_clicked(self):
        book_id = self._get_selected_book_id()
        if book_id is None:
            QMessageBox.information(self, "No selection", "Please select a book first.")
            return
        try:
            info = self.book_manager.get_book_info(book_id)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        
        details = [
            f"ID: {info.get('id')}",
            f"Title: {info.get('title', '')}",
            f"Filename: {info.get('filename', '')}",
            f"Total Pages: {info.get('total_pages', '')}",
            f"Chunks: {info.get('chunk_count', '')}",
            f"Embeddings Generated: {'Yes' if info.get('embeddings_generated') else 'No'}",
            f"Upload Date: {info.get('upload_date', '')}",
            f"File Path: {info.get('file_path', '')}",
        ]
        QMessageBox.information(self, "Book Info", "\n".join(details))
    
    def _on_generate_embeddings_clicked(self):
        book_id = self._get_selected_book_id()
        if book_id is None:
            QMessageBox.information(self, "No selection", "Please select a book first.")
            return
        if self._embed_worker and self._embed_worker.isRunning():
            return
        confirm = QMessageBox.question(
            self,
            "Generate Embeddings",
            "Generate embeddings for the selected book?\n\n"
            "This may take some time for large books.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.embed_button.setEnabled(False)
        self.status_label.setText("Generating embeddings for the selected book. This may take some time...")

        self._embed_worker = GenerateEmbeddingsWorker(self.book_manager, book_id)
        self._embed_worker.finished.connect(self._on_embed_finished)
        self._embed_worker.error.connect(self._on_embed_error)
        self._embed_worker.start()

    def _on_embed_finished(self, result: dict):
        chunks_embedded = result.get("chunks_embedded", 0)
        QMessageBox.information(
            self,
            "Embeddings Generated",
            f"Embeddings generated successfully.\nChunks embedded: {chunks_embedded}",
        )
        self._load_books()
        self.embed_button.setEnabled(True)
        self.status_label.setText("Embeddings generated.")

    def _on_embed_error(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
        self.status_label.setText("Failed to generate embeddings.")
        self.embed_button.setEnabled(True)
    
    # Handle delete book button click
    def _on_delete_book_clicked(self):
        book_id = self._get_selected_book_id()
        if book_id is None:
            QMessageBox.information(self, "No selection", "Please select a book first.")
            return
        
        try:
            book_info = self.book_manager.get_book_info(book_id)
            book_title = book_info.get('title', f'Book ID {book_id}')
        except Exception:
            book_title = f'Book ID {book_id}'
        
        confirm = QMessageBox.question(
            self,
            "Delete Book",
            f"Are you sure you want to delete '{book_title}'?\n\n"
            "This will permanently delete the book, all its chunks, embeddings, and frameworks.\n"
            "This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        try:
            self.book_manager.delete_book(book_id)
            QMessageBox.information(self, "Book Deleted", f"'{book_title}' has been deleted successfully.")
            self._load_books()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to delete book: {exc}")

