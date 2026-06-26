import html
import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit,
    QMessageBox,
    QApplication,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QFrame,
    QMenu,
    QSplitter,
    QToolButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer, QSize, QRectF, QPointF, QEvent, QObject, QUrl
from PyQt6.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShowEvent,
)

from src.api import service

from ..core.book_manager import BookManager
from .styles import (
    CHAT_HISTORY_DOC_STYLESHEET,
    CHAT_HISTORY_TEXTEDIT_STYLE,
    MUTED_LABEL_STYLE,
    TEXTEDIT_SMALL_STYLE,
    create_header_widget,
    create_select_book_row,
    configure_tab_scroll_area,
    refresh_scroll_content_margins,
    refresh_section_cards,
    refresh_hero_cards,
    wire_scroll_content_margins,
    TAB_MARGINS,
    TAB_SPACING,
    BTN_SECONDARY,
    BTN_SECONDARY_SMALL,
    CHAT_BTN_HEIGHT_CLAMP,
)
from .collapsible import CollapsibleSection

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    _CHAT_WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None  # type: ignore[misc, assignment]
    QWebEngineSettings = None  # type: ignore[misc, assignment]
    _CHAT_WEBENGINE_AVAILABLE = False

CHAT_RAIL_DEFAULT_WIDTH_PX = 288
# Minimum splitter width: icon stays inside the rail (ChatGPT-style strip).
CHAT_RAIL_STRIP_WIDTH_PX = 46
# Below this width the rail shows only the sidebar control (list + New chat hidden).
CHAT_RAIL_EXPAND_THRESHOLD_PX = 120
CHAT_QSETTINGS_ORG = "ProperThinkingAI"
CHAT_QSETTINGS_APP = "ProperThinkingAI"
# Send control: smaller footprint so the composer bar height isn’t driven by this button.
CHAT_SEND_BUTTON_PX = 26
# Arrow geometry inside the circle (leave margin for a bold stroke).
SEND_ARROW_INNER_SCALE = 0.76


def _make_sidebar_panel_icon(stroke: QColor, size: int = 24) -> QIcon:
    """Rounded panel + vertical divider — sidebar affordance (theme-colored stroke)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(stroke, 1.25)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    m = 3.5
    span = float(size) - 2.0 * m
    p.drawRoundedRect(QRectF(m, m, span, span), 3.0, 3.0)
    split_x = m + span * 0.28
    p.drawLine(int(split_x), int(m + 1.5), int(split_x), int(size - m - 1.5))
    p.end()
    return QIcon(pm)


def _make_send_composite_icon(size: int, *, enabled: bool, hover: bool) -> QIcon:
    """Single pixmap: green circle + white arrow (ChatGPT-style). Always paints reliably on Windows."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not enabled:
        bg = QColor("#94a3b8")
        fg = QColor("#f8fafc")
    elif hover:
        bg = QColor("#16a34a")
        fg = QColor("#ffffff")
    else:
        bg = QColor("#22c55e")
        fg = QColor("#ffffff")
    p.setBrush(bg)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, size - 1, size - 1)
    ar = SEND_ARROW_INNER_SCALE
    # Bolder stroke; capped so the stroke stays inside the green circle at small sizes.
    stroke_w = max(2.1, min(3.0, size * 0.108))
    pen = QPen(fg, stroke_w)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    cx = size * 0.5
    # Shaft + chevron scaled toward center (smaller inner arrow, same outer circle).
    mid_shaft = 0.53
    half_shaft = 0.19 * ar
    p.drawLine(
        QPointF(cx, (mid_shaft + half_shaft) * size),
        QPointF(cx, (mid_shaft - half_shaft) * size),
    )
    mid_head_y, half_head_h, half_w = 0.29, 0.13 * ar, 0.24 * ar
    tip_y = (mid_head_y - half_head_h) * size
    base_y = (mid_head_y + half_head_h) * size
    hw = half_w * size
    head = QPainterPath()
    head.moveTo(cx - hw, base_y)
    head.lineTo(cx, tip_y)
    head.lineTo(cx + hw, base_y)
    p.drawPath(head)
    p.end()
    return QIcon(pm)


class _SendHoverFilter(QObject):
    """Darker green composite icon on hover (no QSS-only hover — icon is self-drawn)."""

    def __init__(self, tab: "ChatTab"):
        super().__init__(tab)
        self._tab = tab

    def eventFilter(self, obj, event) -> bool:  # type: ignore[override]
        if obj is self._tab.ask_button:
            if event.type() == QEvent.Type.Enter:
                self._tab._send_hover = True
                self._tab._refresh_send_button_icon()
            elif event.type() == QEvent.Type.Leave:
                self._tab._send_hover = False
                self._tab._refresh_send_button_icon()
        return False


def _chat_msg_gap_html() -> str:
    """Vertical gap between turns — no border (replaces old .chat-separator rules)."""
    return '<div class="chat-msg-spacer"></div>'


