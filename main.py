import logging
import sys

# Windows: torch must initialize BEFORE PyQt6 on some systems (your Qt->torch import fails, torch->Qt works).
# This prevents WinError 1114 when generating embeddings inside the GUI process.
if sys.platform == "win32":
    import os

    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    try:
        import torch  # noqa: F401
    except OSError as exc:
        # Some Windows Application Control policies block PyTorch DLLs from local
        # virtual environments. Let the GUI start; embedding operations can
        # report the policy failure when they actually need torch.
        print(f"Warning: PyTorch preload skipped: {exc}", file=sys.stderr)

from dotenv import load_dotenv

load_dotenv()

# After .env: apply data/config.json (single source of truth for OpenRouter key/model in GUI)
from src.core.app_config import load_json_into_env

load_json_into_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
# Avoid noisy per-request INFO lines from HTTP clients (e.g. OpenRouter/httpx).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from src.ui.ui_main import run_gui

if __name__ == "__main__":
    run_gui()
