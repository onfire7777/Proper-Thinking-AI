import logging
import os
from typing import Optional

from openai import OpenAI
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError
from .app_config import DEFAULT_OPENAI_MODEL, OPENROUTER_BASE_URL, get_effective_settings


# Handles LLM calls using OpenRouter (OpenAI-compatible API)
class LLMClient:

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, provider: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.base_url = os.getenv("OPENAI_BASE_URL", OPENROUTER_BASE_URL)
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if not self.api_key or not self.api_key.strip():
            raise RuntimeError(
                "OpenRouter API key is not set. Add one in Settings or .env:\n"
                "  OPENROUTER_API_KEY=sk-or-v1-..."
            )
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key.strip(), base_url=self.base_url.rstrip("/"))
        return self._client

    def test_connection(self) -> tuple[bool, str]:
        if self._uses_chatgpt():
            try:
                self.generate("", "Reply with the single word OK.")
                return True, "ChatGPT plan connection verified with a completed response."
            except Exception as exc:
                return False, str(exc)
        try:
            client = self._get_client()
            client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Reply with the single word OK."}],
                max_completion_tokens=24,
            )
            return (
                True,
                f"Connection OK. API key is valid and model “{self.model}” accepts chat completions via OpenRouter.",
            )
        except AuthenticationError:
            return False, (
                "Invalid or missing API key. Save a valid key in Settings (data/config.json) "
                "or set OPENROUTER_API_KEY."
            )
        except APIConnectionError as exc:
            return False, f"Cannot reach OpenRouter API. Check your internet connection: {exc}"
        except RateLimitError as exc:
            return False, f"OpenRouter rate limit exceeded: {exc}"
        except APIError as exc:
            err = str(exc).lower()
            if "model" in err or getattr(exc, "status_code", None) in (400, 404):
                return False, (
                    f"Model may be invalid or unavailable for this key/account: {self.model}. "
                    f"Details: {exc}"
                )
            return False, f"OpenRouter API error: {exc}"
        except Exception as exc:
            return False, f"OpenRouter connection test failed: {exc}"

    def prewarm_model(self) -> bool:
        if self._uses_chatgpt():
            # Do not spend plan allowance on background warm-up requests.
            return True
        try:
            client = self._get_client()
            client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=5,
            )
            return True
        except Exception:
            return False

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_completion_tokens: int = 4096,
    ) -> str:
        if self._uses_chatgpt():
            from langchain_core.messages import HumanMessage, SystemMessage
            from .model_client import ChatGPTModel
            return ChatGPTModel().invoke([
                SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)
            ]).content
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=max_completion_tokens,
            )
        except AuthenticationError as exc:
            raise RuntimeError(
                "Invalid or missing OpenRouter API key. Check OPENROUTER_API_KEY in your .env file."
            ) from exc
        except APIConnectionError as exc:
            raise RuntimeError(
                "Cannot reach OpenRouter API. Check your internet connection."
            ) from exc
        except RateLimitError as exc:
            raise RuntimeError(
                "OpenRouter rate limit exceeded. Please wait a moment and try again."
            ) from exc
        except APIError as exc:
            raise RuntimeError(f"OpenRouter API error: {exc}") from exc

        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None
        content = message.content if message else ""
        result = (content or "").strip()

        if not result:
            finish_reason = getattr(choice, "finish_reason", None) if choice else None
            usage = getattr(response, "usage", None)
            usage_info = ""
            if usage:
                usage_info = (
                    f", prompt_tokens={getattr(usage, 'prompt_tokens', '?')}, "
                    f"completion_tokens={getattr(usage, 'completion_tokens', '?')}"
                )
            logging.warning(
                "OpenRouter returned empty content. finish_reason=%r, model=%s%s",
                finish_reason,
                getattr(response, "model", "?"),
                usage_info,
            )

        return result

    def _uses_chatgpt(self) -> bool:
        return (self.provider or get_effective_settings()["ai_provider"]) == "chatgpt"