def _wrap_chat_history_page(body_fragment: str) -> str:
    """Full HTML document for QWebEngineView — real CSS (border-radius) unlike QTextDocument HTML."""
    from .styles import (
        CHAT_HISTORY_DOC_STYLESHEET,
        CHAT_INSET_BG,
        CHAT_USER_BUBBLE_BG,
        CHAT_USER_BUBBLE_FG,
        CHAT_USER_BUBBLE_BORDER,
    )

    # WebEngine uses browser defaults (serif headings, tight lists) unless reset. QTextEdit inherited app font.
    # Match QTextEdit document margin (12px); extra right padding so bubbles clear the scrollbar gutter.
    web_engine_reset_css = f"""
    html, body {{
      margin: 0;
      box-sizing: border-box;
      background-color: {CHAT_INSET_BG};
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
      font-size: 13px;
      line-height: 1.45;
      -webkit-font-smoothing: antialiased;
      padding: 12px 16px 12px 12px;
    }}
    h1, h2, h3, h4, h5, h6 {{
      font-family: inherit !important;
      font-weight: 600;
    }}
    p.chat-assistant-label {{
      margin: 0 0 8px 0 !important;
      padding: 0 !important;
      font-size: 13px;
      line-height: 1.35;
    }}
    .assistant-body {{
      line-height: 1.45;
    }}
    .assistant-body p {{
      margin: 0 0 6px 0;
    }}
    .assistant-body p:last-child {{
      margin-bottom: 0;
    }}
    .assistant-body ul {{
      margin: 4px 0 8px 0;
      padding-left: 20px;
    }}
    .assistant-body li {{
      margin: 4px 0;
      line-height: 1.45;
    }}
    .assistant-body h2, .assistant-body h3 {{
      font-family: inherit !important;
    }}
    table {{
      border-collapse: collapse;
    }}
    .chat-msg-spacer {{
      height: 10px;
      margin: 0;
      padding: 0;
      border: none;
      clear: both;
    }}
    .chat-separator {{
      display: none !important;
      border: none !important;
      margin: 0 !important;
      height: 0 !important;
    }}
    """

    bubble_css = f"""
    .user-msg-row {{ text-align: right; margin: 6px 0; clear: both; width: 100%; }}
    .user-bubble {{
      display: inline-block;
      max-width: 88%;
      text-align: left;
      box-sizing: border-box;
      background-color: {CHAT_USER_BUBBLE_BG};
      color: {CHAT_USER_BUBBLE_FG};
      border: 1px solid {CHAT_USER_BUBBLE_BORDER};
      padding: 5px 10px;
      border-radius: 12px;
      word-wrap: break-word;
      overflow-wrap: anywhere;
      font-family: inherit;
      font-size: 13px;
      line-height: 1.45;
    }}
    """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
{CHAT_HISTORY_DOC_STYLESHEET}
{web_engine_reset_css}
{bubble_css}
</style></head><body>{body_fragment}</body></html>"""


def _strip_color_styles_from_chat_html(html_str: str) -> str:
    def _clean_style(m: re.Match) -> str:
        style = m.group(1)
        parts_out: list[str] = []
        for p in style.split(";"):
            p = p.strip()
            if not p or ":" not in p:
                continue
            prop = p.split(":", 1)[0].strip().lower()
            if prop == "color":
                continue
            parts_out.append(p)
        if not parts_out:
            return ""
        return f' style="{"; ".join(parts_out)}"'

    return re.sub(r'\sstyle="([^"]*)"', _clean_style, html_str)


def _inline_markdown_to_html(s: str) -> str:
    if not s:
        return ""
    parts = re.split(r"(\*\*.+?\*\*)", s, flags=re.DOTALL)
    chunks: list[str] = []
    for p in parts:
        if len(p) >= 4 and p.startswith("**") and p.endswith("**"):
            inner = html.escape(p[2:-2])
            chunks.append(f"<b>{inner}</b>")
        else:
            chunks.append(html.escape(p))
    return "".join(chunks)


def _normalize_sources_newline(text: str) -> str:
    return re.sub(r"([^\n\r])(\s*Sources\s*:)", r"\1\n\2", text, flags=re.IGNORECASE)


def _strip_trailing_sources_line(text: str) -> str:
    return re.sub(
        r"\n?\s*Sources\s*:\s*Pages\s*[\d,\s]+\s*$",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )


def _markdown_answer_to_html(text: str) -> str:
    text = _normalize_sources_newline(text)
    lines = text.split("\n")
    out: list[str] = []
    in_ul = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<br/>")
            continue
        if stripped.startswith("### "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h3>{_inline_markdown_to_html(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{_inline_markdown_to_html(stripped[3:])}</h2>")
        elif stripped.startswith("# ") and not stripped.startswith("##"):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append(f"<h2>{_inline_markdown_to_html(stripped[2:])}</h2>")
        elif stripped.startswith("- "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_markdown_to_html(stripped[2:])}</li>")
        elif stripped.startswith("* ") and not stripped.startswith("**"):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline_markdown_to_html(stripped[2:])}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if re.match(r"(?i)^sources\s*:", stripped):
                out.append(
                    f'<div class="chat-sources chat-sources-block">{_inline_markdown_to_html(stripped)}</div>'
                )
            else:
                out.append(f"<p>{_inline_markdown_to_html(stripped)}</p>")
    if in_ul:
        out.append("</ul>")
    return _tighten_chat_html_fragment("".join(out))


def _tighten_chat_html_fragment(html: str) -> str:
    html = re.sub(r"</ul>\s*<br/>\s*<h", r"</ul><h", html)
    html = re.sub(r"</h2>\s*<br/>\s*<h2", r"</h2><h2", html)
    html = re.sub(r"</h3>\s*<br/>\s*<h2", r"</h3><h2", html)
    html = re.sub(r"</h2>\s*<br/>\s*<h3", r"</h2><h3", html)
    html = re.sub(r"</h3>\s*<br/>\s*<h3", r"</h3><h3", html)
    html = re.sub(r"(<br/>\s*){2,}", r"<br/>", html)
    return html


def _conversation_title_from_question(q: str, max_len: int = 48) -> str:
    t = (q or "").strip().replace("\n", " ")
    if not t:
        return "New chat"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


class LLMWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, book_id: int, question: str):
        super().__init__()
        self.book_id = book_id
        self.question = question

    def run(self):
        try:
            result = service.answer_question(self.book_id, self.question)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class ChatComposer(QTextEdit):
    """Multiline composer: Enter sends, Shift+Enter newline."""

    sendRequested = pyqtSignal()
    # Match styles.CHAT_COMPOSER_PADDING vertical total (e.g. 4px + 4px in light theme).
    _PAD_Y = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("chatComposerInput")
        self.setAcceptRichText(False)
        self.setPlaceholderText("Message… (Shift+Enter for new line)")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMaximumHeight(120)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.document().contentsChanged.connect(self._on_document_contents_changed)

    def _line_height(self) -> int:
        return max(16, self.fontMetrics().lineSpacing())

    def minimumSizeHint(self) -> QSize:
        # QTextEdit defaults to ~3 lines here; force a single-line minimum.
        h = self._line_height() + self._PAD_Y
        return QSize(120, min(h, self.maximumHeight()))

    def sizeHint(self) -> QSize:
        layout = self.document().documentLayout()
        doc_h = float(layout.documentSize().height()) if layout is not None else 0.0
        line = float(self._line_height())
        content_h = max(line, doc_h)
        h = int(content_h) + self._PAD_Y
        h = max(self.minimumSizeHint().height(), min(h, self.maximumHeight()))
        w = max(120, self.width()) if self.width() > 0 else 200
        return QSize(w, h)

    def _on_document_contents_changed(self) -> None:
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.updateGeometry()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.sendRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ChatTab(QWidget):
    def __init__(self, book_manager: BookManager, parent: Optional[QWidget] = None):
        super().__init__(parent)
        # Same BookManager as ``service`` after ``MainWindow`` calls ``service.bind_book_manager``.
        self.book_manager = book_manager
        self.selected_book_id: Optional[int] = None
        self._current_conversation_id: Optional[int] = None
        self._chat_history_web: bool = bool(_CHAT_WEBENGINE_AVAILABLE and QWebEngineView is not None)
        self.worker_thread: Optional[LLMWorker] = None
        self._saved_rail_width = CHAT_RAIL_DEFAULT_WIDTH_PX
        self._send_hover = False
        self._last_chat_placeholder_text = "Select a conversation or start a new chat."
        self._init_ui()
        self.apply_theme()
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
                "Chat",
                "Ask questions about the selected book. Answers use only the book's content.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        self._book_label, self.book_combo, self.refresh_button = create_select_book_row(self)
        self.book_combo.currentIndexChanged.connect(self._on_book_selected)
        self.refresh_button.clicked.connect(self._load_books)
        book_selector_row = QHBoxLayout()
        book_selector_row.addWidget(self._book_label, 0)
        book_selector_row.addWidget(self.book_combo, 0)
        book_selector_row.addStretch(1)
        book_selector_row.addWidget(self.refresh_button, 0)
        content_layout.addLayout(book_selector_row)

        self.empty_state_label = QLabel("Please generate embeddings for a book to start chat.")
        self.empty_state_label.setStyleSheet(MUTED_LABEL_STYLE)
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.setWordWrap(True)
        content_layout.addWidget(self.empty_state_label)

        self._chat_workspace = QWidget()
        self._chat_workspace.setMinimumHeight(400)
        chat_ws_layout = QHBoxLayout(self._chat_workspace)
        chat_ws_layout.setContentsMargins(0, 0, 0, 0)
        chat_ws_layout.setSpacing(0)

        self._chat_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._chat_splitter.setObjectName("chatWorkspaceSplitter")
        self._chat_splitter.setHandleWidth(10)
        self._chat_splitter.splitterMoved.connect(self._on_splitter_moved)

        rail = QFrame()
        rail.setObjectName("chatThreadRail")
        rail.setMinimumWidth(CHAT_RAIL_STRIP_WIDTH_PX)
        rail.setMaximumWidth(480)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(8, 8, 8, 8)
        rail_layout.setSpacing(8)
        rail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._rail_toggle = QToolButton()
        self._rail_toggle.setObjectName("chatRailToggle")
        self._rail_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._rail_toggle.setToolTip("Collapse conversation list")
        self._rail_toggle.setFixedSize(28, 28)
        self._rail_toggle.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._rail_toggle.setAutoRaise(True)
        self._rail_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rail_toggle.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._rail_toggle.clicked.connect(self._on_rail_toggle_clicked)

        # QWidget wrapper so we can use addWidget(..., AlignTop); PyQt6 QVBoxLayout.addLayout
        # has no alignment parameter (unlike Qt C++).
        rail_toggle_row = QWidget()
        rail_header = QHBoxLayout(rail_toggle_row)
        rail_header.setContentsMargins(0, 0, 0, 0)
        rail_header.setSpacing(0)
        # When compact, this row is the only visible cell; keep children top-aligned so the
        # toggle does not vertically center in the full rail height.
        rail_header.setAlignment(Qt.AlignmentFlag.AlignTop)
        rail_header.addWidget(self._rail_toggle, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        rail_layout.addWidget(rail_toggle_row, 0, Qt.AlignmentFlag.AlignTop)

        self.new_chat_btn = QPushButton("New chat")
        self.new_chat_btn.setObjectName("chatNewChatBtn")
        self.new_chat_btn.clicked.connect(self._on_new_chat_clicked)
        rail_layout.addWidget(self.new_chat_btn)
        rail_layout.addSpacing(12)

        self.thread_list = QListWidget()
        self.thread_list.setObjectName("chatThreadList")
        self.thread_list.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.thread_list.setUniformItemSizes(True)
        self.thread_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thread_list.currentItemChanged.connect(self._on_thread_item_changed)
        self.thread_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.thread_list.customContextMenuRequested.connect(self._on_thread_context_menu)
        rail_layout.addWidget(self.thread_list, stretch=1)

        self._chat_splitter.addWidget(rail)
        main_panel = QFrame()
        main_panel.setObjectName("chatMainPanel")
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        if self._chat_history_web and QWebEngineView is not None and QWebEngineSettings is not None:
            self.chat_history = QWebEngineView()
            self.chat_history.setObjectName("chatHistoryWebView")
            self.chat_history.setMinimumHeight(280)
            self.chat_history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.chat_history.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.chat_history.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.chat_history.setStyleSheet(CHAT_HISTORY_TEXTEDIT_STYLE)
            ws = self.chat_history.settings()
            ws.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            ws.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            ws.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
            from .styles import CHAT_INSET_BG

            self.chat_history.page().setBackgroundColor(QColor(CHAT_INSET_BG))
        else:
            self.chat_history = QTextEdit()
            self.chat_history.setObjectName("chatHistoryTextEdit")
            self.chat_history.setReadOnly(True)
            self.chat_history.setMinimumHeight(280)
            self.chat_history.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.chat_history.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.chat_history.setStyleSheet(CHAT_HISTORY_TEXTEDIT_STYLE)
            self.chat_history.document().setDocumentMargin(12)
            self.chat_history.document().setDefaultStyleSheet(CHAT_HISTORY_DOC_STYLESHEET)
        main_layout.addWidget(self.chat_history, stretch=1)

        self.process_section = CollapsibleSection("How this answer was produced")
        self.process_view = QTextEdit()
        self.process_view.setReadOnly(True)
        self.process_view.setMinimumHeight(100)
        self.process_view.setStyleSheet(TEXTEDIT_SMALL_STYLE)
        self.process_section.content_layout.addWidget(self.process_view)
        self._update_process_view([])
        main_layout.addWidget(self.process_section)

        composer_bar = QFrame()
        composer_bar.setObjectName("chatComposerBar")
        composer_bar.setMinimumHeight(40)
        composer_row = QHBoxLayout(composer_bar)
        composer_row.setContentsMargins(10, 6, 10, 6)
        composer_row.setSpacing(6)

        self.question_input = ChatComposer()
        self.question_input.sendRequested.connect(self._on_ask_clicked)
        self.question_input.setEnabled(False)
        composer_row.addWidget(self.question_input, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

        # QPushButton + icon + QSS background: QToolButton often fails to paint the icon
        # when a stylesheet sets background (especially on Windows).
        self.ask_button = QPushButton()
        self.ask_button.setObjectName("chatSendButton")
        self.ask_button.setText("")
        self.ask_button.setToolTip("Send")
        self.ask_button.setFixedSize(CHAT_SEND_BUTTON_PX, CHAT_SEND_BUTTON_PX)
        self.ask_button.setIconSize(QSize(CHAT_SEND_BUTTON_PX, CHAT_SEND_BUTTON_PX))
        self.ask_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ask_button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.ask_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ask_button.setAutoDefault(False)
        self.ask_button.setDefault(False)
        self.ask_button.setFlat(False)
        self.ask_button.clicked.connect(self._on_ask_clicked)
        self._send_hover_filter = _SendHoverFilter(self)
        self.ask_button.installEventFilter(self._send_hover_filter)
        self._set_send_enabled(False)
        composer_row.addWidget(self.ask_button, 0, Qt.AlignmentFlag.AlignVCenter)

        main_layout.addWidget(composer_bar)
        self._chat_splitter.addWidget(main_panel)
        # Must add widgets before setCollapsible — otherwise Qt warns "index out of range"
        self._chat_splitter.setCollapsible(0, True)
        self._chat_splitter.setCollapsible(1, False)
        self._chat_splitter.setStretchFactor(0, 0)
        self._chat_splitter.setStretchFactor(1, 1)

        chat_ws_layout.addWidget(self._chat_splitter, stretch=1)

        content_layout.addWidget(self._chat_workspace)

        scroll.setWidget(content)
        self._scroll_area = scroll
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
        self._set_chat_placeholder()

    def _set_chat_history_body(self, body_fragment: str) -> None:
        """Load transcript HTML; WebEngine path wraps with full CSS (real border-radius on user bubbles)."""
        if self._chat_history_web:
            full = _wrap_chat_history_page(body_fragment)
            self.chat_history.setHtml(full, QUrl("about:blank"))
            QTimer.singleShot(80, self._scroll_chat_to_end)
        else:
            assert isinstance(self.chat_history, QTextEdit)
            self.chat_history.document().setDefaultStyleSheet(CHAT_HISTORY_DOC_STYLESHEET)
            self.chat_history.setHtml(body_fragment)
            self._scroll_chat_to_end()

    def _set_chat_placeholder(self, text: Optional[str] = None) -> None:
        if text is not None:
            self._last_chat_placeholder_text = text
        t = self._last_chat_placeholder_text
        esc = html.escape(t)
        body = f'<p style="text-align:center;opacity:0.55;margin:24px 0;">{esc}</p>'
        self._set_chat_history_body(body)
        if not self._chat_history_web and isinstance(self.chat_history, QTextEdit):
            self.chat_history.setPlaceholderText(t)

    def _refresh_send_button_icon(self) -> None:
        hover = bool(self._send_hover) and self.ask_button.isEnabled()
        self.ask_button.setIcon(
            _make_send_composite_icon(
                CHAT_SEND_BUTTON_PX,
                enabled=self.ask_button.isEnabled(),
                hover=hover,
            )
        )

    def _set_send_enabled(self, enabled: bool) -> None:
        self.ask_button.setEnabled(enabled)
        self._refresh_send_button_icon()

    def _refresh_rail_sidebar_icon(self) -> None:
        from .styles import CURRENT_THEME

        stroke = QColor("#64748b") if CURRENT_THEME == "light" else QColor("#94a3b8")
        self._rail_toggle.setIcon(_make_sidebar_panel_icon(stroke))

    def _update_rail_toggle_appearance(self, compact: bool) -> None:
        self._refresh_rail_sidebar_icon()
        self._rail_toggle.setText("")
        self._rail_toggle.setToolTip(
            "Expand conversation list" if compact else "Collapse conversation list"
        )

    def _sync_rail_compact_ui(self) -> None:
        sz = self._chat_splitter.sizes()
        w = sz[0] if sz else 0
        compact = w < CHAT_RAIL_EXPAND_THRESHOLD_PX
        self.new_chat_btn.setVisible(not compact)
        self.thread_list.setVisible(not compact)
        self._update_rail_toggle_appearance(compact)

    def _restore_rail_state(self) -> None:
        sw = self._chat_splitter.width()
        if sw < 120:
            QTimer.singleShot(0, self._restore_rail_state)
            return
        s = QSettings(CHAT_QSETTINGS_ORG, CHAT_QSETTINGS_APP)
        collapsed = s.value("chat/rail_collapsed", False, type=bool)
        w = s.value("chat/rail_width", CHAT_RAIL_DEFAULT_WIDTH_PX, type=int)
        self._saved_rail_width = max(CHAT_RAIL_EXPAND_THRESHOLD_PX, min(420, int(w)))
        total = max(sw, 400)
        if collapsed:
            self._chat_splitter.setSizes([CHAT_RAIL_STRIP_WIDTH_PX, total - CHAT_RAIL_STRIP_WIDTH_PX])
        else:
            left = min(self._saved_rail_width, total - 200)
            left = max(left, CHAT_RAIL_EXPAND_THRESHOLD_PX)
            self._chat_splitter.setSizes([left, total - left])
        self._sync_rail_compact_ui()

    def _on_rail_toggle_clicked(self) -> None:
        s = QSettings(CHAT_QSETTINGS_ORG, CHAT_QSETTINGS_APP)
        sz = self._chat_splitter.sizes()
        total = max(self._chat_splitter.width(), 400)
        compact = sz[0] < CHAT_RAIL_EXPAND_THRESHOLD_PX
        if compact:
            left = min(self._saved_rail_width, total - 200)
            left = max(left, CHAT_RAIL_EXPAND_THRESHOLD_PX)
            self._chat_splitter.setSizes([left, total - left])
            s.setValue("chat/rail_collapsed", False)
        else:
            self._saved_rail_width = max(sz[0], CHAT_RAIL_EXPAND_THRESHOLD_PX)
            s.setValue("chat/rail_width", self._saved_rail_width)
            self._chat_splitter.setSizes([CHAT_RAIL_STRIP_WIDTH_PX, total - CHAT_RAIL_STRIP_WIDTH_PX])
            s.setValue("chat/rail_collapsed", True)
        self._sync_rail_compact_ui()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self._chat_splitter.sizes()
        if sizes[0] >= CHAT_RAIL_EXPAND_THRESHOLD_PX:
            self._saved_rail_width = sizes[0]
            s = QSettings(CHAT_QSETTINGS_ORG, CHAT_QSETTINGS_APP)
            s.setValue("chat/rail_width", sizes[0])
            s.setValue("chat/rail_collapsed", False)
        self._sync_rail_compact_ui()

    def _refresh_chat_document_theme(self) -> None:
        from .styles import CHAT_HISTORY_DOC_STYLESHEET, CHAT_INSET_BG

        if self._chat_history_web:
            self.chat_history.page().setBackgroundColor(QColor(CHAT_INSET_BG))
            cid = self._current_conversation_id
            if cid is not None:
                self._load_conversation_messages(cid)
            else:
                self._set_chat_placeholder()
            return

        doc = self.chat_history.document()
        doc.setDefaultStyleSheet(CHAT_HISTORY_DOC_STYLESHEET)
        html_str = _strip_color_styles_from_chat_html(self.chat_history.toHtml())
        self.chat_history.setHtml(html_str)

    def apply_theme(self) -> None:
        from .styles import (
            COMBO_STYLE,
            BTN_SECONDARY,
            BTN_SECONDARY_SMALL,
            select_book_row_label_style,
            CHAT_BTN_HEIGHT_CLAMP,
            CHAT_COMPOSER_STYLE,
            CHAT_HISTORY_TEXTEDIT_STYLE,
            configure_tab_scroll_area,
            refresh_scroll_content_margins,
        )

        self._book_label.setStyleSheet(select_book_row_label_style())
        self.book_combo.setStyleSheet(COMBO_STYLE)
        self.refresh_button.setStyleSheet(BTN_SECONDARY_SMALL)
        self.empty_state_label.setStyleSheet(MUTED_LABEL_STYLE)
        self.new_chat_btn.setStyleSheet(BTN_SECONDARY + CHAT_BTN_HEIGHT_CLAMP)
        self._rail_toggle.setStyleSheet("")
        self._refresh_rail_sidebar_icon()
        self.chat_history.setStyleSheet(CHAT_HISTORY_TEXTEDIT_STYLE)
        self._refresh_chat_document_theme()
        self.process_view.setStyleSheet(TEXTEDIT_SMALL_STYLE)
        self.process_section.apply_theme()
        self.question_input.setStyleSheet(CHAT_COMPOSER_STYLE)
        self.ask_button.setStyleSheet("")
        self._refresh_send_button_icon()
        self.status_label.setStyleSheet(MUTED_LABEL_STYLE)
        configure_tab_scroll_area(self._scroll_area)
        refresh_scroll_content_margins(
            self._scroll_area, self._scroll_content_layout, self._footer_layout
        )
        refresh_section_cards(self)
        refresh_hero_cards(self)
        self._sync_rail_compact_ui()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self._load_books()
        QTimer.singleShot(0, self._restore_rail_state)

    def _load_books(self):
        current_selected_id = self.selected_book_id
        self.book_combo.clear()
        try:
            all_books = service.list_books()
            books_with_embeddings = [b for b in all_books if b.get("embeddings_generated", False)]

            if not books_with_embeddings:
                self.empty_state_label.setVisible(True)
                self._chat_workspace.setVisible(False)
                self.selected_book_id = None
                self._current_conversation_id = None
                self.thread_list.clear()
                self._set_chat_placeholder("Select a conversation or start a new chat.")
                self.status_label.setText("No books with embeddings available.")
                return

            self.empty_state_label.setVisible(False)
            self._chat_workspace.setVisible(True)

            for book in books_with_embeddings:
                self.book_combo.addItem(book.get("title", "Untitled"), book.get("id"))

            selected_index = 0
            for idx in range(self.book_combo.count()):
                if self.book_combo.itemData(idx) == current_selected_id:
                    selected_index = idx
                    break
            self.book_combo.setCurrentIndex(selected_index)
            self._on_book_selected(selected_index)
            self.status_label.setText(f"{len(books_with_embeddings)} book(s) available for chat.")
        except Exception as exc:
            self.status_label.setText(f"Error loading books: {exc}")
        finally:
            refresh_scroll_content_margins(
                self._scroll_area, self._scroll_content_layout, self._footer_layout
            )

    def _on_book_selected(self, index: int):
        if index < 0:
            self.selected_book_id = None
            self._current_conversation_id = None
            self.question_input.setEnabled(False)
            self._set_send_enabled(False)
            self.thread_list.clear()
            self._set_chat_placeholder("Select a conversation or start a new chat.")
            self._update_process_view([])
            return

        book_id = self.book_combo.itemData(index)
        if book_id:
            self.selected_book_id = int(book_id)
            self.question_input.setEnabled(True)
            self._set_send_enabled(True)
            self._refresh_thread_list(reload_messages=True)
            book_title = self.book_combo.currentText()
            self.status_label.setText(f"Selected: {book_title}")
        else:
            self.selected_book_id = None
            self._current_conversation_id = None
            self.question_input.setEnabled(False)
            self._set_send_enabled(False)

    def _refresh_thread_list(
        self,
        select_id: Optional[int] = None,
        *,
        reload_messages: bool = False,
    ) -> None:
        self.thread_list.blockSignals(True)
        self.thread_list.clear()
        if not self.selected_book_id:
            self.thread_list.blockSignals(False)
            return
        try:
            convs = service.chat_list_conversations(self.selected_book_id)
        except Exception as exc:
            log.warning("chat_list_conversations: %s", exc)
            self.thread_list.blockSignals(False)
            return

        to_select: Optional[int] = select_id
        if to_select is None and convs:
            to_select = convs[0]["id"]

        fm = self.thread_list.fontMetrics()
        # Match QSS padding + vertical margins on #chatThreadList::item (taller rows, gaps between items).
        row_h = fm.height() + 20
        vw = self.thread_list.viewport().width()
        row_w = max(120, vw - 8) if vw > 0 else 220
        row_size = QSize(row_w, row_h)

        for c in convs:
            title = (c.get("title") or "Chat").strip() or "Chat"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, c["id"])
            item.setSizeHint(row_size)
            self.thread_list.addItem(item)

        if to_select is not None:
            for i in range(self.thread_list.count()):
                it = self.thread_list.item(i)
                if it and it.data(Qt.ItemDataRole.UserRole) == to_select:
                    self.thread_list.setCurrentItem(it)
                    break
        else:
            self._current_conversation_id = None
            self._set_chat_placeholder("Click “New chat” or pick a conversation.")

        self.thread_list.blockSignals(False)

        if reload_messages and to_select is not None:
            self._current_conversation_id = to_select
            self._load_conversation_messages(to_select)

    def _on_thread_item_changed(self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_conversation_id = None
            self._set_chat_placeholder("Click “New chat” or pick a conversation.")
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid is None:
            return
        self._current_conversation_id = int(cid)
        self._load_conversation_messages(self._current_conversation_id)

    def _on_new_chat_clicked(self) -> None:
        if not self.selected_book_id:
            return
        try:
            cid = service.chat_create_conversation(self.selected_book_id, "New chat")
        except Exception as exc:
            QMessageBox.warning(self, "Chat", f"Could not create conversation: {exc}")
            return
        self._refresh_thread_list(select_id=cid, reload_messages=True)

    def _on_thread_context_menu(self, pos) -> None:
        item = self.thread_list.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setObjectName("chatThreadContextMenu")
        del_act = menu.addAction("Delete conversation")
        act = menu.exec(self.thread_list.mapToGlobal(pos))
        if act == del_act and cid is not None:
            self._delete_conversation(int(cid))

    def _delete_conversation(self, cid: int) -> None:
        reply = QMessageBox.question(
            self,
            "Delete conversation",
            "Delete this conversation permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.selected_book_id is None:
            QMessageBox.warning(self, "Chat", "No book selected.")
            return
        try:
            service.chat_delete_conversation(self.selected_book_id, cid)
        except Exception as exc:
            QMessageBox.warning(self, "Chat", str(exc))
            return
        if self._current_conversation_id == cid:
            self._current_conversation_id = None
        self._refresh_thread_list(reload_messages=True)

    def _load_conversation_messages(self, conversation_id: int) -> None:
        try:
            if self.selected_book_id is None:
                raise ValueError("No book selected")
            msgs = service.chat_list_messages(self.selected_book_id, conversation_id)
        except Exception as exc:
            self._set_chat_history_body(f"<p>Error loading messages: {html.escape(str(exc))}</p>")
            return
        html_body = self._messages_to_html(msgs)
        self._set_chat_history_body(html_body)
        last_chunks: List[Dict[str, Any]] = []
        for m in reversed(msgs):
            if m.get("role") == "assistant" and m.get("used_chunks"):
                last_chunks = m["used_chunks"] or []
                break
        self._update_process_view(last_chunks)

    def _messages_to_html(self, msgs: List[Dict[str, Any]]) -> str:
        from .styles import (
            CHAT_USER_BUBBLE_BG,
            CHAT_USER_BUBBLE_FG,
            CHAT_USER_BUBBLE_BORDER,
            CHAT_ASSISTANT_BUBBLE_BG,
            CHAT_ASSISTANT_BUBBLE_FG,
            CHAT_ASSISTANT_BUBBLE_BORDER,
        )

        parts: list[str] = []
        for m in msgs:
            role = m.get("role") or ""
            content = m.get("content") or ""
            used_chunks = m.get("used_chunks")
            status = m.get("status")
            if role == "user":
                safe = html.escape(content).replace("\n", "<br/>")
                if self._chat_history_web:
                    parts.append(
                        f'<div class="user-msg-row"><div class="user-bubble">{safe}</div></div>'
                    )
                else:
                    # QTextDocument does not paint border-radius reliably; table layout still helps alignment.
                    parts.append(
                        '<table width="100%" cellspacing="0" cellpadding="0"><tr><td align="right">'
                        '<table cellspacing="0" cellpadding="0" align="right" style="border-collapse:separate;">'
                        f'<tr><td bgcolor="{CHAT_USER_BUBBLE_BG}" '
                        f'style="color:{CHAT_USER_BUBBLE_FG};border:1px solid {CHAT_USER_BUBBLE_BORDER};'
                        f"padding:5px 10px;border-radius:12px;-qt-border-radius:12px;text-align:left;"
                        f'max-width:88%;">'
                        f"{safe}</td></tr></table></td></tr></table>"
                    )
            elif role == "assistant":
                parts.append(
                    self._assistant_message_fragment(
                        content,
                        used_chunks if isinstance(used_chunks, list) else None,
                        status,
                        CHAT_ASSISTANT_BUBBLE_BG,
                        CHAT_ASSISTANT_BUBBLE_FG,
                        CHAT_ASSISTANT_BUBBLE_BORDER,
                    )
                )
            parts.append(_chat_msg_gap_html())
        return "".join(parts)

    def _assistant_message_fragment(
        self,
        message: str,
        used_chunks: Optional[List[Dict[str, Any]]],
        status: Optional[str],
        bubble_bg: str,
        bubble_fg: str,
        bubble_border: str,
    ) -> str:
        parts: list[str] = []
        if status == "error":
            safe = html.escape(message or "").replace("\n", "<br/>")
            inner = f'<p class="chat-line chat-line-error"><b>Error:</b> {safe}</p>'
        elif status == "not_supported":
            safe = html.escape(message or "").replace("\n", "<br/>")
            inner = f'<p class="chat-line chat-line-warn"><b>Assistant:</b> {safe}</p>'
        else:
            if not message or not str(message).strip():
                message = "The model returned an empty response. Please try rephrasing your question."
            body = str(message)
            if used_chunks:
                body = _strip_trailing_sources_line(body)
            body_html = _markdown_answer_to_html(body)
            inner = (
                '<p class="chat-assistant-label"><b>Assistant:</b></p>'
                f'<div class="assistant-body">{body_html}</div>'
            )
            if used_chunks:
                pages = set(chunk.get("page_number") for chunk in used_chunks)
                pages_str = ", ".join(sorted(str(p) for p in pages))
                inner += (
                    '<br/><span class="chat-sources">' f"Sources: Pages {pages_str}</span>"
                )
        wrapped = (
            f'<table width="100%" cellpadding="4" cellspacing="0"><tr><td align="left">'
            f'<span style="display:inline-block;background-color:{bubble_bg};color:{bubble_fg};'
            f'border:1px solid {bubble_border};padding:12px 14px;border-radius:18px;max-width:92%;text-align:left;">{inner}</span>'
            f'</td></tr></table>'
        )
        return wrapped

    def _scroll_chat_to_end(self) -> None:
        if self._chat_history_web:
            self.chat_history.page().runJavaScript(
                "window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight));"
            )
        else:
            sb = self.chat_history.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_ask_clicked(self):
        if not self.selected_book_id:
            QMessageBox.information(self, "No book selected", "Please select a book first.")
            return

        question = self.question_input.toPlainText().strip()
        if not question:
            return

        if self.worker_thread and self.worker_thread.isRunning():
            return

        if not self._current_conversation_id:
            try:
                self._current_conversation_id = service.chat_create_conversation(
                    self.selected_book_id, _conversation_title_from_question(question)
                )
            except Exception as exc:
                QMessageBox.warning(self, "Chat", f"Could not start conversation: {exc}")
                return

        try:
            service.chat_add_message(
                self.selected_book_id, self._current_conversation_id, "user", question
            )
            service.chat_update_conversation_title(
                self.selected_book_id,
                self._current_conversation_id,
                _conversation_title_from_question(question),
            )
        except Exception as exc:
            log.warning("persist user message: %s", exc)

        self._refresh_thread_list(select_id=self._current_conversation_id, reload_messages=True)
        self.question_input.clear()
        self.question_input.setEnabled(False)
        self._set_send_enabled(False)
        self.status_label.setText("Calling the model…")

        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.terminate()
            self.worker_thread.wait()

        self.worker_thread = LLMWorker(self.selected_book_id, question)
        self.worker_thread.finished.connect(self._on_llm_finished)
        self.worker_thread.error.connect(self._on_llm_error)
        self.worker_thread.start()

    def _on_llm_finished(self, result: dict):
        QApplication.processEvents()
        status = result.get("status", "ok")
        answer = result.get("answer", "")
        used_chunks = result.get("used_chunks", [])

        if status == "not_supported":
            self._persist_and_show_assistant(
                "Not supported by the source.", None, "not_supported"
            )
        else:
            self._persist_and_show_assistant(answer, used_chunks, "ok")

        self.status_label.setText("")
        self.question_input.setEnabled(True)
        self._set_send_enabled(True)
        self.question_input.setFocus()
        self._refresh_thread_list(select_id=self._current_conversation_id)

    def _persist_and_show_assistant(
        self,
        message: str,
        used_chunks: Optional[List[Dict[str, Any]]],
        status: str,
    ) -> None:
        if self._current_conversation_id and self.selected_book_id is not None:
            try:
                service.chat_add_message(
                    self.selected_book_id,
                    self._current_conversation_id,
                    "assistant",
                    message or "",
                    used_chunks=used_chunks,
                    status=status,
                )
            except Exception as exc:
                log.warning("persist assistant message: %s", exc)
        if self._current_conversation_id:
            self._load_conversation_messages(self._current_conversation_id)

    def _on_llm_error(self, error_msg: str):
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            text = "Request Timeout:\n\nThe request took too long. Try again."
            self._persist_and_show_assistant(text, None, "error")
            self.status_label.setText("Request timed out. Try again.")
        elif "api key" in error_msg.lower() or "OPENAI_API_KEY" in error_msg or "OPENROUTER" in error_msg.upper():
            text = f"API key error:\n\n{error_msg}"
            self._persist_and_show_assistant(text, None, "error")
            self.status_label.setText("Check your API key in Settings or .env")
        elif "rate limit" in error_msg.lower():
            text = f"Rate limit:\n\n{error_msg}"
            self._persist_and_show_assistant(text, None, "error")
            self.status_label.setText("Rate limited. Wait a moment and try again.")
        else:
            self._persist_and_show_assistant(f"Error: {error_msg}", None, "error")
            self.status_label.setText("Failed to get answer.")

        self.question_input.setEnabled(True)
        self._set_send_enabled(True)
        self.question_input.setFocus()
        self._refresh_thread_list(select_id=self._current_conversation_id)

    def _update_process_view(self, used_chunks: list) -> None:
        rules = (
            "<b>Process rules</b><ul>"
            "<li>Only use the provided book excerpts.</li>"
            "<li>If the answer is not supported, respond with: Not supported by the source.</li>"
            "<li>Include page numbers when quoting.</li>"
            "<li>Keep reasoning clear and grounded in the quotes; separate direct quotes from inferences.</li>"
            "</ul>"
        )
        if not used_chunks:
            sources_html = "<b>Sources used</b><br><span style='color:#666;'>No sources yet.</span>"
        else:
            items = []
            for chunk in used_chunks:
                page = chunk.get("page_number")
                chunk_index = chunk.get("chunk_index")
                text = (chunk.get("text") or "").strip()
                preview = html.escape(text[:180] + ("..." if len(text) > 180 else ""))
                items.append(
                    f"<li><b>Page {page}</b> (Chunk {chunk_index})<br><span style='color:#555;'>{preview}</span></li>"
                )
            sources_html = "<b>Sources used</b><ul>" + "".join(items) + "</ul>"
        self.process_view.setHtml(rules + sources_html)
