import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from src.ui.ui_settings import SettingsTab
from src.ui.chatgpt_settings import ChatGPTConnectionWidget


class ChatGPTSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_chatgpt_provider_hides_router_controls_and_explains_consent(self):
        with patch("src.ui.ui_settings.get_effective_settings", return_value={
            "ai_provider": "chatgpt", "chatgpt_model": "", "routing_preset": "balanced"
        }):
            widget = SettingsTab()
        self.addCleanup(widget.deleteLater)
        self.assertEqual(widget._provider_combo.currentData(), "chatgpt")
        self.assertTrue(widget._openrouter_section.isHidden())
        self.assertFalse(widget._chatgpt_section.isHidden())
        self.assertEqual(widget._chatgpt.connect_button.text(), "Continue with ChatGPT")
        self.assertIn("password", widget._chatgpt.consent_label.text())
        self.assertIn("No automatic", widget._chatgpt.consent_label.text())

    def test_selecting_provider_persists_choice_not_oauth_tokens(self):
        with patch("src.ui.ui_settings.get_effective_settings", return_value={"ai_provider": "openrouter", "chatgpt_model": ""}), patch(
            "src.ui.ui_settings.save_provider_settings"
        ) as save:
            widget = SettingsTab()
            widget._provider_combo.setCurrentIndex(widget._provider_combo.findData("chatgpt"))
        self.addCleanup(widget.deleteLater)
        self.assertEqual(save.call_args.args[0], "chatgpt")
        self.assertEqual(len(save.call_args.args), 2)

    def test_temporary_discovery_error_preserves_same_account_model(self):
        widget = ChatGPTConnectionWidget()
        self.addCleanup(widget.deleteLater)
        status = {"active_profile_id": "one", "connected": True, "sharing": True,
                  "profiles": [{"id": "one", "label": "Account one"}]}
        widget._render({"status": status, "models": [{"slug": "eligible", "display_name": "Eligible"}]})
        widget._render({"status": status, "models": None, "notice": "Network unavailable"})
        self.assertEqual(widget.selected_model(), "eligible")
        self.assertIn("Network unavailable", widget.status_label.text())

    def test_switching_accounts_does_not_reuse_old_model_list_when_discovery_fails(self):
        widget = ChatGPTConnectionWidget()
        self.addCleanup(widget.deleteLater)
        status = {"active_profile_id": "one", "connected": True, "sharing": True,
                  "profiles": [{"id": "one", "label": "Account one"}]}
        widget._render({"status": status, "models": [{"slug": "eligible", "display_name": "Eligible"}]})
        widget._render({"status": {**status, "active_profile_id": "two",
                                   "profiles": [{"id": "two", "label": "Account two"}]},
                        "models": None, "notice": "Network unavailable"})
        self.assertEqual(widget.selected_model(), "")

    def test_constructing_settings_does_not_wait_for_credential_lock(self):
        with patch("src.ui.chatgpt_settings.ChatGPTAuth") as auth:
            auth.return_value.status.side_effect = AssertionError("UI must not acquire credential lock")
            widget = ChatGPTConnectionWidget()
            self.addCleanup(widget.deleteLater)

    def test_initial_offline_discovery_does_not_clear_saved_model(self):
        settings = {"ai_provider": "openrouter", "chatgpt_model": "saved-model"}
        with patch("src.ui.ui_settings.get_effective_settings", return_value=settings), patch(
            "src.ui.ui_settings.save_provider_settings"
        ) as save:
            widget = SettingsTab()
            self.addCleanup(widget.deleteLater)
            widget._chatgpt._render({"status": {
                "active_profile_id": "one", "connected": True, "sharing": True,
                "profiles": [{"id": "one", "label": "Account one"}]},
                "models": None, "notice": "Network unavailable"})
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
