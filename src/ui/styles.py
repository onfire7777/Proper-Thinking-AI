"""Theme tokens, global QSS (build_app_stylesheet), and widget helpers."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QComboBox,
    QPushButton,
    QGraphicsDropShadowEffect,
    QSizePolicy,
    QScrollArea,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
)

# =============================================================================
# TABLE DELEGATE
# =============================================================================
_TABLE_GRID_QCOLOR = QColor("#bdbdbd")

# =============================================================================
# APP CONSTANTS (non-theme)
# =============================================================================
CURRENT_THEME: str = "light"
DATA_TABLE_MAX_VIEW_HEIGHT = 380
RECENT_UPLOADS_MIN_BODY_VIEWPORT_PX = 180
RECENT_UPLOADS_ROW_HEIGHT_PX = 32


class DataTableFirstColumnEdgeDelegate(QStyledItemDelegate):
    """Paints outer vertical gridlines on column 0 and last column for QTableWidget#dataTable."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        model = index.model()
        if model is None:
            return
        r = option.rect
        if index.column() == 0:
            painter.fillRect(r.left(), r.top(), 1, r.height(), _TABLE_GRID_QCOLOR)
        last_col = model.columnCount() - 1
        if last_col >= 0 and index.column() == last_col:
            x = r.left() + r.width() - 1
            painter.fillRect(x, r.top(), 1, r.height(), _TABLE_GRID_QCOLOR)


