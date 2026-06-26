"""
Frozen-friendly entrypoint for the MCP (stdio) server.

Why this exists:
- Clients won't run `python -m src.api mcp`.
- On Windows, importing `torch` before other native stacks avoids a class of DLL init
  failures; MCP tool calls can still trigger Torch-backed embedding code.

Protocol requirement:
- stdout is reserved for MCP JSON-RPC. Human-readable status must go to stderr only.
"""

from __future__ import annotations

import logging
import os
import sys


def _windows_preimport_torch() -> None:
    if sys.platform != "win32":
        return
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    import torch  # noqa: F401


def _bootstrap_env() -> None:
    from dotenv import load_dotenv

    from src.core.app_config import load_json_into_env

    load_dotenv()
    load_json_into_env()


def _warm_book_manager() -> None:
    # Match FastAPI startup behavior: fail fast if local DB/config can't initialize.
    from src.api import service

    service.get_book_manager()


def main() -> int:
    _windows_preimport_torch()

    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s", stream=sys.stderr)

    _bootstrap_env()
    _warm_book_manager()

    from src.api.mcp_server import run_stdio

    run_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
