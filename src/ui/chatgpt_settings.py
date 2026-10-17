"""Native connection card. Credentials never enter UI fields or worker signals."""

import threading
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QThread, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox, QPushButton, QMessageBox

from ..core.app_config import get_effective_settings, acknowledge_chatgpt_plan
from ..core.chatgpt_auth import ChatGPTAuth, ChatGPTError, USAGE_URL
from ..core.model_client import list_chatgpt_models
from ..core.llm_client import LLMClient
from . import styles


class _ConnectionJob(QThread):
    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.result.emit(self.operation())
        except ChatGPTError as error:
            self.error.emit(str(error))
        except Exception:
            self.error.emit("Could not update the ChatGPT connection. Please try again.")


class ChatGPTConnectionWidget(QWidget):
    model_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job = None
        self._cancel = threading.Event()
        self._models = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.consent_label = QLabel(
            "Sign in in your browser to let Proper Thinking AI use your eligible ChatGPT Plus or Pro plan. "
            "OpenAI asks permission to identify your account, use your plan, and keep you signed in. "
            "Your password stays with OpenAI; this does not access your ChatGPT conversations. "
            "No automatic fallback to paid OpenRouter/API calls."
        )
        self.consent_label.setWordWrap(True)
        layout.addWidget(self.consent_label)
        self.status_label = QLabel("Not connected")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.account_combo = QComboBox()
        self.account_combo.setAccessibleName("ChatGPT account")
        self.account_combo.setPlaceholderText("No account connected")
        self.account_combo.currentIndexChanged.connect(self._select_account)
        self.model_combo = QComboBox()
        self.model_combo.setAccessibleName("ChatGPT model available to this account")
        self.model_combo.setPlaceholderText("Sign in to load available models")
        self.model_combo.currentIndexChanged.connect(lambda: self.model_changed.emit(self.selected_model()))
        form = QFormLayout()
        form.addRow("Account:", self.account_combo)
        form.addRow("Model:", self.model_combo)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.connect_button = QPushButton("Continue with ChatGPT")
        self.connect_button.setIcon(QIcon(str(Path(__file__).parent / "resources" / "chatgpt-button-white-21.svg")))
        self.connect_button.setIconSize(QSize(21, 21))
        self.connect_button.clicked.connect(self._sign_in)
        self.add_button = QPushButton("Add account")
        self.add_button.clicked.connect(lambda: self._sign_in(new_profile=True))
        self.disconnect_button = QPushButton("Sign out")
        self.disconnect_button.clicked.connect(self._sign_out)
        self.cancel_button = QPushButton("Cancel sign-in")
        self.cancel_button.clicked.connect(self._cancel.set)
        self.cancel_button.hide()
        for button in (self.connect_button, self.add_button, self.disconnect_button, self.cancel_button):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        tools = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh models")
        self.refresh_button.clicked.connect(self.refresh)
        self.test_button = QPushButton("Test ChatGPT connection")
        self.test_button.clicked.connect(self._test)
        usage = QPushButton("Manage usage")
        usage.clicked.connect(lambda: webbrowser.open(USAGE_URL))
        for button in (self.refresh_button, self.test_button, usage):
            tools.addWidget(button)
        tools.addStretch(1)
        layout.addLayout(tools)
        self._buttons = (self.connect_button, self.add_button, self.disconnect_button,
                         self.refresh_button, self.test_button, usage, self.cancel_button)
        self.apply_theme()
        # Credential locks may be held by another process doing a network refresh.
        # Never acquire one on the GUI thread, including at startup.
        if get_effective_settings()["ai_provider"] == "chatgpt":
            QTimer.singleShot(0, self.refresh)

    def apply_theme(self):
        for label in (self.consent_label, self.status_label):
            label.setStyleSheet(styles.PREVIEW_LABEL_STYLE)
        for combo in (self.account_combo, self.model_combo):
            combo.setStyleSheet(styles.COMBO_STYLE)
        for button in self._buttons:
            button.setStyleSheet(styles.BTN_SECONDARY)
        self.connect_button.setStyleSheet(
            "QPushButton { background: #000; color: #fff; border: 1px solid #666; "
            "border-radius: 6px; padding: 7px 12px; } "
            "QPushButton:hover { background: #242424; } "
            "QPushButton:disabled { background: #333; color: #aaa; } "
            "QPushButton:focus { border: 2px solid #fff; }"
        )

    def selected_model(self) -> str:
        return self.model_combo.currentData() or ""

    def _snapshot(self) -> dict:
        status = ChatGPTAuth().status()
        payload = {"status": status, "models": []}
        if status["sharing"]:
            try:
                payload["models"] = list_chatgpt_models()
            except ChatGPTError as error:
                payload["notice"] = str(error)
                payload["models"] = None
                payload["status"] = ChatGPTAuth().status()
        return payload

    def _render(self, payload):
        status = payload["status"]
        # First hydration is not an account switch: an offline startup must not
        # erase the model already saved for that account.
        same_account = not hasattr(self, "_active_profile_id") or self._active_profile_id == status["active_profile_id"]
        self._active_profile_id = status["active_profile_id"]
        previous = self.selected_model() or get_effective_settings()["chatgpt_model"]
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        for profile in status["profiles"]:
            self.account_combo.addItem(profile["label"], profile["id"])
        self.account_combo.setCurrentIndex(self.account_combo.findData(status["active_profile_id"]))
        self.account_combo.blockSignals(False)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if payload["models"] is not None:
            self._models = payload["models"]
        elif not same_account or not status["sharing"]:
            self._models = []
        for model in self._models:
            self.model_combo.addItem(model["display_name"], model["slug"])
        index = self.model_combo.findData(previous)
        self.model_combo.setCurrentIndex(index if index >= 0 else (0 if self._models else -1))
        self.model_combo.blockSignals(False)
        if payload["models"] is not None or not same_account or not status["sharing"]:
            self.model_changed.emit(self.selected_model())
        if status["sharing"]:
            text = "Connected · Using ChatGPT plan. Model availability and limits come from your account."
        elif status["connected"]:
            text = "Signed in · ChatGPT plan permission was not granted. Continue with ChatGPT to enable it."
        else:
            text = "Not connected · Continue with ChatGPT to sign in."
        self.status_label.setText(payload.get("notice") or text)
        if payload.get("welcome") and status["sharing"] and acknowledge_chatgpt_plan():
            welcome = QMessageBox(self)
            welcome.setWindowTitle("You’re using your ChatGPT plan")
            welcome.setText("Proper Thinking AI can now use the plan you authorized. "
                            "Review limits and disconnect access with Manage usage.")
            welcome.addButton("Got it", QMessageBox.ButtonRole.AcceptRole)
            welcome.exec()
        if payload.get("test_message"):
            QMessageBox.information(self, "ChatGPT connection", payload["test_message"])

    def _busy(self, busy):
        for button in (self.connect_button, self.add_button, self.disconnect_button,
                       self.refresh_button, self.test_button):
            button.setEnabled(not busy)
        self.account_combo.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.cancel_button.setVisible(busy and self._signing_in)

    def _run(self, operation, signing_in=False):
        if self._job is not None:
            return
        self._signing_in = signing_in
        self._cancel.clear()
        self._busy(True)
        self.status_label.setText("Finish sign-in in your browser. You can cancel here." if signing_in else "Updating ChatGPT connection…")
        self._job = _ConnectionJob(operation, self)
        self._job.result.connect(self._render)
        self._job.error.connect(self._error)
        self._job.finished.connect(self._finished)
        self._job.start()

    def _finished(self):
        job, self._job = self._job, None
        self._busy(False)
        job.deleteLater()

    def _error(self, message):
        self.status_label.setText(message)
        if not self._cancel.is_set():
            QMessageBox.warning(self, "ChatGPT connection", message)

    def _sign_in(self, _checked=False, new_profile=False):
        profile_id = self.account_combo.currentData()
        def operation():
            ChatGPTAuth().sign_in(profile_id, new_profile, self._cancel)
            return {**self._snapshot(), "welcome": True}
        self._run(operation, signing_in=True)

    def _select_account(self):
        profile_id = self.account_combo.currentData()
        if not profile_id:
            return
        # Clear the old account's selection before its replacement is discovered.
        self.model_combo.clear()
        self.model_changed.emit("")
        def operation():
            ChatGPTAuth().select_profile(profile_id)
            return self._snapshot()
        self._run(operation)

    def _sign_out(self):
        profile_id = self.account_combo.currentData()
        if not profile_id:
            return
        def operation():
            confirmed = ChatGPTAuth().sign_out(profile_id)
            payload = self._snapshot()
            if not confirmed:
                payload["notice"] = "Signed out locally. Remote revocation was not confirmed; disconnect the app in ChatGPT Settings → Usage."
            return payload
        self._run(operation)

    def refresh(self):
        self._run(self._snapshot)

    def _test(self):
        def operation():
            ok, message = LLMClient(provider="chatgpt").test_connection()
            if not ok:
                raise ChatGPTError(message)
            return {**self._snapshot(), "test_message": message}
        self._run(operation)

    def can_close(self) -> bool:
        if self._job is not None:
            self._cancel.set()
            self.status_label.setText("Cancelling… Please wait for the connection operation to finish before closing.")
            return False
        return True