class SectionCardFrame(QFrame):
    """Section card: paint rounded rect with real corner transparency so drop shadows follow the shape."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._radius = float(SECTION_CARD_RADIUS_PX)
        self._bg = SECTION_CARD_BG
        self._border = SECTION_CARD_BORDER

    def set_theme_card(self, bg: str, border: str, radius_px: int) -> None:
        self._bg = bg
        self._border = border
        self._radius = float(radius_px)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), self._radius, self._radius)
        painter.fillPath(path, QColor(self._bg))
        pen = QPen(QColor(self._border))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)


# =============================================================================
# NAVIGATION & ACCENTS (defaults; set_theme updates where needed)
# =============================================================================
MAIN_BG = "#ffffff"
NAV_BAR_BG = "#ffffff"
NAV_BAR_BORDER_BOTTOM = "#d1d5db"
NAV_TEXT = "#475569"
NAV_TEXT_ACTIVE = "#2563eb"
NAV_TEXT_HOVER = "#1d4ed8"
NAV_TAB_PADDING_V = 9
NAV_TAB_PADDING_H = 18
ACCENT_BLUE = "#1e3a8a"
ACCENT_BLUE_HOVER = "#1e40af"
ACCENT_BLUE_PRESSED = "#172554"

# =============================================================================
# TAB PAGE LAYOUT (scroll area content)
# =============================================================================
TAB_MARGINS = (28, 28, 28, 24)
TAB_SPACING = 16
SECTION_CARD_STACK_GAP_PX = 22
# Inner scroll content (L, T, R, B)
SCROLL_CONTENT_MARGINS_NO_VSCROLL = (22, 14, 22, 28)
SCROLL_CONTENT_MARGINS_VSCROLL = (34, 14, 22, 28)
HERO_TO_MAIN_CONTENT_GAP_PX = TAB_SPACING
MINDMAP_WEB_VIEW_MIN_HEIGHT = 520

# =============================================================================
# HERO & SECTION CARDS
# =============================================================================
HERO_CARD_BG = "#f4f6f9"
HERO_CARD_BORDER = "#d1d5db"
SECTION_CARD_BG = "#ffffff"
SECTION_CARD_BORDER = "#cbd5e1"
SECTION_CARD_RADIUS_PX = 12
SECTION_CARD_CONTENT_MARGINS = (18, 16, 18, 18)
SECTION_TITLE_STYLE = (
    "font-size: 16px; font-weight: 600; color: #0f172a; letter-spacing: -0.02em;"
)
TITLE_STYLE = (
    "background-color: transparent; font-size: 22px; font-weight: 700; color: #0f172a; letter-spacing: -0.02em;"
)
SUBTITLE_STYLE = "background-color: transparent; font-size: 13px; color: #475569;"

# =============================================================================
# GROUP BOX & FORM LABELS
# =============================================================================
GROUPBOX_BORDER_COLOR = "#7a7a7a"
GROUPBOX_RADIUS_PX = 8
GROUPBOX_MARGIN_TOP_PX = 13
GROUPBOX_CONTENT_MARGINS = (6, 8, 6, 6)
SECTION_LABEL_STYLE = (
    "font-size: 13px; font-weight: 600; color: #334155; "
    "border: none; padding-left: 10px; background-color: transparent;"
)

# =============================================================================
# INPUTS (QComboBox, QLineEdit)
# =============================================================================
COMBO_STYLE = (
    "QComboBox { background-color: #f8fafc; color: #0f172a; "
    "border: 1px solid #e2e8f0; border-radius: 8px; "
    "padding: 6px 12px; font-size: 12.5px; }"
    "QComboBox:hover { border-color: #cbd5e1; background-color: #ffffff; }"
    "QComboBox:focus { border-color: #2563eb; background-color: #ffffff; }"
    "QComboBox::drop-down { border: none; width: 28px; "
    "border-top-right-radius: 8px; border-bottom-right-radius: 8px; subcontrol-origin: padding; "
    "subcontrol-position: center right; }"
    "QComboBox::down-arrow { width: 12px; height: 12px; }"
)

# Line edit (question input, etc.) — complete border, modern look
INPUT_LINE = (
    "QLineEdit { background-color: #f8fafc; color: #0f172a; "
    "border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 12px; font-size: 12.5px; }"
    "QLineEdit:hover { border-color: #cbd5e1; background-color: #ffffff; }"
    "QLineEdit:focus { border-color: #2563eb; background-color: #ffffff; }"
    "QLineEdit:disabled { background-color: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }"
)

# =============================================================================
# BUTTONS (QSS strings; refreshed by _refresh_button_tokens after set_theme)
# =============================================================================
BTN_FONT = ""
BTN_PRIMARY = ""
BTN_SECONDARY = ""
BTN_DANGER = ""
BTN_SECONDARY_SMALL = ""
BTN_PRIMARY_SMALL = ""
BTN_DANGER_SMALL = ""


def _refresh_button_tokens() -> None:
    """Rebuild BTN_* QSS from CURRENT_THEME."""
    global BTN_FONT, BTN_PRIMARY, BTN_SECONDARY, BTN_DANGER, BTN_SECONDARY_SMALL, BTN_PRIMARY_SMALL, BTN_DANGER_SMALL
    dark = CURRENT_THEME == "dark"
    BTN_FONT = "font-size: 14px; font-weight: 600;"
    btn_font_sm = "font-size: 12.5px; font-weight: 600;"
    pad = "margin: 0px; padding: 6px 14px;"
    pad_sm = "margin: 0px; padding: 5px 12px;"
    dis = (
        "border: 1px solid #30363d; background-color: #30363d; color: #6e7681;"
        if dark
        else "border: 1px solid #d1d5db; background-color: #f3f4f6; color: #6b7280;"
    )
    focus_pri = "border: 1px solid #4ade80;" if dark else "border: 1px solid #22c55e;"
    focus_sec = "border: 1px solid #79b8ff;" if dark else "border: 1px solid #3b82f6;"
    focus_dan = "border: 1px solid #ff7b72;" if dark else "border: 1px solid #f87171;"
    BTN_PRIMARY = (
        "QPushButton { background-color: #15803d; color: #ffffff; "
        f"border: 1px solid #166534; border-radius: 6px; {pad} "
        + BTN_FONT
        + " }"
        "QPushButton:hover { background-color: #166534; color: #ffffff; }"
        "QPushButton:pressed { background-color: #14532d; color: #ffffff; }"
        f"QPushButton:focus {{ {focus_pri} }}"
        f"QPushButton:disabled {{ {dis} " + BTN_FONT + " }"
    )
    BTN_SECONDARY = (
        f"QPushButton {{ background-color: {ACCENT_BLUE_HOVER}; color: #ffffff; "
        f"border: 1px solid {ACCENT_BLUE}; border-radius: 6px; {pad} "
        + BTN_FONT
        + " }"
        f"QPushButton:hover {{ background-color: {ACCENT_BLUE}; color: #ffffff; }}"
        f"QPushButton:pressed {{ background-color: {ACCENT_BLUE_PRESSED}; color: #ffffff; }}"
        f"QPushButton:focus {{ {focus_sec} }}"
        f"QPushButton:disabled {{ {dis} " + BTN_FONT + " }"
    )
    BTN_DANGER = (
        "QPushButton { background-color: #ef4444; color: #ffffff; "
        f"border: 1px solid #dc2626; border-radius: 6px; {pad} "
        + BTN_FONT
        + " }"
        "QPushButton:hover { background-color: #dc2626; color: #ffffff; }"
        "QPushButton:pressed { background-color: #b91c1c; color: #ffffff; }"
        f"QPushButton:focus {{ {focus_dan} }}"
        f"QPushButton:disabled {{ {dis} " + BTN_FONT + " }"
    )
    BTN_PRIMARY_SMALL = (
        "QPushButton { background-color: #15803d; color: #ffffff; "
        f"border: 1px solid #166534; border-radius: 6px; {pad_sm} "
        + btn_font_sm
        + " margin: 0; }"
        "QPushButton:hover { background-color: #166534; color: #ffffff; }"
        "QPushButton:pressed { background-color: #14532d; color: #ffffff; }"
        f"QPushButton:focus {{ {focus_pri} }}"
        f"QPushButton:disabled {{ {dis} " + btn_font_sm + " }"
    )
    BTN_DANGER_SMALL = (
        "QPushButton { background-color: #ef4444; color: #ffffff; "
        f"border: 1px solid #dc2626; border-radius: 6px; {pad_sm} "
        + btn_font_sm
        + " margin: 0; }"
        "QPushButton:hover { background-color: #dc2626; color: #ffffff; }"
        "QPushButton:pressed { background-color: #b91c1c; color: #ffffff; }"
        f"QPushButton:focus {{ {focus_dan} }}"
        f"QPushButton:disabled {{ {dis} " + btn_font_sm + " }"
    )
    BTN_SECONDARY_SMALL = (
        f"QPushButton {{ background-color: {ACCENT_BLUE_HOVER}; color: #ffffff; "
        f"border: 1px solid {ACCENT_BLUE}; border-radius: 6px; {pad_sm} "
        + btn_font_sm
        + " margin: 0; }"
        f"QPushButton:hover {{ background-color: {ACCENT_BLUE}; color: #ffffff; }}"
        f"QPushButton:pressed {{ background-color: {ACCENT_BLUE_PRESSED}; color: #ffffff; }}"
        f"QPushButton:focus {{ {focus_sec} }}"
        f"QPushButton:disabled {{ {dis} " + btn_font_sm + " }"
    )


_refresh_button_tokens()

# =============================================================================
# CHAT TAB — height clamp (concatenate after BTN_SECONDARY / BTN_PRIMARY)
# =============================================================================
CHAT_BTN_HEIGHT_CLAMP = (
    "QPushButton { padding: 3px 12px; min-height: 22px; max-height: 29px; }"
)

# =============================================================================
# DATA TABLES & LISTS (defaults; set_theme updates)
# =============================================================================
TABLE_GRID_HEX = "#bdbdbd"
TABLE_HEADER_BG = "#eeeeee"
TABLE_HEADER_TEXT = "#1a1a1a"
TABLE_SELECTED_BG = "#e8e8e8"
TABLE_SELECTED_TEXT = "#1a1a1a"
TABLE_CORNER_BG = "#eeeeee"
RECENT_UPLOADS_TABLE_RADIUS_PX = 10
RECENT_UPLOADS_TABLE_BG = "#f4f6f9"
RECENT_UPLOADS_HEADER_BG = "#eeeeee"
RECENT_UPLOADS_TABLE_BORDER = "#94a3b8"
RECENT_UPLOADS_HEADER_RULE = "#cbd5e1"
RECENT_UPLOADS_SCROLLBAR_HANDLE = "#c0c4cc"
RECENT_UPLOADS_SCROLLBAR_TRACK = "#eceff3"
CARD_TABLE_LIGHT_BODY_FILLED = "#ffffff"
LIST_BORDER = "#d0d0d0"
LIST_ITEM_HOVER_BG = "#e8e8e8"
LIST_ITEM_SELECTED_BG = "#d8d8d8"
LIST_ITEM_SELECTED_TEXT = "#1a1a1a"
LIST_ITEM_SELECTED_HOVER_BG = "#e0e0e0"
COMBO_POPUP_ITEM_BG = "#f0f0f0"
COMBO_POPUP_ITEM_TEXT = "#1a1a1a"
GROUPBOX_TITLE_COLOR = "#0f172a"
QMSG_LABEL_COLOR = "#1a1a1a"
MUTED_LABEL_STYLE = "color: #777777; font-style: italic;"
PREVIEW_LABEL_STYLE = (
    "font-size:13px; color:#334155; line-height: 1.45; background-color: transparent;"
)
TEXTEDIT_READONLY_STYLE = "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 13px; color: #1a1a1a;"
TEXTEDIT_SMALL_STYLE = "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 12px;"

# Frameworks tab — white surfaces inside section cards (Framework Content / Quality Audit).
FRAMEWORK_CONTENT_VIEW_STYLE = (
    "background-color: #ffffff; color: #0f172a; "
    "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 13px; "
    "selection-background-color: #bfdbfe; selection-color: #0f172a;"
)
FRAMEWORK_AUDIT_VIEW_STYLE = (
    "background-color: #ffffff; color: #0f172a; "
    "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 12px; "
    "selection-background-color: #bfdbfe; selection-color: #0f172a;"
)
STATUS_LABEL_STRONG = "color: #1a1a1a; padding: 6px 0; font-size: 13px; font-weight: 600;"

# =============================================================================
# RICH TEXT / HTML DOCUMENT DEFAULTS (QTextEdit / chat HTML)
# =============================================================================
FRAMEWORK_ASK_DOC_STYLESHEET = (
    "p, div, body { margin: 0 0 2px 0; } "
    "hr { margin: 2px 0; border: none; border-top: 1px solid #d0d0d0; height: 0; }"
)
CHAT_HISTORY_DOC_STYLESHEET = (
    "p, div, body { margin: 0 0 2px 0; } "
    "hr { margin: 2px 0; border: none; border-top: 1px solid #d0d0d0; height: 0; }"
)

# =============================================================================
# CHAT TAB — inset surfaces (history, composer, rail); set_theme overwrites
# =============================================================================
CHAT_INSET_BG = "#f0f0f2"
CHAT_INSET_BORDER = "#bdbdbd"
CHAT_SURFACE_RADIUS_PX = 14
CHAT_COMPOSER_BAR_RADIUS_PX = 20
CHAT_COMPOSER_PADDING = "4px 10px"
CHAT_HISTORY_TEXTEDIT_STYLE = (
    f"border: 1px solid {CHAT_INSET_BORDER}; border-bottom: none; "
    f"border-top-left-radius: {CHAT_SURFACE_RADIUS_PX}px; border-top-right-radius: {CHAT_SURFACE_RADIUS_PX}px; "
    f"border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; "
    f"font-size: 13px; color: #1a1a1a; background-color: {CHAT_INSET_BG};"
)
CHAT_SOURCES_INLINE_STYLE = "color: #555555; font-size: 11px;"
CHAT_SEP_BORDER_COLOR = "#d0d0d0"
CHAT_USER_BUBBLE_BG = "#15803d"
CHAT_USER_BUBBLE_FG = "#ffffff"
CHAT_USER_BUBBLE_BORDER = "#166534"
CHAT_ASSISTANT_BUBBLE_BG = "#f1f5f9"
CHAT_ASSISTANT_BUBBLE_FG = "#0f172a"
CHAT_ASSISTANT_BUBBLE_BORDER = "#e2e8f0"
CHAT_RAIL_BG = "#f6f7f9"
CHAT_RAIL_BORDER = "#d4d4d4"
CHAT_RAIL_TOGGLE_HOVER = "#e8eaed"
# Circular send (ChatGPT-style); set_theme overwrites hover/pressed/disabled.
CHAT_SEND_BG = "#22c55e"
CHAT_SEND_HOVER = "#16a34a"
CHAT_SEND_PRESSED = "#15803d"
CHAT_SEND_DISABLED = "#cbd5e1"
# Thread list rows — flat, compact; set_theme overwrites.
CHAT_THREAD_ITEM_BG = "transparent"
CHAT_THREAD_ITEM_BG_HOVER = "#eeeff2"
CHAT_THREAD_ITEM_BG_SELECTED = "#e6e8ed"
CHAT_THREAD_ITEM_BG_SELECTED_HOVER = "#dfe2e8"
CHAT_THREAD_ITEM_TEXT = "#1a1a1a"
CHAT_THREAD_ITEM_TEXT_SELECTED = "#0f172a"
CHAT_COMPOSER_STYLE = (
    f"QTextEdit {{ background-color: transparent; color: #1a1a1a; "
    f"border: none; border-radius: 4px; padding: {CHAT_COMPOSER_PADDING}; font-size: 13px; }}"
    "QTextEdit:focus { border: none; outline: none; }"
    "QTextEdit:disabled { background-color: transparent; color: #888888; }"
)


# =============================================================================
# THEME: set_theme
# =============================================================================
def set_theme(name: str) -> None:
    """Assign light/dark globals for tokens, QSS, and inline widget styles."""
    global CURRENT_THEME
    global MAIN_BG, NAV_BAR_BG, NAV_BAR_BORDER_BOTTOM, NAV_TEXT, NAV_TEXT_ACTIVE, NAV_TEXT_HOVER
    global HERO_CARD_BG, HERO_CARD_BORDER, TITLE_STYLE, SUBTITLE_STYLE
    global SECTION_CARD_BG, SECTION_CARD_BORDER, SECTION_TITLE_STYLE
    global RECENT_UPLOADS_TABLE_BG, RECENT_UPLOADS_HEADER_BG, RECENT_UPLOADS_TABLE_BORDER, RECENT_UPLOADS_HEADER_RULE
    global RECENT_UPLOADS_SCROLLBAR_HANDLE, RECENT_UPLOADS_SCROLLBAR_TRACK
    global GROUPBOX_BORDER_COLOR, SECTION_LABEL_STYLE, COMBO_STYLE, INPUT_LINE
    global TABLE_GRID_HEX, TABLE_HEADER_BG, TABLE_HEADER_TEXT, TABLE_SELECTED_BG, TABLE_SELECTED_TEXT, TABLE_CORNER_BG
    global LIST_BORDER, LIST_ITEM_HOVER_BG, LIST_ITEM_SELECTED_BG, LIST_ITEM_SELECTED_TEXT, LIST_ITEM_SELECTED_HOVER_BG
    global COMBO_POPUP_ITEM_BG, COMBO_POPUP_ITEM_TEXT, GROUPBOX_TITLE_COLOR, QMSG_LABEL_COLOR
    global MUTED_LABEL_STYLE, PREVIEW_LABEL_STYLE, TEXTEDIT_READONLY_STYLE, TEXTEDIT_SMALL_STYLE
    global STATUS_LABEL_STRONG, FRAMEWORK_ASK_DOC_STYLESHEET, CHAT_HISTORY_DOC_STYLESHEET
    global CHAT_HISTORY_TEXTEDIT_STYLE, CHAT_SOURCES_INLINE_STYLE, CHAT_SEP_BORDER_COLOR
    global CHAT_USER_BUBBLE_BG, CHAT_USER_BUBBLE_FG, CHAT_USER_BUBBLE_BORDER
    global CHAT_ASSISTANT_BUBBLE_BG, CHAT_ASSISTANT_BUBBLE_FG
    global CHAT_ASSISTANT_BUBBLE_BORDER, CHAT_RAIL_BG, CHAT_RAIL_BORDER
    global CHAT_COMPOSER_STYLE, CHAT_COMPOSER_PADDING, CHAT_INSET_BG, CHAT_INSET_BORDER
    global CHAT_RAIL_TOGGLE_HOVER
    global CHAT_SEND_BG, CHAT_SEND_HOVER, CHAT_SEND_PRESSED, CHAT_SEND_DISABLED
    global CHAT_THREAD_ITEM_BG, CHAT_THREAD_ITEM_BG_HOVER
    global CHAT_THREAD_ITEM_BG_SELECTED, CHAT_THREAD_ITEM_BG_SELECTED_HOVER
    global CHAT_THREAD_ITEM_TEXT, CHAT_THREAD_ITEM_TEXT_SELECTED
    global _TABLE_GRID_QCOLOR

    dark = (name or "light").strip().lower() == "dark"
    CURRENT_THEME = "dark" if dark else "light"

    # --- Dark ---
    if dark:
        MAIN_BG = "#161B22"
        NAV_BAR_BG = "#161B22"
        NAV_BAR_BORDER_BOTTOM = "#444c56"
        NAV_TEXT = "#9ca3af"
        NAV_TEXT_ACTIVE = "#58a6ff"
        NAV_TEXT_HOVER = "#79b8ff"
        HERO_CARD_BG = "#21262D"
        HERO_CARD_BORDER = "#30363D"
        SECTION_CARD_BG = "#21262D"
        SECTION_CARD_BORDER = "#444c56"
        SECTION_TITLE_STYLE = (
            "font-size: 16px; font-weight: 600; color: #e2e8f0; letter-spacing: -0.02em;"
        )
        TITLE_STYLE = (
            "background-color: transparent; font-size: 22px; font-weight: 700; color: #f0f6fc; "
            "letter-spacing: -0.02em;"
        )
        SUBTITLE_STYLE = "background-color: transparent; font-size: 13px; color: #8b949e;"
        GROUPBOX_BORDER_COLOR = "#444c56"
        SECTION_LABEL_STYLE = (
            "font-size: 13px; font-weight: 600; color: #cbd5e1; "
            "border: none; padding-left: 10px; background-color: transparent;"
        )
        COMBO_STYLE = (
            "QComboBox { background-color: #161b22; color: #e6edf3; "
            "border: 1px solid #475569; border-radius: 8px; "
            "padding: 6px 12px; font-size: 12.5px; }"
            "QComboBox:hover { border-color: #64748b; background-color: #21262d; }"
            "QComboBox:focus { border-color: #58a6ff; background-color: #21262d; }"
            "QComboBox::drop-down { border: none; width: 28px; "
            "border-top-right-radius: 8px; border-bottom-right-radius: 8px; subcontrol-origin: padding; "
            "subcontrol-position: center right; }"
            "QComboBox::down-arrow { width: 12px; height: 12px; }"
        )
        INPUT_LINE = (
            "QLineEdit { background-color: #161b22; color: #e6edf3; "
            "border: 1px solid #475569; border-radius: 8px; padding: 6px 12px; font-size: 12.5px; }"
            "QLineEdit:hover { border-color: #64748b; background-color: #21262d; }"
            "QLineEdit:focus { border-color: #58a6ff; background-color: #21262d; }"
            "QLineEdit:disabled { background-color: #0d1117; color: #6e7681; border-color: #30363d; }"
        )
        TABLE_GRID_HEX = "#444c56"
        TABLE_HEADER_BG = "#2d333b"
        TABLE_HEADER_TEXT = "#e6edf3"
        TABLE_SELECTED_BG = "#21262d"
        TABLE_SELECTED_TEXT = "#e6edf3"
        TABLE_CORNER_BG = "#2d333b"
        RECENT_UPLOADS_TABLE_BG = SECTION_CARD_BG
        RECENT_UPLOADS_HEADER_BG = "#2d333b"
        RECENT_UPLOADS_TABLE_BORDER = "#30363d"
        RECENT_UPLOADS_HEADER_RULE = "#444c56"
        RECENT_UPLOADS_SCROLLBAR_HANDLE = "#6e7681"
        RECENT_UPLOADS_SCROLLBAR_TRACK = "#21262d"
        LIST_BORDER = "#30363d"
        LIST_ITEM_HOVER_BG = "#21262d"
        LIST_ITEM_SELECTED_BG = "#30363d"
        LIST_ITEM_SELECTED_TEXT = "#f0f6fc"
        LIST_ITEM_SELECTED_HOVER_BG = "#3d444c"
        COMBO_POPUP_ITEM_BG = "#21262d"
        COMBO_POPUP_ITEM_TEXT = "#e6edf3"
        GROUPBOX_TITLE_COLOR = "#f0f6fc"
        QMSG_LABEL_COLOR = "#e6edf3"
        MUTED_LABEL_STYLE = "color: #9ca3af; font-style: italic;"
        PREVIEW_LABEL_STYLE = (
            "font-size:13px; color:#c9d1d9; line-height: 1.45; background-color: transparent;"
        )
        TEXTEDIT_READONLY_STYLE = (
            f"border: 1px solid #444c56; border-radius: 4px; font-size: 13px; color: #e6edf3; "
            f"background-color: {SECTION_CARD_BG};"
        )
        TEXTEDIT_SMALL_STYLE = (
            f"border: 1px solid #444c56; border-radius: 4px; font-size: 12px; "
            f"background-color: {SECTION_CARD_BG}; color: #e6edf3;"
        )
        STATUS_LABEL_STRONG = "color: #f0f6fc; padding: 6px 0; font-size: 13px; font-weight: 600;"
        FRAMEWORK_ASK_DOC_STYLESHEET = (
            "p, div, body { margin: 0 0 2px 0; } "
            "hr { margin: 2px 0; border: none; border-top: 1px solid #444c56; height: 0; }"
        )
        CHAT_HISTORY_DOC_STYLESHEET = (
            "body { color: #e6edf3; } "
            "p, div, span, li { color: #e6edf3; } "
            "b, strong { color: inherit; font-weight: 600; } "
            "h2 { font-size: 13px; font-weight: 600; margin: 4px 0 2px 0; color: #f0f6fc; } "
            "h3 { font-size: 12px; font-weight: 600; margin: 4px 0 2px 0; color: #f0f6fc; } "
            "ul { margin: 2px 0; padding-left: 20px; color: #e6edf3; } "
            "li { margin: 1px 0; color: #e6edf3; } "
            "p { margin: 0 0 2px 0; } "
            ".assistant-body { margin: 0; padding: 0; color: #e6edf3; } "
            ".assistant-body h2:first-child, .assistant-body h3:first-child { margin-top: 0; } "
            ".chat-sources { font-size: 11px; color: #8b949e; background-color: transparent; } "
            "p.chat-sources, span.chat-sources, div.chat-sources { background-color: transparent; } "
            ".chat-sources-block { margin-top: 3px; margin-bottom: 1px; } "
            ".chat-msg-spacer { height: 10px; margin: 0; padding: 0; border: none; } "
            ".chat-separator { display: none; border: none; margin: 0; height: 0; } "
            ".chat-line-user { margin: 0 0 4px 0; color: #e6edf3; } "
            ".chat-line-user .chat-role { color: #f0f6fc; font-weight: 600; } "
            "p.chat-assistant-label { margin: 0; padding: 0; } "
            "p.chat-assistant-label, p.chat-assistant-label b { color: #f0f6fc; } "
            ".chat-line-error, .chat-line-warn { color: #ff7b72; } "
            "hr { margin: 2px 0; border: none; border-top: 1px solid #444c56; height: 0; }"
        )
        CHAT_INSET_BG = "#282e36"
        CHAT_INSET_BORDER = "#444c56"
        CHAT_COMPOSER_PADDING = "4px 10px"
        CHAT_HISTORY_TEXTEDIT_STYLE = (
            f"border: 1px solid {CHAT_INSET_BORDER}; border-bottom: none; "
            f"border-top-left-radius: {CHAT_SURFACE_RADIUS_PX}px; border-top-right-radius: {CHAT_SURFACE_RADIUS_PX}px; "
            f"border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; "
            f"font-size: 13px; color: #e6edf3; background-color: {CHAT_INSET_BG};"
        )
        CHAT_SOURCES_INLINE_STYLE = "color: #8b949e; font-size: 11px;"
        CHAT_SEP_BORDER_COLOR = "#444c56"
        CHAT_USER_BUBBLE_BG = "#15803d"
        CHAT_USER_BUBBLE_FG = "#ffffff"
        CHAT_USER_BUBBLE_BORDER = "#166534"
        CHAT_ASSISTANT_BUBBLE_BG = "#21262d"
        CHAT_ASSISTANT_BUBBLE_FG = "#e6edf3"
        CHAT_ASSISTANT_BUBBLE_BORDER = "#30363d"
        CHAT_RAIL_BG = "#1b2028"
        CHAT_RAIL_BORDER = "#30363d"
        CHAT_RAIL_TOGGLE_HOVER = "#3d444c"
        CHAT_SEND_BG = "#22c55e"
        CHAT_SEND_HOVER = "#4ade80"
        CHAT_SEND_PRESSED = "#16a34a"
        CHAT_SEND_DISABLED = "#525252"
        CHAT_THREAD_ITEM_BG = "transparent"
        CHAT_THREAD_ITEM_BG_HOVER = "#3d424c"
        CHAT_THREAD_ITEM_BG_SELECTED = "#3e434d"
        CHAT_THREAD_ITEM_BG_SELECTED_HOVER = "#484e59"
        CHAT_THREAD_ITEM_TEXT = TABLE_HEADER_TEXT
        CHAT_THREAD_ITEM_TEXT_SELECTED = "#f6f7f8"
        CHAT_COMPOSER_STYLE = (
            f"QTextEdit {{ background-color: transparent; color: #e6edf3; "
            f"border: none; border-radius: 4px; padding: {CHAT_COMPOSER_PADDING}; font-size: 13px; }}"
            "QTextEdit:focus { border: none; outline: none; }"
            f"QTextEdit:disabled {{ background-color: transparent; color: #6e7681; }}"
        )
    # --- Light ---
    else:
        MAIN_BG = "#ffffff"
        NAV_BAR_BG = "#ffffff"
        NAV_BAR_BORDER_BOTTOM = "#d1d5db"
        NAV_TEXT = "#475569"
        NAV_TEXT_ACTIVE = "#2563eb"
        NAV_TEXT_HOVER = "#1d4ed8"
        HERO_CARD_BG = "#f4f6f9"
        HERO_CARD_BORDER = "#d1d5db"
        SECTION_CARD_BG = "#ffffff"
        SECTION_CARD_BORDER = "#cbd5e1"
        SECTION_TITLE_STYLE = (
            "font-size: 16px; font-weight: 600; color: #0f172a; letter-spacing: -0.02em;"
        )
        TITLE_STYLE = (
            "background-color: transparent; font-size: 22px; font-weight: 700; color: #0f172a; "
            "letter-spacing: -0.02em;"
        )
        SUBTITLE_STYLE = "background-color: transparent; font-size: 13px; color: #475569;"
        GROUPBOX_BORDER_COLOR = "#7a7a7a"
        SECTION_LABEL_STYLE = (
            "font-size: 13px; font-weight: 600; color: #334155; "
            "border: none; padding-left: 10px; background-color: transparent;"
        )
        COMBO_STYLE = (
            "QComboBox { background-color: #f8fafc; color: #0f172a; "
            "border: 1px solid #e2e8f0; border-radius: 8px; "
            "padding: 6px 12px; font-size: 12.5px; }"
            "QComboBox:hover { border-color: #cbd5e1; background-color: #ffffff; }"
            "QComboBox:focus { border-color: #2563eb; background-color: #ffffff; }"
            "QComboBox::drop-down { border: none; width: 28px; "
            "border-top-right-radius: 8px; border-bottom-right-radius: 8px; subcontrol-origin: padding; "
            "subcontrol-position: center right; }"
            "QComboBox::down-arrow { width: 12px; height: 12px; }"
        )
        INPUT_LINE = (
            "QLineEdit { background-color: #f8fafc; color: #0f172a; "
            "border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 12px; font-size: 12.5px; }"
            "QLineEdit:hover { border-color: #cbd5e1; background-color: #ffffff; }"
            "QLineEdit:focus { border-color: #2563eb; background-color: #ffffff; }"
            "QLineEdit:disabled { background-color: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }"
        )
        TABLE_GRID_HEX = "#bdbdbd"
        TABLE_HEADER_BG = "#eeeeee"
        TABLE_HEADER_TEXT = "#1a1a1a"
        TABLE_SELECTED_BG = "#e8e8e8"
        TABLE_SELECTED_TEXT = "#1a1a1a"
        TABLE_CORNER_BG = "#eeeeee"
        RECENT_UPLOADS_TABLE_BG = "#f4f6f9"
        RECENT_UPLOADS_HEADER_BG = "#eeeeee"
        RECENT_UPLOADS_TABLE_BORDER = "#94a3b8"
        RECENT_UPLOADS_HEADER_RULE = "#cbd5e1"
        RECENT_UPLOADS_SCROLLBAR_HANDLE = "#c0c4cc"
        RECENT_UPLOADS_SCROLLBAR_TRACK = "#eceff3"
        LIST_BORDER = "#d0d0d0"
        LIST_ITEM_HOVER_BG = "#e8e8e8"
        LIST_ITEM_SELECTED_BG = "#d8d8d8"
        LIST_ITEM_SELECTED_TEXT = "#1a1a1a"
        LIST_ITEM_SELECTED_HOVER_BG = "#e0e0e0"
        COMBO_POPUP_ITEM_BG = "#f0f0f0"
        COMBO_POPUP_ITEM_TEXT = "#1a1a1a"
        GROUPBOX_TITLE_COLOR = "#0f172a"
        QMSG_LABEL_COLOR = "#1a1a1a"
        MUTED_LABEL_STYLE = "color: #777777; font-style: italic;"
        PREVIEW_LABEL_STYLE = (
            "font-size:13px; color:#334155; line-height: 1.45; background-color: transparent;"
        )
        TEXTEDIT_READONLY_STYLE = (
            "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 13px; color: #1a1a1a;"
        )
        TEXTEDIT_SMALL_STYLE = "border: 1px solid #d0d0d0; border-radius: 4px; font-size: 12px;"
        STATUS_LABEL_STRONG = "color: #1a1a1a; padding: 6px 0; font-size: 13px; font-weight: 600;"
        FRAMEWORK_ASK_DOC_STYLESHEET = (
            "p, div, body { margin: 0 0 2px 0; } "
            "hr { margin: 2px 0; border: none; border-top: 1px solid #d0d0d0; height: 0; }"
        )
        CHAT_HISTORY_DOC_STYLESHEET = (
            "body { color: #1a1a1a; } "
            "p, div, span, li { color: #1a1a1a; } "
            "b, strong { color: inherit; font-weight: 600; } "
            "h2 { font-size: 13px; font-weight: 600; margin: 4px 0 2px 0; color: #0f172a; } "
            "h3 { font-size: 12px; font-weight: 600; margin: 4px 0 2px 0; color: #0f172a; } "
            "ul { margin: 2px 0; padding-left: 20px; color: #1a1a1a; } "
            "li { margin: 1px 0; color: #1a1a1a; } "
            "p { margin: 0 0 2px 0; } "
            ".assistant-body { margin: 0; padding: 0; color: #1a1a1a; } "
            ".assistant-body h2:first-child, .assistant-body h3:first-child { margin-top: 0; } "
            ".chat-sources { font-size: 11px; color: #64748b; background-color: transparent; } "
            "p.chat-sources, span.chat-sources, div.chat-sources { background-color: transparent; } "
            ".chat-sources-block { margin-top: 6px; margin-bottom: 0; } "
            ".chat-msg-spacer { height: 10px; margin: 0; padding: 0; border: none; } "
            ".chat-separator { display: none; border: none; margin: 0; height: 0; } "
            ".chat-line-user { margin: 0 0 4px 0; color: #1a1a1a; } "
            ".chat-line-user .chat-role { color: #0f172a; font-weight: 600; } "
            "p.chat-assistant-label { margin: 0; padding: 0; } "
            "p.chat-assistant-label, p.chat-assistant-label b { color: #0f172a; } "
            ".chat-line-error, .chat-line-warn { color: #b00020; } "
            "hr { margin: 2px 0; border: none; border-top: 1px solid #d0d0d0; height: 0; }"
        )
        CHAT_INSET_BG = "#f0f0f2"
        CHAT_INSET_BORDER = "#bdbdbd"
        CHAT_COMPOSER_PADDING = "4px 10px"
        CHAT_HISTORY_TEXTEDIT_STYLE = (
            f"border: 1px solid {CHAT_INSET_BORDER}; border-bottom: none; "
            f"border-top-left-radius: {CHAT_SURFACE_RADIUS_PX}px; border-top-right-radius: {CHAT_SURFACE_RADIUS_PX}px; "
            f"border-bottom-left-radius: 0px; border-bottom-right-radius: 0px; "
            f"font-size: 13px; color: #1a1a1a; background-color: {CHAT_INSET_BG};"
        )
        CHAT_SOURCES_INLINE_STYLE = "color: #555555; font-size: 11px;"
        CHAT_SEP_BORDER_COLOR = "#d0d0d0"
        CHAT_USER_BUBBLE_BG = "#15803d"
        CHAT_USER_BUBBLE_FG = "#ffffff"
        CHAT_USER_BUBBLE_BORDER = "#166534"
        CHAT_ASSISTANT_BUBBLE_BG = "#f1f5f9"
        CHAT_ASSISTANT_BUBBLE_FG = "#0f172a"
        CHAT_ASSISTANT_BUBBLE_BORDER = "#e2e8f0"
        CHAT_RAIL_BG = "#f6f7f9"
        CHAT_RAIL_BORDER = "#d4d4d4"
        CHAT_RAIL_TOGGLE_HOVER = "#e8eaed"
        CHAT_SEND_BG = "#22c55e"
        CHAT_SEND_HOVER = "#16a34a"
        CHAT_SEND_PRESSED = "#15803d"
        CHAT_SEND_DISABLED = "#cbd5e1"
        CHAT_THREAD_ITEM_BG = "transparent"
        CHAT_THREAD_ITEM_BG_HOVER = "#eeeff2"
        CHAT_THREAD_ITEM_BG_SELECTED = "#e6e8ed"
        CHAT_THREAD_ITEM_BG_SELECTED_HOVER = "#dfe2e8"
        CHAT_THREAD_ITEM_TEXT = TABLE_HEADER_TEXT
        CHAT_THREAD_ITEM_TEXT_SELECTED = "#0f172a"
        CHAT_COMPOSER_STYLE = (
            f"QTextEdit {{ background-color: transparent; color: #1a1a1a; "
            f"border: none; border-radius: 4px; padding: {CHAT_COMPOSER_PADDING}; font-size: 13px; }}"
            "QTextEdit:focus { border: none; outline: none; }"
            "QTextEdit:disabled { background-color: transparent; color: #888888; }"
        )

    _refresh_button_tokens()
    _TABLE_GRID_QCOLOR = QColor(TABLE_GRID_HEX)


# =============================================================================
# GLOBAL QSS
# =============================================================================
def build_app_stylesheet() -> str:
    """Return application-wide QSS (call after set_theme)."""
    scroll_track = RECENT_UPLOADS_SCROLLBAR_TRACK
    scroll_handle = RECENT_UPLOADS_SCROLLBAR_HANDLE
    return f"""
