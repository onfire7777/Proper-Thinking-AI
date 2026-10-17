"""One model factory for OpenRouter or explicitly selected ChatGPT plan usage."""

import os

import requests
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from openai import APIError, OpenAI

from .app_config import OPENROUTER_BASE_URL, get_effective_settings, resolve_model_for_task
from .chatgpt_auth import ChatGPTAuth, ChatGPTError, RESOURCE, USAGE_URL


def _api_error(status: int, code: str = "") -> ChatGPTError:
    if status == 401:
        return ChatGPTError("Your ChatGPT session is no longer valid. Continue with ChatGPT again in Settings.")
    if status == 429 or "limit" in code or "usage" in code or "quota" in code:
        return ChatGPTError("ChatGPT usage limit reached. Manage usage: " + USAGE_URL +
                            " . No paid API fallback was used.")
    if status == 403:
        return ChatGPTError("ChatGPT plan access is unavailable or disabled for this account. "
                            "Check plan permissions and Manage usage: " + USAGE_URL)
    return ChatGPTError(f"ChatGPT request failed (HTTP {status}). Check the account/model in Settings and try again.")


def list_chatgpt_models() -> list[dict]:
    token = ChatGPTAuth().access_token()
    try:
        response = requests.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + token},
                                timeout=(10, 30))
        if not response.ok:
            raise _api_error(response.status_code)
        data = response.json()
    except (requests.RequestException, ValueError):
        raise ChatGPTError("Could not load ChatGPT models. Check your connection and try Refresh models.") from None
    return [{"slug": item["slug"], "display_name": item.get("display_name") or item["slug"]}
            for item in data.get("models", []) if item.get("visibility") == "list" and item.get("slug")]


class ChatGPTModel:
    def invoke(self, messages) -> AIMessage:
        instructions, inputs = [], []
        for message in messages:
            role = {"human": "user", "ai": "assistant", "system": "system"}.get(message.type, message.type)
            if not isinstance(message.content, str):
                raise ChatGPTError("ChatGPT plan integration currently supports text messages only.")
            if role in ("system", "developer"):
                instructions.append(message.content)
            elif role in ("user", "assistant"):
                inputs.append({"role": role, "content": message.content})
            else:
                raise ChatGPTError("Unsupported message type for ChatGPT plan usage.")
        model = get_effective_settings()["chatgpt_model"]
        if not model:
            raise ChatGPTError("Choose an available ChatGPT model in Settings first.")
        token = ChatGPTAuth().access_token()
        client = OpenAI(api_key=token, base_url=RESOURCE, max_retries=0, timeout=300)
        text = []
        completed = False
        try:
            with client.responses.create(model=model, instructions="\n\n".join(instructions),
                                         input=inputs, store=False, stream=True) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        text.append(event.delta)
                    elif event.type == "response.completed":
                        completed = True
                    elif event.type in ("response.failed", "response.incomplete", "error"):
                        error = getattr(getattr(event, "response", None), "error", None)
                        code = str(getattr(error, "code", "") or getattr(event, "code", ""))
                        if "limit" in code or "usage" in code or "quota" in code:
                            raise _api_error(429, code)
                        raise ChatGPTError("ChatGPT did not complete the response. Partial output was discarded. "
                                            "Check Settings or Manage usage: " + USAGE_URL)
        except APIError as error:
            raise _api_error(getattr(error, "status_code", 0) or 0, str(getattr(error, "code", ""))) from None
        finally:
            client.close()
        if not completed:
            raise ChatGPTError("ChatGPT connection ended before completion. Partial output was discarded; please retry.")
        result = "".join(text).strip()
        if not result:
            raise ChatGPTError("ChatGPT completed without a text answer. Try again or choose another model.")
        return AIMessage(content=result, response_metadata={"model_name": model, "provider": "chatgpt"})


def create_chat_model(task_name: str, max_tokens: int):
    if get_effective_settings()["ai_provider"] == "chatgpt":
        return ChatGPTModel()
    # Keep existing OpenRouter routing and token limits unchanged.
    return ChatOpenAI(model=resolve_model_for_task(task_name), max_tokens=max_tokens,
                      openai_api_base=os.getenv("OPENAI_BASE_URL", OPENROUTER_BASE_URL))
