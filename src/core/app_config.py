"""Provider settings and task routing; OAuth credentials live separately."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# OpenRouter defaults
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_MODEL = "openai/gpt-6.1-sol"
DEFAULT_ROUTING_PRESET = "balanced"

ROUTING_PRESET_CHOICES: tuple[str, ...] = ("best_quality", "balanced", "low_cost")

# OpenRouter model IDs verified against the public catalog on 2026-10-17.
REASONING_MODEL_CHOICES: tuple[str, ...] = (
    "openai/gpt-6.1-sol",
    "openai/gpt-6-astra",
    "openai/gpt-6-luna",
    "anthropic/claude-opus-5",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-5.5",
    "google/gemini-3.8-flash",
)

_TASK_TO_BUCKET: Dict[str, str] = {
    "framework_extraction": "critical_reasoning",
    "judgment_audit": "critical_reasoning",
    "logic_audit": "critical_reasoning",
    "definitive_fields": "structured_json",
    "scope_pass": "structured_json",
    "overview_prose": "structured_json",
    "epistemic_pass": "structured_json",
    "mindmap_edges": "structured_json",
    "graph_edge_repair": "structured_json",
    "meta_pass": "fast_utility",
    "target_audience": "fast_utility",
    "default": "critical_reasoning",
}

_PRESET_BUCKET_MODELS: Dict[str, Dict[str, str]] = {
    "best_quality": {
        "critical_reasoning": "openai/gpt-6-astra",
        "structured_json": "openai/gpt-6.1-sol",
        "fast_utility": "anthropic/claude-sonnet-5.5",
    },
    "balanced": {
        "critical_reasoning": "openai/gpt-6.1-sol",
        "structured_json": "anthropic/claude-sonnet-5.5",
        "fast_utility": "anthropic/claude-haiku-5.5",
    },
    "low_cost": {
        "critical_reasoning": "openai/gpt-6-luna",
        "structured_json": "openai/gpt-6-luna",
        "fast_utility": "anthropic/claude-haiku-5.5",
    },
}

_CONFIG_NAME = "config.json"


def project_root() -> Path:
    """
    Directory that should hold `data/`, `books/`, etc.

    - From source: repo root (parent of `src/`).
    - Frozen (PyInstaller, etc.):
      - Default: folder containing the executable.
      - If that folder has no existing data markers, but a parent folder does
        (e.g. MCP executable placed in a child subfolder of the desktop app),
        use the nearest parent that already has data markers.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent

        def _has_data_markers(p: Path) -> bool:
            return (
                (p / "data" / _CONFIG_NAME).is_file()
                or (p / "data").is_dir()
                or (p / "books").is_dir()
            )

        if _has_data_markers(exe_dir):
            return exe_dir

        # Walk upward to find the nearest existing app data root.
        for parent in exe_dir.parents:
            if _has_data_markers(parent):
                return parent

        return exe_dir
    return Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    d = project_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_json_path() -> Path:
    return data_dir() / _CONFIG_NAME


def _normalize_preset(v: Optional[str]) -> str:
    s = (v or "").strip().lower()
    return s if s in ROUTING_PRESET_CHOICES else DEFAULT_ROUTING_PRESET


def _read_file() -> Dict[str, Any]:
    path = config_json_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_file(data: Dict[str, Any]) -> None:
    data_dir()
    path = config_json_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def apply_to_process_env(api_key: Optional[str], model: Optional[str], preset: Optional[str] = None) -> None:
    """Update process env for OpenRouter via OpenAI-compatible clients."""
    key = (api_key or "").strip()
    mod = (model or "").strip() or DEFAULT_OPENAI_MODEL
    rp = _normalize_preset(preset)
    if key:
        os.environ["OPENAI_API_KEY"] = key
        os.environ["OPENROUTER_API_KEY"] = key
    else:
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["OPENAI_BASE_URL"] = OPENROUTER_BASE_URL
    os.environ["OPENAI_MODEL"] = mod
    os.environ["OPENROUTER_MODEL"] = mod
    os.environ["OPENROUTER_ROUTING_PRESET"] = rp


def load_json_into_env() -> Dict[str, str]:
    """
    On startup: if data/config.json exists, it is the source of truth for key/model
    (empty saved key means no key — does not fall back to .env). If the file is absent,
    use .env / environment only.
    """
    path = config_json_path()
    if path.is_file():
        data = _read_file()
        file_key = (data.get("openrouter_api_key") or data.get("openai_api_key") or "").strip()
        file_model = (data.get("openrouter_model") or data.get("openai_model") or "").strip() or DEFAULT_OPENAI_MODEL
        file_preset = _normalize_preset(data.get("routing_preset"))
        apply_to_process_env(file_key, file_model, file_preset)
        os.environ["AI_PROVIDER"] = "chatgpt" if data.get("ai_provider") == "chatgpt" else "openrouter"
        os.environ["CHATGPT_MODEL"] = str(data.get("chatgpt_model") or "")
        return get_effective_settings()

    env_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    env_model = (os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "").strip() or DEFAULT_OPENAI_MODEL
    env_preset = _normalize_preset(os.getenv("OPENROUTER_ROUTING_PRESET"))
    apply_to_process_env(env_key, env_model, env_preset)
    return get_effective_settings()