/* === SHELL === */
QMainWindow, QWidget#centralWidget {{
    background-color: {MAIN_BG};
}}
QStackedWidget#mainStack {{
    background-color: {MAIN_BG};
    border: none;
}}
QWidget#tabPageFooter {{
    background-color: {MAIN_BG};
    border-top: 1px solid {NAV_BAR_BORDER_BOTTOM};
}}
/* === NAV BAR === */
QFrame#mainNavBar {{
    background-color: {NAV_BAR_BG};
    border: none;
    border-bottom: 1px solid {NAV_BAR_BORDER_BOTTOM};
}}
/* Nav tab buttons */
QPushButton[navLink="true"] {{
    border: none;
    background-color: transparent;
    color: {NAV_TEXT};
    padding: {NAV_TAB_PADDING_V}px {NAV_TAB_PADDING_H}px {NAV_TAB_PADDING_V}px {NAV_TAB_PADDING_H}px;
    margin: 0px;
    font-size: 14px;
    font-weight: 500;
    min-height: 22px;
}}
QPushButton[navLink="true"]:hover {{
    color: {NAV_TEXT_HOVER};
}}
QPushButton[navLink="true"]:checked {{
    color: {NAV_TEXT_ACTIVE};
    font-weight: 600;
}}
QPushButton[navLink="true"]:focus {{
    outline: none;
}}
/* === HERO === */
QFrame#heroCard {{
    background-color: {HERO_CARD_BG};
    border: 1px solid {HERO_CARD_BORDER};
    border-radius: 12px;
}}
QFrame#heroCard QLabel {{
    background-color: transparent;
}}
/* === SECTION CARD (labels / form rows) === */
QFrame#sectionCard QLabel {{
    background-color: transparent;
}}
QFrame#sectionCard QWidget#sectionCardRow {{
    background-color: transparent;
}}
/* === SCROLL AREA (tab pages) === */
QScrollArea {{
    background-color: {MAIN_BG};
}}
QScrollArea QScrollBar:vertical {{
    width: 12px;
    background: {scroll_track};
    margin: 2px 2px 2px 0;
    border: none;
    border-radius: 6px;
}}
QScrollArea QScrollBar::handle:vertical {{
    background: {scroll_handle};
    min-height: 28px;
    border-radius: 6px;
    margin: 3px 2px;
}}
QScrollArea QScrollBar::add-line:vertical, QScrollArea QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QScrollArea QScrollBar::add-page:vertical, QScrollArea QScrollBar::sub-page:vertical {{
    background: {scroll_track};
    border: none;
}}
/* QTextEdit / combo popup base (per-widget COMBO_STYLE still applies) */
QTextEdit,
QComboBox QAbstractItemView {{
    background-color: {MAIN_BG};
}}
QListWidget {{
    background-color: {MAIN_BG};
    border: 1px solid {LIST_BORDER};
    border-radius: 4px;
    padding: 4px;
}}
/* === CHAT TAB === */
QFrame#chatThreadRail {{
    background-color: {CHAT_RAIL_BG};
    border: 1px solid {CHAT_RAIL_BORDER};
    border-radius: 10px;
}}
QToolButton#chatRailToggle {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 2px;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}
QToolButton#chatRailToggle:hover {{
    background-color: {CHAT_RAIL_TOGGLE_HOVER};
}}
QToolButton#chatRailToggle:pressed {{
    background-color: {CHAT_RAIL_TOGGLE_HOVER};
}}
QPushButton#chatSendButton {{
    background-color: transparent;
    border: none;
    border-radius: 13px;
    min-width: 26px;
    max-width: 26px;
    min-height: 26px;
    max-height: 26px;
    padding: 0px;
}}
QPushButton#chatSendButton:hover {{
    background-color: transparent;
}}
QPushButton#chatSendButton:pressed {{
    background-color: transparent;
}}
QPushButton#chatSendButton:disabled {{
    background-color: transparent;
}}
QPushButton#chatSendButton:focus {{
    border: none;
}}
QMenu#chatThreadContextMenu {{
    background-color: {MAIN_BG};
    color: {TABLE_HEADER_TEXT};
    border: 1px solid {LIST_BORDER};
    border-radius: 6px;
    padding: 4px 0;
}}
QMenu#chatThreadContextMenu::item {{
    padding: 6px 18px;
    border-radius: 4px;
    color: {TABLE_HEADER_TEXT};
    background-color: transparent;
}}
QMenu#chatThreadContextMenu::item:selected {{
    background-color: {LIST_ITEM_SELECTED_BG};
    color: {LIST_ITEM_SELECTED_TEXT};
}}
QMenu#chatThreadContextMenu::separator {{
    height: 1px;
    margin: 4px 8px;
    background-color: {LIST_BORDER};
}}
QFrame#chatComposerBar {{
    background-color: {CHAT_INSET_BG};
    border: 1px solid {CHAT_INSET_BORDER};
    border-radius: {CHAT_COMPOSER_BAR_RADIUS_PX}px;
}}
QFrame#chatMainPanel {{
    background-color: {SECTION_CARD_BG};
    border: 1px solid {SECTION_CARD_BORDER};
    border-radius: 12px;
}}
QTextEdit#chatHistoryTextEdit {{
    background-color: {CHAT_INSET_BG};
    border: 1px solid {CHAT_INSET_BORDER};
    border-bottom: none;
    border-top-left-radius: {CHAT_SURFACE_RADIUS_PX}px;
    border-top-right-radius: {CHAT_SURFACE_RADIUS_PX}px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    color: {TABLE_HEADER_TEXT};
    font-size: 13px;
}}
QTextEdit#chatHistoryTextEdit:focus {{
    border-color: {NAV_TEXT_ACTIVE};
}}
QWebEngineView#chatHistoryWebView {{
    background-color: {CHAT_INSET_BG};
    border: 1px solid {CHAT_INSET_BORDER};
    border-bottom: none;
    border-top-left-radius: {CHAT_SURFACE_RADIUS_PX}px;
    border-top-right-radius: {CHAT_SURFACE_RADIUS_PX}px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}}
