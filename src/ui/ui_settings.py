"""AI provider settings; OAuth credentials are kept out of data/config.json."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QMessageBox,
    QFormLayout,
    QScrollArea,
)
from PyQt6.QtCore import Qt

from ..core.app_config import (
    REASONING_MODEL_CHOICES,
    ROUTING_PRESET_CHOICES,
    DEFAULT_OPENAI_MODEL,
    get_effective_settings,
    preview_bucket_models_for_preset,
    save_settings,
    save_provider_settings,
)
from ..core.llm_client import LLMClient
from .chatgpt_settings import ChatGPTConnectionWidget
from .styles import (
    create_header_widget,
    create_section_card,
    SECTION_CARD_STACK_GAP_PX,
    TAB_MARGINS,
    TAB_SPACING,
    SECTION_LABEL_STYLE,
    COMBO_STYLE,
    INPUT_LINE,
    BTN_PRIMARY,
    BTN_SECONDARY,
    BTN_SECONDARY_SMALL,
    PREVIEW_LABEL_STYLE,
    configure_tab_scroll_area,
    refresh_section_cards,
    wire_scroll_content_margins,
)


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._reload_from_config()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        configure_tab_scroll_area(scroll)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(*TAB_MARGINS)
        content_layout.setSpacing(0)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_layout.addWidget(
            create_header_widget(
                self,
                "Settings",
                "Choose your ChatGPT plan or OpenRouter, then configure the models used across the app.",
            )
        )
        content_layout.addSpacing(TAB_SPACING)

        provider_section, provider_inner = create_section_card(content, "AI provider")
        self._provider_combo = QComboBox()
        self._provider_combo.setStyleSheet(COMBO_STYLE)
        self._provider_combo.addItem("OpenRouter · API key", "openrouter")
        self._provider_combo.addItem("ChatGPT · Sign in with your plan", "chatgpt")
        self._provider_combo.setAccessibleName("AI provider")
        provider_inner.addWidget(self._provider_combo)
        content_layout.addWidget(provider_section)
        content_layout.addSpacing(SECTION_CARD_STACK_GAP_PX)

        self._chatgpt_section, chatgpt_inner = create_section_card(content, "ChatGPT account")
        self._chatgpt = ChatGPTConnectionWidget(self)
        chatgpt_inner.addWidget(self._chatgpt)
        content_layout.addWidget(self._chatgpt_section)
        content_layout.addSpacing(SECTION_CARD_STACK_GAP_PX)

        open_section, open_inner = create_section_card(content, "OpenRouter")
        self._openrouter_section = open_section
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("sk-or-v1-…")
        self._key_edit.setStyleSheet(INPUT_LINE)
        self._key_edit.setMinimumWidth(320)

        self._show_key_btn = QPushButton("Show")
        self._show_key_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self._show_key_btn.setCheckable(True)
        self._show_key_btn.toggled.connect(self._on_toggle_key_visibility)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self._key_edit, 1)
        key_row.addWidget(self._show_key_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._key_label = QLabel("API key:")
        self._key_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._key_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        key_wrap = QWidget()
        key_wrap.setObjectName("sectionCardRow")
        key_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        key_wrap.setStyleSheet("background-color: transparent;")
        key_wrap.setLayout(key_row)
        form.addRow(self._key_label, key_wrap)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(False)
        self._model_combo.setStyleSheet(COMBO_STYLE)
        self._model_combo.setMinimumWidth(400)
        for m in REASONING_MODEL_CHOICES:
            self._model_combo.addItem(m)
        self._model_label = QLabel("Primary model:")
        self._model_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._model_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        form.addRow(self._model_label, self._model_combo)

        self._preset_combo = QComboBox()
        self._preset_combo.setEditable(False)
        self._preset_combo.setStyleSheet(COMBO_STYLE)
        self._preset_combo.setMinimumWidth(260)
        labels = {
            "best_quality": "Best Quality",
            "balanced": "Balanced",
            "low_cost": "Low Cost",
        }
        for p in ROUTING_PRESET_CHOICES:
            self._preset_combo.addItem(labels.get(p, p), p)
        self._preset_label = QLabel("Quality mode:")
        self._preset_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._preset_label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        form.addRow(self._preset_label, self._preset_combo)

        open_inner.addLayout(form)
        content_layout.addWidget(open_section)
        content_layout.addSpacing(SECTION_CARD_STACK_GAP_PX)

        preview_section, preview_inner = create_section_card(content, "Current model usage")
        self._preview_section = preview_section
        self._preview_critical = QLabel("")
        self._preview_structured = QLabel("")
        self._preview_fast = QLabel("")
        for w in (self._preview_critical, self._preview_structured, self._preview_fast):
            w.setStyleSheet(PREVIEW_LABEL_STYLE)
            w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            w.setWordWrap(True)
            preview_inner.addWidget(w)
        content_layout.addWidget(preview_section)

        content_layout.addSpacing(SECTION_CARD_STACK_GAP_PX)
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)
        self._btn_test = QPushButton("Test OpenRouter connection")
        self._btn_test.setStyleSheet(BTN_SECONDARY)
        self._btn_test.clicked.connect(self._on_test)
        self._btn_save = QPushButton("Save")
        self._btn_save.setStyleSheet(BTN_PRIMARY)
        self._btn_save.clicked.connect(self._on_save)
        bottom_bar.addStretch(1)
        bottom_bar.addWidget(self._btn_test)
        bottom_bar.addWidget(self._btn_save)
        content_layout.addLayout(bottom_bar)

        scroll.setWidget(content)
        self._settings_scroll = scroll
        self._settings_content_layout = content_layout
        wire_scroll_content_margins(scroll, content_layout)
        outer.addWidget(scroll, stretch=1)

        self._model_combo.currentIndexChanged.connect(self._refresh_preview)
        self._preset_combo.currentIndexChanged.connect(self._refresh_preview)
        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self._chatgpt.model_changed.connect(self._on_chatgpt_model_changed)

    def apply_theme(self) -> None:
        from .styles import (
            SECTION_LABEL_STYLE,
            INPUT_LINE,
            COMBO_STYLE,
            BTN_PRIMARY,
            BTN_SECONDARY,
            BTN_SECONDARY_SMALL,
            PREVIEW_LABEL_STYLE,
            configure_tab_scroll_area,
            refresh_scroll_content_margins,
        )

        self._key_edit.setStyleSheet(INPUT_LINE)
        self._show_key_btn.setStyleSheet(BTN_SECONDARY_SMALL)
        self._model_combo.setStyleSheet(COMBO_STYLE)
        self._preset_combo.setStyleSheet(COMBO_STYLE)
        self._provider_combo.setStyleSheet(COMBO_STYLE)
        self._chatgpt.apply_theme()
        self._key_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._model_label.setStyleSheet(SECTION_LABEL_STYLE)
        self._preset_label.setStyleSheet(SECTION_LABEL_STYLE)
        for w in (self._preview_critical, self._preview_structured, self._preview_fast):
            w.setStyleSheet(PREVIEW_LABEL_STYLE)
        self._btn_test.setStyleSheet(BTN_SECONDARY)
        self._btn_save.setStyleSheet(BTN_PRIMARY)
        configure_tab_scroll_area(self._settings_scroll)
        refresh_scroll_content_margins(self._settings_scroll, self._settings_content_layout)
        refresh_section_cards(self)

    def _on_toggle_key_visibility(self, show_plain: bool):
        if show_plain:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_key_btn.setText("Hide")
        else:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._show_key_btn.setText("Show")

    def _reload_from_config(self):
        s = get_effective_settings()
        self._provider_combo.blockSignals(True)
        self._provider_combo.setCurrentIndex(self._provider_combo.findData(s.get("ai_provider", "openrouter")))
        self._provider_combo.blockSignals(False)
        self._update_provider_visibility()
        self._key_edit.setText(s.get("openrouter_api_key") or "")
        model = s.get("openrouter_model") or DEFAULT_OPENAI_MODEL
        idx = self._model_combo.findText(model)
        if idx < 0:
            self._model_combo.addItem(model)
            idx = self._model_combo.findText(model)
        self._model_combo.setCurrentIndex(idx)
        preset = (s.get("routing_preset") or "balanced").strip().lower()
        pidx = self._preset_combo.findData(preset)
        if pidx >= 0:
            self._preset_combo.setCurrentIndex(pidx)
        else:
            self._preset_combo.setCurrentIndex(1)  # balanced
        self._refresh_preview()

    def _current_key(self) -> str:
        return self._key_edit.text().strip()

    def _current_model(self) -> str:
        return self._model_combo.currentText().strip() or DEFAULT_OPENAI_MODEL

    def _current_preset(self) -> str:
        return (self._preset_combo.currentData() or "balanced").strip()

    def _refresh_preview(self):
        models = preview_bucket_models_for_preset(
            self._current_preset(),
            primary_model=self._current_model(),
        )
        self._preview_critical.setText(f"Critical reasoning: {models['critical_reasoning']}")
        self._preview_structured.setText(f"Structured JSON / audit: {models['structured_json']}")
        self._preview_fast.setText(f"Fast utility / chat helpers: {models['fast_utility']}")

    def _on_save(self):
        save_settings(self._current_key(), self._current_model(), self._current_preset())
        save_provider_settings(self._provider_combo.currentData(), self._chatgpt.selected_model() or
                               get_effective_settings()["chatgpt_model"])
        QMessageBox.information(
            self,
            "Settings saved",
            "Provider settings were saved and applied. ChatGPT credentials remain in protected local storage.",
        )

    def _on_test(self):
        client = LLMClient(api_key=self._current_key(), model=self._current_model(), provider="openrouter")
        ok, msg = client.test_connection()
        title = "Connection OK" if ok else "Connection failed"
        box = QMessageBox.information if ok else QMessageBox.warning
        box(self, title, msg)

    def _update_provider_visibility(self):
        chatgpt = self._provider_combo.currentData() == "chatgpt"
        self._chatgpt_section.setVisible(chatgpt)
        self._openrouter_section.setVisible(not chatgpt)
        self._preview_section.setVisible(not chatgpt)
        self._btn_test.setVisible(not chatgpt)

    def _on_provider_changed(self):
        self._update_provider_visibility()
        save_provider_settings(self._provider_combo.currentData(), self._chatgpt.selected_model() or
                               get_effective_settings()["chatgpt_model"])
        if self._provider_combo.currentData() == "chatgpt":
            self._chatgpt.refresh()

    def _on_chatgpt_model_changed(self, model):
        save_provider_settings(self._provider_combo.currentData(), model)
