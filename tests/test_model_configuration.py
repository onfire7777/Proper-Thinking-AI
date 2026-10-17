import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from src.core import app_config, langchain_framework, langchain_framework_qa, langchain_rag, model_client


class ModelConfigurationTests(unittest.TestCase):
    def setUp(self):
        system_environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("OPENAI_", "OPENROUTER_"))
        }
        self.environment = patch.dict(os.environ, system_environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_dir = Path(self.directory.name)
        self.data_path = patch.object(app_config, "data_dir", return_value=self.config_dir)
        self.data_path.start()
        self.addCleanup(self.data_path.stop)

    def test_default_and_dropdown_use_current_models(self):
        self.assertEqual(app_config.DEFAULT_OPENAI_MODEL, "openai/gpt-6.1-sol")
        self.assertEqual(
            set(app_config.REASONING_MODEL_CHOICES),
            {
                "openai/gpt-6.1-sol",
                "openai/gpt-6-astra",
                "openai/gpt-6-luna",
                "anthropic/claude-opus-5",
                "anthropic/claude-sonnet-5.5",
                "anthropic/claude-haiku-5.5",
                "google/gemini-3.8-flash",
            },
        )

    def test_preset_previews_use_current_models(self):
        expected = {
            "best_quality": ("openai/gpt-6-astra", "openai/gpt-6.1-sol", "anthropic/claude-sonnet-5.5"),
            "balanced": ("openai/gpt-6.1-sol", "anthropic/claude-sonnet-5.5", "anthropic/claude-haiku-5.5"),
            "low_cost": ("openai/gpt-6-luna", "openai/gpt-6-luna", "anthropic/claude-haiku-5.5"),
        }
        for preset, models in expected.items():
            with self.subTest(preset=preset):
                preview = app_config.preview_bucket_models_for_preset(preset)
                self.assertEqual(
                    preview,
                    dict(zip(("critical_reasoning", "structured_json", "fast_utility"), models)),
                )

    def test_fresh_install_loads_new_default(self):
        settings = app_config.load_json_into_env()
        self.assertEqual(settings["openrouter_model"], "openai/gpt-6.1-sol")
        self.assertEqual(app_config.resolve_model_for_task("default"), "openai/gpt-6.1-sol")
        self.assertEqual(app_config.resolve_model_for_task("meta_pass"), "anthropic/claude-haiku-5.5")

    def test_selected_primary_overrides_only_critical_tasks(self):
        app_config.apply_to_process_env("test-key", "google/gemini-3.8-flash", "low_cost")
        self.assertEqual(app_config.resolve_model_for_task("framework_extraction"), "google/gemini-3.8-flash")
        self.assertEqual(app_config.resolve_model_for_task("definitive_fields"), "openai/gpt-6-luna")
        self.assertEqual(app_config.resolve_model_for_task("target_audience"), "anthropic/claude-haiku-5.5")

    def test_saved_custom_model_key_and_theme_are_preserved(self):
        path = self.config_dir / "config.json"
        path.write_text(json.dumps({"ui_theme": "dark"}), encoding="utf-8")
        app_config.save_settings("test-key", "custom/provider-model", "best_quality")
        settings = app_config.load_json_into_env()
        self.assertEqual(settings["openrouter_model"], "custom/provider-model")
        self.assertEqual(settings["openrouter_api_key"], "test-key")
        self.assertEqual(app_config.get_ui_theme(), "dark")

    def test_saved_empty_key_does_not_fall_back_to_environment(self):
        app_config.save_settings("", "openai/gpt-6.1-sol", "balanced")
        os.environ["OPENROUTER_API_KEY"] = "environment-test-key"
        self.assertEqual(app_config.load_json_into_env()["openrouter_api_key"], "")

    def test_settings_displays_saved_model_even_outside_current_choices(self):
        from PyQt6.QtWidgets import QApplication

        from src.ui.ui_settings import SettingsTab

        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication.instance() or QApplication([])
        for model in (app_config.DEFAULT_OPENAI_MODEL, "openai/gpt-5.2", "custom/provider-model"):
            with self.subTest(model=model), patch(
                "src.ui.ui_settings.get_effective_settings",
                return_value={"openrouter_model": model, "routing_preset": "balanced"},
            ):
                widget = SettingsTab()
                self.assertEqual(widget._current_model(), model)
                self.assertIn(model, widget._preview_critical.text())
                widget.close()
                widget.deleteLater()
                app.processEvents()


class ModelRequestTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"OPENROUTER_MODEL": "openai/gpt-6.1-sol"}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_framework_client_omits_unsupported_temperature(self):
        with patch.object(model_client, "ChatOpenAI") as factory:
            langchain_framework._chat_llm_for_task("framework_extraction", 8192)
        self.assertEqual(factory.call_args.kwargs["model"], "openai/gpt-6.1-sol")
        self.assertNotIn("temperature", factory.call_args.kwargs)

    def test_serialized_requests_omit_temperature_for_current_models(self):
        for model in app_config.REASONING_MODEL_CHOICES:
            with self.subTest(model=model), patch.dict(
                os.environ, {"OPENROUTER_MODEL": model, "OPENAI_API_KEY": "test-key"}
            ):
                client = langchain_framework._chat_llm_for_task("framework_extraction", 8192)
                payload = client._get_request_payload([HumanMessage(content="Test input.")])
                self.assertEqual(payload["model"], model)
                self.assertNotIn("temperature", payload)

    def test_book_and_framework_qa_omit_unsupported_temperature(self):
        document = Document(page_content="Example source text.", metadata={"page_number": 7, "chunk_index": 0})
        for module in (langchain_rag, langchain_framework_qa):
            with self.subTest(module=module.__name__):
                with patch.object(module, "BookRetriever") as retriever, patch.object(model_client, "ChatOpenAI") as factory:
                    retriever.return_value.invoke.return_value = [document]
                    factory.return_value.invoke.return_value = SimpleNamespace(content="A grounded answer.")
                    if module is langchain_rag:
                        result = module.run_qa(None, 1, "Question?")
                    else:
                        result = module.run_framework_qa(None, 1, "Framework text.", "Example", "Question?")
                self.assertEqual(factory.call_args.kwargs["model"], "openai/gpt-6.1-sol")
                self.assertNotIn("temperature", factory.call_args.kwargs)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["used_chunks"][0]["page_number"], 7)


if __name__ == "__main__":
    unittest.main()