QWebEngineView#chatHistoryWebView:focus {{
    border-color: {NAV_TEXT_ACTIVE};
}}
QTextEdit#chatComposerInput {{
    border: none;
    border-radius: 4px;
    padding: {CHAT_COMPOSER_PADDING};
    font-size: 13px;
    background-color: transparent;
    color: {TABLE_HEADER_TEXT};
}}
QSplitter#chatWorkspaceSplitter::handle:horizontal {{
    background-color: {MAIN_BG};
}}
QTextEdit#chatComposerInput:focus {{
    border: none;
}}
QGroupBox {{
    background-color: {MAIN_BG};
    border: 1px solid {GROUPBOX_BORDER_COLOR};
    border-radius: {GROUPBOX_RADIUS_PX}px;
    margin-top: {GROUPBOX_MARGIN_TOP_PX}px;
    padding: 11px 14px 14px 14px;
    font-weight: bold;
    font-size: 13px;
    color: {GROUPBOX_TITLE_COLOR};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 13px;
    padding: 0 6px;
    background-color: {MAIN_BG};
    font-size: 13px;
    font-weight: bold;
    color: {GROUPBOX_TITLE_COLOR};
}}
/* === DATA TABLE (#dataTable) === */
QTableWidget#dataTable {{
    background-color: {MAIN_BG};
    border: none;
    border-radius: 0px;
    gridline-color: {TABLE_GRID_HEX};
    outline: none;
}}
QTableWidget#dataTable::item {{
    padding: 4px 8px;
    border: none;
}}
QTableWidget#dataTable::item:selected {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
    border: none;
    outline: none;
}}
QTableWidget#dataTable::item:selected:active {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
    border: none;
}}
QTableWidget#dataTable::item:focus {{
    outline: none;
}}
QTableWidget#dataTable QTableCornerButton::section {{
    border: none;
    border-top: 1px solid {TABLE_GRID_HEX};
    border-left: 1px solid {TABLE_GRID_HEX};
    border-right: 1px solid {TABLE_GRID_HEX};
    border-bottom: 1px solid {TABLE_GRID_HEX};
    background-color: {TABLE_CORNER_BG};
}}
QTableWidget#dataTable QHeaderView {{
    background-color: transparent;
}}
QTableWidget#dataTable QHeaderView::section {{
    background-color: {TABLE_HEADER_BG};
    color: {TABLE_HEADER_TEXT};
    padding: 4px 8px;
    border: none;
    border-top: 1px solid {TABLE_GRID_HEX};
    border-right: 1px solid {TABLE_GRID_HEX};
    border-bottom: 1px solid {TABLE_GRID_HEX};
    font-weight: bold;
    font-size: 12px;
}}
QTableWidget#dataTable QHeaderView::section:first {{
    border-left: 1px solid {TABLE_GRID_HEX};
}}
/* === CARD TABLE (#cardDataTable) === */
QTableWidget#cardDataTable {{
    background-color: {RECENT_UPLOADS_TABLE_BG};
    border-top: 1px solid {RECENT_UPLOADS_TABLE_BORDER};
    border-left: none;
    border-bottom: none;
    border-right: none;
    border-radius: {RECENT_UPLOADS_TABLE_RADIUS_PX}px;
    gridline-color: {RECENT_UPLOADS_HEADER_RULE};
    outline: none;
}}
QTableWidget#cardDataTable::item {{
    padding: 4px 10px;
    border: none;
    background-color: {RECENT_UPLOADS_TABLE_BG};
}}
QTableWidget#cardDataTable::item:selected {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
    border: none;
}}
QTableWidget#cardDataTable::item:selected:active {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
}}
QTableWidget#cardDataTable::item:focus {{
    outline: none;
}}
QTableWidget#cardDataTable QAbstractItemView {{
    background-color: {RECENT_UPLOADS_TABLE_BG};
    border: none;
}}
QTableWidget#cardDataTable[ptaLightBody="empty"] {{
    background-color: {RECENT_UPLOADS_TABLE_BG};
}}
QTableWidget#cardDataTable[ptaLightBody="empty"]::item {{
    background-color: {RECENT_UPLOADS_TABLE_BG};
}}
QTableWidget#cardDataTable[ptaLightBody="empty"] QAbstractItemView {{
    background-color: {RECENT_UPLOADS_TABLE_BG};
    border: none;
}}
QTableWidget#cardDataTable[ptaLightBody="filled"] {{
    background-color: {CARD_TABLE_LIGHT_BODY_FILLED};
}}
QTableWidget#cardDataTable[ptaLightBody="filled"]::item {{
    background-color: {CARD_TABLE_LIGHT_BODY_FILLED};
}}
QTableWidget#cardDataTable[ptaLightBody="filled"] QAbstractItemView {{
    background-color: {CARD_TABLE_LIGHT_BODY_FILLED};
    border: none;
}}
QTableWidget#cardDataTable[ptaLightBody="filled"]::item:selected {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
    border: none;
}}
QTableWidget#cardDataTable[ptaLightBody="filled"]::item:selected:active {{
    background-color: {TABLE_SELECTED_BG};
    color: {TABLE_SELECTED_TEXT};
}}
QTableWidget#cardDataTable QTableCornerButton::section {{
    border: none;
    background-color: {RECENT_UPLOADS_HEADER_BG};
}}
QTableWidget#cardDataTable QHeaderView {{
    background-color: transparent;
}}
QTableWidget#cardDataTable QHeaderView::section {{
    background-color: {RECENT_UPLOADS_HEADER_BG};
    color: {TABLE_HEADER_TEXT};
    min-height: {RECENT_UPLOADS_ROW_HEIGHT_PX}px;
    max-height: {RECENT_UPLOADS_ROW_HEIGHT_PX}px;
    padding: 0 10px;
    border: none;
    border-right: 1px solid {RECENT_UPLOADS_HEADER_RULE};
    border-bottom: 1px solid {RECENT_UPLOADS_TABLE_BORDER};
    font-weight: 600;
    font-size: 12px;
}}
QTableWidget#cardDataTable QHeaderView::section:first {{
    border-top-left-radius: {RECENT_UPLOADS_TABLE_RADIUS_PX - 1}px;
}}
QTableWidget#cardDataTable QHeaderView::section:last {{
    border-right: none;
    border-top-right-radius: {RECENT_UPLOADS_TABLE_RADIUS_PX - 1}px;
}}
QTableWidget#cardDataTable QScrollBar:vertical {{
    width: 12px;
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    margin: 2px 2px 2px 0;
    border: none;
    border-radius: 6px;
}}
QTableWidget#cardDataTable QScrollBar::handle:vertical {{
    background: {RECENT_UPLOADS_SCROLLBAR_HANDLE};
    min-height: 28px;
    border-radius: 6px;
    margin: 3px 2px;
}}
QTableWidget#cardDataTable QScrollBar::add-line:vertical, QTableWidget#cardDataTable QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QTableWidget#cardDataTable QScrollBar::add-page:vertical, QTableWidget#cardDataTable QScrollBar::sub-page:vertical {{
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    border: none;
}}
QTableWidget#cardDataTable QScrollBar:horizontal {{
    height: 12px;
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    margin: 0 2px 2px 2px;
    border: none;
    border-radius: 6px;
}}
QTableWidget#cardDataTable QScrollBar::handle:horizontal {{
    background: {RECENT_UPLOADS_SCROLLBAR_HANDLE};
    min-width: 28px;
    border-radius: 6px;
    margin: 2px 3px;
}}
QTableWidget#cardDataTable QScrollBar::add-line:horizontal, QTableWidget#cardDataTable QScrollBar::sub-line:horizontal {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QTableWidget#cardDataTable QScrollBar::add-page:horizontal, QTableWidget#cardDataTable QScrollBar::sub-page:horizontal {{
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    border: none;
}}
QTextEdit#chatHistoryTextEdit QScrollBar:vertical {{
    width: 12px;
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    margin: 2px 2px 2px 0;
    border: none;
    border-radius: 6px;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::handle:vertical {{
    background: {RECENT_UPLOADS_SCROLLBAR_HANDLE};
    min-height: 28px;
    border-radius: 6px;
    margin: 3px 2px;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::add-line:vertical, QTextEdit#chatHistoryTextEdit QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::add-page:vertical, QTextEdit#chatHistoryTextEdit QScrollBar::sub-page:vertical {{
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    border: none;
}}
QTextEdit#chatHistoryTextEdit QScrollBar:horizontal {{
    height: 12px;
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    margin: 0 2px 2px 2px;
    border: none;
    border-radius: 6px;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::handle:horizontal {{
    background: {RECENT_UPLOADS_SCROLLBAR_HANDLE};
    min-width: 28px;
    border-radius: 6px;
    margin: 2px 3px;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::add-line:horizontal, QTextEdit#chatHistoryTextEdit QScrollBar::sub-line:horizontal {{
    height: 0;
    width: 0;
    border: none;
    background: transparent;
}}
QTextEdit#chatHistoryTextEdit QScrollBar::add-page:horizontal, QTextEdit#chatHistoryTextEdit QScrollBar::sub-page:horizontal {{
    background: {RECENT_UPLOADS_SCROLLBAR_TRACK};
    border: none;
}}
QComboBox QAbstractItemView {{
    border: 1px solid #9ca3af;
    outline: none;
    border-radius: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    min-height: 24px;
    border: none;
    outline: none;
    color: {COMBO_POPUP_ITEM_TEXT};
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {COMBO_POPUP_ITEM_BG};
    color: {COMBO_POPUP_ITEM_TEXT};
    border: none;
    border-left: 3px solid {ACCENT_BLUE_HOVER};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {COMBO_POPUP_ITEM_BG};
    color: {COMBO_POPUP_ITEM_TEXT};
    border: none;
    border-left: 3px solid {ACCENT_BLUE_HOVER};
}}
/* === GENERIC LIST WIDGET === */
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 2px;
}}
QListWidget::item:hover {{
    background-color: {LIST_ITEM_HOVER_BG};
}}
QListWidget::item:selected {{
    background-color: {LIST_ITEM_SELECTED_BG};
    color: {LIST_ITEM_SELECTED_TEXT};
}}
QListWidget::item:selected:hover {{
    background-color: {LIST_ITEM_SELECTED_HOVER_BG};
}}
/* Chat thread rail (overrides generic list item rules above) */
QListWidget#chatThreadList {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 2px 4px;
    font-size: 13px;
}}
QListWidget#chatThreadList::item {{
    background-color: {CHAT_THREAD_ITEM_BG};
    color: {CHAT_THREAD_ITEM_TEXT};
    border: none;
    padding: 7px 10px;
    border-radius: 8px;
    margin: 4px 0px;
}}
QListWidget#chatThreadList::item:hover {{
    background-color: {CHAT_THREAD_ITEM_BG_HOVER};
    color: {CHAT_THREAD_ITEM_TEXT};
    border: none;
}}
QListWidget#chatThreadList::item:selected {{
    background-color: {CHAT_THREAD_ITEM_BG_SELECTED};
    color: {CHAT_THREAD_ITEM_TEXT_SELECTED};
    border: none;
}}
QListWidget#chatThreadList::item:selected:active {{
    background-color: {CHAT_THREAD_ITEM_BG_SELECTED};
    color: {CHAT_THREAD_ITEM_TEXT_SELECTED};
    border: none;
}}
QListWidget#chatThreadList::item:selected:hover {{
    background-color: {CHAT_THREAD_ITEM_BG_SELECTED_HOVER};
    color: {CHAT_THREAD_ITEM_TEXT_SELECTED};
    border: none;
}}

