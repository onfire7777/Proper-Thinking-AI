"""CLI stdout/stderr helpers."""

from __future__ import annotations

import json
import sys
from typing import Any, Optional


def print_json(data: Any, *, compact: bool = False) -> None:
    indent = None if compact else 2
    print(json.dumps(data, ensure_ascii=False, indent=indent, default=str))


def print_markdown_document(data: dict, *, field: str = "definitive_document") -> None:
    doc = (data.get(field) or "").strip()
    if not doc:
        print_json({"error": f"No {field} in response (generation may still be running)."})
        sys.exit(1)
    sys.stdout.write(doc)
    if not doc.endswith("\n"):
        sys.stdout.write("\n")


def print_error(message: str) -> None:
    print(message, file=sys.stderr)


def progress_line(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
