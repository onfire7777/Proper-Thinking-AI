import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import HumanMessage, SystemMessage

from src.core import app_config, model_client
from src.core.chatgpt_auth import ChatGPTError
from src.core.llm_client import LLMClient


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, *_args):
        pass


class ChatGPTModelTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"AI_PROVIDER": "chatgpt", "CHATGPT_MODEL": "eligible-model"}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_provider_persists_without_overwriting_openrouter_settings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app_config, "data_dir", return_value=Path(directory)):
            app_config.save_settings("existing-key", "custom/router-model", "low_cost")
            app_config.save_provider_settings("chatgpt", "eligible-model")
            settings = app_config.load_json_into_env()
            self.assertEqual(settings["ai_provider"], "chatgpt")
            self.assertEqual(settings["chatgpt_model"], "eligible-model")
            self.assertEqual(settings["openrouter_api_key"], "existing-key")
            self.assertEqual(settings["openrouter_model"], "custom/router-model")
            for task in ("default", "framework_extraction", "meta_pass", "definitive_fields"):
                self.assertEqual(app_config.resolve_model_for_task(task), "eligible-model")

    def test_responses_uses_plan_token_and_no_unsupported_parameters(self):
        events = [SimpleNamespace(type="response.output_text.delta", delta="Grounded answer."),
                  SimpleNamespace(type="response.completed")]
        with patch.object(model_client, "ChatGPTAuth") as auth, patch.object(model_client, "OpenAI") as sdk:
            auth.return_value.access_token.return_value = "test-oauth-access"
            sdk.return_value.responses.create.return_value = FakeStream(events)
            result = model_client.create_chat_model("meta_pass", 8192).invoke([
                SystemMessage(content="Use the source only."), HumanMessage(content="Book excerpt.")])
        self.assertEqual(result.content, "Grounded answer.")
        self.assertEqual(sdk.call_args.kwargs["base_url"], "https://api.openai.com/v1")
        payload = sdk.return_value.responses.create.call_args.kwargs
        self.assertEqual(payload, {"model": "eligible-model", "instructions": "Use the source only.",
                                  "input": [{"role": "user", "content": "Book excerpt."}],
                                  "store": False, "stream": True})

    def test_incomplete_or_failed_stream_never_returns_partial_output(self):
        for terminal in (None, "response.failed", "response.incomplete", "error"):
            events = [SimpleNamespace(type="response.output_text.delta", delta="Partial answer")]
            if terminal:
                events.append(SimpleNamespace(type=terminal))
            with self.subTest(terminal=terminal), patch.object(model_client, "ChatGPTAuth"), patch.object(model_client, "OpenAI") as sdk:
                sdk.return_value.responses.create.return_value = FakeStream(events)
                with self.assertRaises(ChatGPTError):
                    model_client.ChatGPTModel().invoke([HumanMessage(content="Question?")])

    def test_models_preserve_account_order_and_exclude_hidden_entries(self):
        class Response:
            status_code = 200
            ok = True

            def json(self):
                return {"models": [
                    {"slug": "second", "display_name": "Second", "visibility": "list"},
                    {"slug": "hidden", "display_name": "Hidden", "visibility": "hide"},
                    {"slug": "first", "display_name": "First", "visibility": "list"}]}

        with patch.object(model_client, "ChatGPTAuth"), patch.object(model_client.requests, "get", return_value=Response()):
            models = model_client.list_chatgpt_models()
        self.assertEqual([model["slug"] for model in models], ["second", "first"])

    def test_legacy_client_routes_to_chatgpt_without_openrouter_key(self):
        events = [SimpleNamespace(type="response.output_text.delta", delta="OK"),
                  SimpleNamespace(type="response.completed")]
        with patch.object(model_client, "ChatGPTAuth"), patch.object(model_client, "OpenAI") as sdk:
            sdk.return_value.responses.create.return_value = FakeStream(events)
            self.assertEqual(LLMClient().generate("System instruction", "Question"), "OK")

    def test_failed_chatgpt_request_never_falls_back_to_openrouter(self):
        with patch.object(model_client, "ChatGPTAuth") as auth, patch.object(model_client, "ChatOpenAI") as router:
            auth.return_value.access_token.side_effect = ChatGPTError("Plan usage limit reached")
            with self.assertRaisesRegex(ChatGPTError, "usage limit"):
                model_client.create_chat_model("default", 200).invoke([HumanMessage(content="Question?")])
        router.assert_not_called()

    def test_openrouter_connection_test_does_not_spend_chatgpt_allowance(self):
        from src.api import service
        with patch("src.core.llm_client.OpenAI") as router, patch.object(model_client, "ChatGPTAuth") as auth:
            self.assertTrue(service.settings_test_connection("router-test-key", "router-model")["ok"])
        auth.assert_not_called()
        self.assertEqual(router.return_value.chat.completions.create.call_args.kwargs["model"], "router-model")


if __name__ == "__main__":
    unittest.main()