/* === DIALOGS === */
QMessageBox {{
    background-color: {MAIN_BG};
}}
QMessageBox QLabel {{
    color: {QMSG_LABEL_COLOR};
}}
QMessageBox QPushButton {{
    background-color: {ACCENT_BLUE_HOVER};
    color: #ffffff;
    border: 1px solid {ACCENT_BLUE};
    border-radius: 6px;
    margin: 0px;
    padding: 4px 12px;
    min-height: 26px;
    font-size: 13px;
    font-weight: 500;
}}
QMessageBox QPushButton:hover {{
    background-color: {ACCENT_BLUE};
    color: #ffffff;
}}
QMessageBox QPushButton:pressed {{
    background-color: {ACCENT_BLUE_PRESSED};
    color: #ffffff;
}}

"""


# =============================================================================
# UPLOAD DROP ZONE
# =============================================================================
DROP_AREA_BORDER_LIGHT_NORMAL = "#94a3b8"
DROP_AREA_BORDER_LIGHT_DRAG = "#3b82f6"
DROP_AREA_BORDER_DARK_NORMAL = "#8b949e"
DROP_AREA_BORDER_DARK_DRAG = "#79b8ff"
DROP_AREA_MIN_HEIGHT_PX = 216


def drop_area_normal_style() -> str:
    if CURRENT_THEME == "dark":
        return (
            f"QFrame#drop_area {{ border: 1.5px dashed {DROP_AREA_BORDER_DARK_NORMAL}; border-radius: 8px; "
            "background-color: #21262d; }"
        )
    return (
        f"QFrame#drop_area {{ border: 1.5px dashed {DROP_AREA_BORDER_LIGHT_NORMAL}; border-radius: 8px; "
        "background-color: #e4e6ea; }"
    )


def drop_area_drag_style() -> str:
    if CURRENT_THEME == "dark":
        return (
            f"QFrame#drop_area {{ border: 1.5px dashed {DROP_AREA_BORDER_DARK_DRAG}; border-radius: 8px; "
            "background-color: #1c2128; }"
        )
    return (
        f"QFrame#drop_area {{ border: 1.5px dashed {DROP_AREA_BORDER_LIGHT_DRAG}; border-radius: 8px; "
        "background-color: #dbeafe; }"
    )


# =============================================================================
# HELPERS — TAB LAYOUT (hero, scroll, section cards)
# =============================================================================
def refresh_hero_cards(root: QWidget) -> None:
    """Re-apply hero QFrame#heroCard and title labels after set_theme."""
    for card in root.findChildren(QFrame):
        if card.objectName() != "heroCard":
            continue
        card.setStyleSheet(
            f"QFrame#heroCard {{ background-color: {HERO_CARD_BG}; border: 1px solid {HERO_CARD_BORDER}; "
            f"border-radius: 12px; }}"
        )
        for lb in card.findChildren(QLabel):
            if lb.objectName() == "heroTitleLabel":
                lb.setStyleSheet(TITLE_STYLE)
            elif lb.objectName() == "heroSubtitleLabel":
                lb.setStyleSheet(SUBTITLE_STYLE)


