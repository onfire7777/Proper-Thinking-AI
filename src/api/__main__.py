"""
CLI entrypoint for Phase 1 HTTP API and MCP server.

From the **repository root**::

    python -m src.cli books list
    python -m src.cli frameworks generate 1 --name "My Framework"
    python -m src.api http --host 127.0.0.1 --port 8765
    python -m src.api mcp

Environment (same as desktop app):

- ``load_dotenv()`` + ``data/config.json`` via ``load_json_into_env()`` on first ``BookManager`` use.
- Optional ``PTA_API_KEY``: when set, HTTP routes require header ``X-API-Key: <value>``.
  MCP stdio transport has no HTTP headers; run MCP only in trusted local contexts.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _cmd_http(args: argparse.Namespace) -> None:
    import uvicorn

    from src.api.http_app import create_app

    if not (os.getenv("PTA_API_KEY") or "").strip():
        print(
            "PTA_API_KEY is not set; /v1/* is open to anyone who can reach this bind address.",
            file=sys.stderr,
        )
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
    )


def _cmd_mcp(_: argparse.Namespace) -> None:
    from src.api.mcp_server import run_stdio

    run_stdio()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.api",
        description="Proper Thinking AI - Phase 1 HTTP API and MCP (stdio).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_http = sub.add_parser("http", help="Run FastAPI + uvicorn")
    p_http.add_argument("--host", default="127.0.0.1")
    p_http.add_argument("--port", type=int, default=8765)
    p_http.set_defaults(func=_cmd_http)

    p_mcp = sub.add_parser("mcp", help="Run MCP server (stdio)")
    p_mcp.set_defaults(func=_cmd_mcp)

    ns = parser.parse_args()
    ns.func(ns)


if __name__ == "__main__":
    main()