def get_effective_settings() -> Dict[str, str]:
    """Current process env after load (no file read)."""
    return {
        "ai_provider": "chatgpt" if os.getenv("AI_PROVIDER") == "chatgpt" else "openrouter",
        "chatgpt_model": os.getenv("CHATGPT_MODEL", "").strip(),
        "openrouter_api_key": (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip(),
        "openrouter_model": (os.getenv("OPENROUTER_MODEL") or os.getenv("OPENAI_MODEL") or "").strip()
        or DEFAULT_OPENAI_MODEL,
        "routing_preset": _normalize_preset(os.getenv("OPENROUTER_ROUTING_PRESET")),
    }


def save_settings(api_key: str, model: str, routing_preset: Optional[str] = None) -> None:
    """Persist OpenRouter key/model/preset to data/config.json and sync env."""
    mod = (model or "").strip() or DEFAULT_OPENAI_MODEL
    rp = _normalize_preset(routing_preset)
    data = _read_file()
    data.update(
        {
            "openrouter_api_key": (api_key or "").strip(),
            "openrouter_model": mod,
            "routing_preset": rp,
        }
    )
    _write_file(data)
    apply_to_process_env(data["openrouter_api_key"], data["openrouter_model"], data["routing_preset"])


def save_provider_settings(provider: str, chatgpt_model: str = "") -> None:
    if provider not in ("openrouter", "chatgpt"):
        raise ValueError("Unknown AI provider")
    data = _read_file()
    data.update(ai_provider=provider, chatgpt_model=chatgpt_model.strip())
    _write_file(data)
    os.environ["AI_PROVIDER"] = provider
    os.environ["CHATGPT_MODEL"] = chatgpt_model.strip()


def acknowledge_chatgpt_plan() -> bool:
    """Return true once so the UI can show the required first-connection welcome."""
    data = _read_file()
    if data.get("chatgpt_welcome_shown"):
        return False
    data["chatgpt_welcome_shown"] = True
    _write_file(data)
    return True


def get_ui_theme() -> str:
    """Persisted UI theme: light | dark (default light)."""
    t = (str(_read_file().get("ui_theme") or "light")).strip().lower()
    return t if t in ("light", "dark") else "light"


def save_ui_theme(theme: str) -> None:
    """Merge ui_theme into data/config.json (preserves OpenRouter keys)."""
    t = (theme or "light").strip().lower()
    t = t if t in ("light", "dark") else "light"
    data = _read_file()
    data["ui_theme"] = t
    _write_file(data)


def resolve_model_for_task(task_name: str) -> str:
    """Return routed model for a given logical task using current preset + env overrides."""
    settings = get_effective_settings()
    if settings["ai_provider"] == "chatgpt":
        return settings["chatgpt_model"]
    preset = _normalize_preset(settings.get("routing_preset"))
    bucket = _TASK_TO_BUCKET.get((task_name or "").strip().lower(), _TASK_TO_BUCKET["default"])
    model = _PRESET_BUCKET_MODELS.get(preset, _PRESET_BUCKET_MODELS[DEFAULT_ROUTING_PRESET]).get(
        bucket, DEFAULT_OPENAI_MODEL
    )
    if bucket == "critical_reasoning":
        # UI primary model always drives critical tasks.
        primary = (settings.get("openrouter_model") or "").strip()
        if primary:
            model = primary
    return model


def preview_bucket_models_for_preset(
    preset: Optional[str],
    primary_model: Optional[str] = None,
) -> Dict[str, str]:
    """Preview model assignment by bucket for UI (without saving)."""
    rp = _normalize_preset(preset)
    base = dict(_PRESET_BUCKET_MODELS.get(rp, _PRESET_BUCKET_MODELS[DEFAULT_ROUTING_PRESET]))
    primary = (primary_model or "").strip()
    if primary:
        base["critical_reasoning"] = primary
    return {
        "critical_reasoning": base.get("critical_reasoning", DEFAULT_OPENAI_MODEL),
        "structured_json": base.get("structured_json", DEFAULT_OPENAI_MODEL),
        "fast_utility": base.get("fast_utility", DEFAULT_OPENAI_MODEL),
    }