def configure_tab_scroll_area(scroll: QScrollArea) -> None:
    """Frameless QScrollArea; viewport background = MAIN_BG."""
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    vp = scroll.viewport()
    vp.setAutoFillBackground(True)
    vp.setStyleSheet(f"background-color: {MAIN_BG};")


def refresh_scroll_content_margins(
    scroll: QScrollArea,
    content_layout: QVBoxLayout,
    footer_layout: QVBoxLayout | None = None,
) -> None:
    """Tighten horizontal padding when content fits; add extra left when v-scrollbar is active."""
    vsb = scroll.verticalScrollBar()
    m = SCROLL_CONTENT_MARGINS_VSCROLL if vsb.maximum() > 0 else SCROLL_CONTENT_MARGINS_NO_VSCROLL
    content_layout.setContentsMargins(*m)
    if footer_layout is not None:
        ml, _mt, mr, _mb = m
        footer_layout.setContentsMargins(ml, 6, mr, 8)


class _ScrollViewportMarginFilter(QObject):
    """Resize event → refresh_scroll_content_margins (+ optional footer sync)."""

    def __init__(
        self,
        scroll: QScrollArea,
        content_layout: QVBoxLayout,
        footer_layout: QVBoxLayout | None = None,
    ):
        super().__init__(scroll)
        self._scroll = scroll
        self._layout = content_layout
        self._footer_layout = footer_layout

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if event.type() == QEvent.Type.Resize:
            refresh_scroll_content_margins(self._scroll, self._layout, self._footer_layout)
        return False


