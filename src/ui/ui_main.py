from __future__ import annotations

import sys
from typing import List

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.api import service

from ..core.app_config import get_ui_theme, save_ui_theme
from ..core.book_manager import BookManager
from .styles import (
    TAB_SPACING,
    build_app_stylesheet,
    refresh_hero_cards,
    refresh_section_cards,
    set_theme,
)
from .ui_settings import SettingsTab
from .ui_upload_doc import UploadTab
from .ui_library import LibraryTab
from .ui_chat import ChatTab
from .ui_frameworks import FrameworksTab
from .ui_mindmap import MindmapTab
from .theme_switch import ThemeSwitch


def _application_palette_for_theme(theme: str) -> QPalette:
    pal = QPalette()
    if theme == "dark":
        pal.setColor(QPalette.ColorRole.Window, QColor("#161B22"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0d1117"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e6edf3"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#e6edf3"))
    else:
        pal.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#1a1a1a"))
    return pal


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proper Thinking AI")
        self.resize(900, 600)

        self.book_manager = BookManager()
        service.bind_book_manager(self.book_manager)
        self._init_ui()

    def _init_ui(self):
        central_widget = QWidget(self)
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(TAB_SPACING)
        central_widget.setLayout(main_layout)

        nav_bar = QFrame()
        self._nav_bar = nav_bar
        nav_bar.setObjectName("mainNavBar")
        nav_outer = QHBoxLayout(nav_bar)
        nav_outer.setContentsMargins(0, 0, 0, 0)
        nav_outer.setSpacing(0)
        nav_outer.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        nav_outer.addStretch(1)
        nav_center = QHBoxLayout()
        nav_center.setSpacing(0)
        nav_center.setContentsMargins(0, 4, 0, 4)
        nav_center.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        titles = [
            "Settings",
            "Upload",
            "Library",
            "Chat",
            "Frameworks",
            "Mindmap",
        ]
        self._nav_buttons: List[QPushButton] = []
        for i, title in enumerate(titles):
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("navLink", True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._nav_group.addButton(btn, i)
            nav_center.addWidget(btn, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._nav_buttons.append(btn)

        nav_outer.addLayout(nav_center)
        nav_right = QHBoxLayout()
        nav_right.setContentsMargins(0, 0, 16, 0)
        nav_right.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        nav_right.addStretch(1)
        self._theme_toggle = ThemeSwitch()
        self._theme_toggle.setCheckedSilently(get_ui_theme() == "dark")
        self._theme_toggle.toggled.connect(self._on_theme_toggled)
        nav_right.addWidget(self._theme_toggle, alignment=Qt.AlignmentFlag.AlignVCenter)
        nav_outer.addLayout(nav_right, 1)

        main_layout.addWidget(nav_bar)

        stack = QStackedWidget()
        stack.setObjectName("mainStack")
        main_layout.addWidget(stack, 1)

        settings_tab = SettingsTab()
        stack.addWidget(settings_tab)

        upload_tab = UploadTab(self.book_manager)
        stack.addWidget(upload_tab)

        library_tab = LibraryTab(self.book_manager)
        stack.addWidget(library_tab)
        self._library_tab_index = 2

        chat_tab = ChatTab(self.book_manager)
        stack.addWidget(chat_tab)

        frameworks_tab = FrameworksTab(self.book_manager)
        stack.addWidget(frameworks_tab)

        mindmap_tab = MindmapTab(self.book_manager)
        stack.addWidget(mindmap_tab)

        self._stack = stack
        self._nav_group.idClicked.connect(stack.setCurrentIndex)
        stack.currentChanged.connect(self._on_tab_changed)

        self._nav_buttons[0].setChecked(True)

    def _on_theme_toggled(self, checked: bool) -> None:
        theme = "dark" if checked else "light"
        save_ui_theme(theme)
        set_theme(theme)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_app_stylesheet())
            app.setPalette(_application_palette_for_theme(theme))
        self._theme_toggle.update()
        refresh_hero_cards(self)
        refresh_section_cards(self)
        for i in range(self._stack.count()):
            w = self._stack.widget(i)
            if hasattr(w, "apply_theme"):
                w.apply_theme()

    def _on_tab_changed(self, index: int):
        if index == self._library_tab_index:
            self._stack.widget(self._library_tab_index).refresh_books()


def run_gui():
    try:
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass
    app = QApplication(sys.argv)
    t = get_ui_theme()
    set_theme(t)
    app.setPalette(_application_palette_for_theme(t))
    app.setStyleSheet(build_app_stylesheet())
    window = MainWindow()
    window.show()
    app.exec()