def wire_scroll_content_margins(
    scroll: QScrollArea,
    content_layout: QVBoxLayout,
    footer_layout: QVBoxLayout | None = None,
) -> None:
    """Connect scrollbar range + viewport resize to refresh_scroll_content_margins."""
    refresh_scroll_content_margins(scroll, content_layout, footer_layout)
    scroll.verticalScrollBar().rangeChanged.connect(
        lambda *_: refresh_scroll_content_margins(scroll, content_layout, footer_layout)
    )
    filt = _ScrollViewportMarginFilter(scroll, content_layout, footer_layout)
    scroll.viewport().installEventFilter(filt)
    scroll._pta_scroll_margin_filter = filt  # noqa: SLF001 — keep QObject alive
    QTimer.singleShot(0, lambda: refresh_scroll_content_margins(scroll, content_layout, footer_layout))
    QTimer.singleShot(80, lambda: refresh_scroll_content_margins(scroll, content_layout, footer_layout))


def create_header_widget(parent: QWidget, title: str, subtitle: str) -> QWidget:
    """QFrame#heroCard with title + subtitle."""
    card = QFrame(parent)
    card.setObjectName("heroCard")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    card.setStyleSheet(
        f"QFrame#heroCard {{ background-color: {HERO_CARD_BG}; border: 1px solid {HERO_CARD_BORDER}; border-radius: 12px; }}"
    )
    shadow = QGraphicsDropShadowEffect(card)
    if CURRENT_THEME == "light":
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(15, 23, 42, 55))
    else:
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 95))
    card.setGraphicsEffect(shadow)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 18, 22, 20)
    layout.setSpacing(4)

    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    title_lb = QLabel(title)
    title_lb.setObjectName("heroTitleLabel")
    title_lb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    title_lb.setStyleSheet(TITLE_STYLE)
    title_lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    layout.addWidget(title_lb)

    sub_lb = QLabel(subtitle)
    sub_lb.setObjectName("heroSubtitleLabel")
    sub_lb.setWordWrap(True)
    sub_lb.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    sub_lb.setStyleSheet(SUBTITLE_STYLE)
    sub_lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    layout.addWidget(sub_lb)

    return card


def _apply_section_card_shadow(widget: QWidget) -> None:
    """Soft elevation; works cleanly when the card paints rounded alpha (SectionCardFrame)."""
    eff = QGraphicsDropShadowEffect(widget)
    if CURRENT_THEME == "light":
        eff.setBlurRadius(36)
        eff.setOffset(0, 10)
        eff.setColor(QColor(15, 23, 42, 52))
    else:
        eff.setBlurRadius(32)
        eff.setOffset(0, 8)
        eff.setColor(QColor(0, 0, 0, 95))
    widget.setGraphicsEffect(eff)


def _apply_section_card_chrome(card: QFrame) -> None:
    """Theme colors + shadow for section cards."""
    if isinstance(card, SectionCardFrame):
        card.setStyleSheet("")
        card.set_theme_card(SECTION_CARD_BG, SECTION_CARD_BORDER, SECTION_CARD_RADIUS_PX)
        _apply_section_card_shadow(card)
    else:
        card.setGraphicsEffect(None)
        card.setStyleSheet(
            f"QFrame#sectionCard {{ background-color: {SECTION_CARD_BG}; border: 1px solid {SECTION_CARD_BORDER}; "
            f"border-radius: {SECTION_CARD_RADIUS_PX}px; }}"
        )


def create_section_card(parent: QWidget, title: str) -> tuple[QWidget, QVBoxLayout]:
    """Returns (outer wrapper, inner QVBoxLayout of QFrame#sectionCard)."""
    outer = QWidget(parent)
    outer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    col = QVBoxLayout(outer)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(10)

    title_lb = QLabel(title)
    title_lb.setObjectName("sectionCardTitle")
    title_lb.setStyleSheet(SECTION_TITLE_STYLE)
    title_lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    col.addWidget(title_lb)

    card = SectionCardFrame(outer)
    _apply_section_card_chrome(card)
    inner = QVBoxLayout(card)
    inner.setContentsMargins(*SECTION_CARD_CONTENT_MARGINS)
    inner.setSpacing(10)
    col.addWidget(card)
    return outer, inner


def refresh_section_cards(root: QWidget) -> None:
    """Re-apply QFrame#sectionCard chrome and sectionCardTitle after set_theme."""
    for card in root.findChildren(QFrame):
        if card.objectName() == "sectionCard":
            _apply_section_card_chrome(card)
    for lb in root.findChildren(QLabel):
        if lb.objectName() == "sectionCardTitle":
            lb.setStyleSheet(SECTION_TITLE_STYLE)


# =============================================================================
# HELPERS — TABLES
# =============================================================================
def sync_data_table_height(table: QTableWidget) -> None:
    """Set #dataTable height to header + rows (capped); scroll inside table when tall."""
    hdr = table.horizontalHeader()
    if hdr is None:
        return
    header_h = hdr.height() if hdr.isVisible() and hdr.height() > 0 else int(hdr.sizeHint().height())
    vh = table.verticalHeader()
    row_default = max(int(vh.defaultSectionSize()), 1)
    rows = table.rowCount()
    body_h = 0
    for r in range(rows):
        rh = table.rowHeight(r)
        body_h += rh if rh > 0 else row_default
    min_empty = int(getattr(table, "_pta_min_empty_body_rows", 0) or 0)
    if rows == 0 and min_empty > 0:
        body_h = row_default * min_empty
    h_sb = table.horizontalScrollBar()
    extra = int(h_sb.height()) if h_sb.isVisible() else 0
    total = header_h + body_h + extra + 2
    table.setFixedHeight(min(total, DATA_TABLE_MAX_VIEW_HEIGHT))
    table.updateGeometry()


def sync_card_style_table_height(table: QTableWidget) -> None:
    """#cardDataTable: height = header + body (min viewport when empty); internal scroll when tall."""
    hdr = table.horizontalHeader()
    if hdr is None:
        return
    header_h = hdr.height() if hdr.isVisible() and hdr.height() > 0 else int(hdr.sizeHint().height())
    vh = table.verticalHeader()
    row_default = max(int(vh.defaultSectionSize()), RECENT_UPLOADS_ROW_HEIGHT_PX)
    rows = table.rowCount()
    body_h = 0
    for r in range(rows):
        rh = table.rowHeight(r)
        body_h += rh if rh > 0 else row_default
    min_vp = int(getattr(table, "_pta_min_body_viewport_px", RECENT_UPLOADS_MIN_BODY_VIEWPORT_PX))
    if rows == 0:
        body_h = max(body_h, min_vp)
    elif getattr(table, "_pta_enforce_min_body_when_filled", False):
        # Saved frameworks (etc.): min viewport applies whenever rows exist but sum(row heights) is smaller.
        body_h = max(body_h, min_vp)
    h_sb = table.horizontalScrollBar()
    extra = int(h_sb.height()) if h_sb is not None and h_sb.isVisible() else 0
    total = header_h + body_h + extra + 2
    max_cap = int(getattr(table, "_pta_max_view_height_px", DATA_TABLE_MAX_VIEW_HEIGHT))
    if getattr(table, "_pta_no_internal_vscroll", False):
        max_cap = 1_000_000
    elif rows == 0:
        # Default cap (380px) must not clip empty-state min viewport (configure_card_style_table).
        max_cap = max(max_cap, total)
    table.setFixedHeight(min(total, max_cap))
    table.updateGeometry()
    apply_card_style_table_viewport_style(table)


def apply_card_style_table_viewport_style(table: QTableWidget) -> None:
    """Viewport palette + ptaLightBody property (light theme empty vs filled body)."""
    if CURRENT_THEME == "light":
        table.setProperty("ptaLightBody", "empty" if table.rowCount() == 0 else "filled")
    else:
        table.setProperty("ptaLightBody", None)

    st = table.style()
    if st is not None:
        st.unpolish(table)
        st.polish(table)

    if CURRENT_THEME == "dark":
        bg_hex = RECENT_UPLOADS_TABLE_BG
    elif table.rowCount() == 0:
        bg_hex = RECENT_UPLOADS_TABLE_BG
    else:
        bg_hex = CARD_TABLE_LIGHT_BODY_FILLED

    c = QColor(bg_hex)
    vp = table.viewport()
    if vp is None:
        return
    pal = vp.palette()
    pal.setColor(QPalette.ColorRole.Base, c)
    pal.setColor(QPalette.ColorRole.Window, c)
    vp.setPalette(pal)
    vp.setAutoFillBackground(True)
    vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    vp.setStyleSheet(f"background-color: {bg_hex}; border: none;")


def configure_data_table(table: QTableWidget, *, min_empty_body_rows: int = 0) -> None:
    """Configure #dataTable: delegate, scroll, height sync. min_empty_body_rows: phantom rows when empty."""
    table.setObjectName("dataTable")
    table.setShowGrid(True)
    table.setAlternatingRowColors(False)
    table.setItemDelegate(DataTableFirstColumnEdgeDelegate(table))
    table.setGraphicsEffect(None)
    table._pta_min_empty_body_rows = max(0, int(min_empty_body_rows))
    table.setMinimumHeight(0)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    hh = table.horizontalHeader()
    if hh is not None:
        hh.setStretchLastSection(True)
    sync_data_table_height(table)


def configure_card_style_table(
    table: QTableWidget,
    *,
    min_empty_viewport_px: int | None = None,
    enforce_min_body_when_filled: bool = False,
    max_view_height_px: int | None = None,
) -> None:
    """Configure #cardDataTable.

    min_empty_viewport_px: minimum body viewport height when empty (None = default).
    enforce_min_body_when_filled: if True, body height is at least that minimum even when rows exist
        (e.g. Saved frameworks should stay tall with one short row).
    max_view_height_px: cap table total height before internal scroll (None = DATA_TABLE_MAX_VIEW_HEIGHT).
    """
    table.setObjectName("cardDataTable")
    table.setShowGrid(True)
    table.setAlternatingRowColors(False)
    table.setItemDelegate(QStyledItemDelegate(table))
    table.setGraphicsEffect(None)
    table._pta_min_body_viewport_px = (
        int(min_empty_viewport_px)
        if min_empty_viewport_px is not None
        else RECENT_UPLOADS_MIN_BODY_VIEWPORT_PX
    )
    table._pta_enforce_min_body_when_filled = bool(enforce_min_body_when_filled)
    if max_view_height_px is not None:
        table._pta_max_view_height_px = int(max_view_height_px)
    elif hasattr(table, "_pta_max_view_height_px"):
        delattr(table, "_pta_max_view_height_px")
    vh = table.verticalHeader()
    vh.setDefaultSectionSize(RECENT_UPLOADS_ROW_HEIGHT_PX)
    table.setMinimumHeight(0)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    hh = table.horizontalHeader()
    if hh is not None:
        hh.setStretchLastSection(True)
    sync_card_style_table_height(table)
    apply_card_style_table_viewport_style(table)
    QTimer.singleShot(0, lambda: sync_card_style_table_height(table))
    QTimer.singleShot(0, lambda: apply_card_style_table_viewport_style(table))


sync_recent_uploads_table_height = sync_card_style_table_height
apply_recent_uploads_table_viewport_style = apply_card_style_table_viewport_style
configure_recent_uploads_table = configure_card_style_table


# =============================================================================
# HELPERS — SELECT BOOK ROW
# =============================================================================
def select_book_row_label_style() -> str:
    """SECTION_LABEL_STYLE at 14px for 'Select Book:' (call after set_theme; reads current SECTION_LABEL_STYLE)."""
    return SECTION_LABEL_STYLE.replace("font-size: 13px", "font-size: 14px")


def create_select_book_row(parent: QWidget) -> "tuple[QLabel, QComboBox, QPushButton]":
    """Label + QComboBox + Refresh (BTN_SECONDARY_SMALL)."""
    label = QLabel("Select Book:")
    label.setStyleSheet(select_book_row_label_style())
    label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    combo = QComboBox()
    combo.setStyleSheet(COMBO_STYLE)
    combo.setMinimumWidth(320)
    combo.setMaximumWidth(720)
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
    combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    btn = QPushButton("Refresh")
    btn.setStyleSheet(BTN_SECONDARY_SMALL)
    return label, combo, btn


from ..core.app_config import get_ui_theme as _get_ui_theme  # noqa: E402 — after theme helpers

set_theme(_get_ui_theme())
