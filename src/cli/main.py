"""
Proper Thinking AI terminal CLI.

Run from repository root::

    python -m src.cli books list
    python -m src.cli frameworks generate 1 --name "My Framework"
    python -m src.cli frameworks wait 1 3
    python -m src.cli frameworks get 1 3 --markdown

Uses the same ``service`` layer as HTTP/MCP/GUI. Framework generation defaults to
async start (``--wait`` blocks until complete). Retrieval defaults to
``view=definitive`` (nine-section markdown only).
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Callable, List, Optional

from src.api import service
from src.cli import output


def _progress_cb(msg: str) -> None:
    output.progress_line(msg)


def _handle(fn: Callable[[], Any], *, as_json: bool = True) -> int:
    try:
        result = fn()
        if result is None:
            print_json({"status": "ok"})
        elif as_json:
            print_json(result)
        return 0
    except ValueError as exc:
        output.print_error(f"error: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        output.print_error(f"error: {exc}")
        return 1


def print_json(data: Any, *, compact: bool = False) -> None:
    output.print_json(data, compact=compact)


def _add_json_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--compact",
        action="store_true",
        help="Single-line JSON output",
    )


def _cmd_books_list(_: argparse.Namespace) -> int:
    def _run() -> List[dict]:
        rows = service.list_books()
        return [
            {
                "id": b.get("id"),
                "title": b.get("title"),
                "filename": b.get("filename"),
                "pages": b.get("pages"),
                "chunk_count": b.get("chunk_count"),
                "embeddings_generated": b.get("embeddings_generated"),
            }
            for b in rows
        ]

    return _handle(_run)


def _cmd_books_show(args: argparse.Namespace) -> int:
    return _handle(lambda: service.get_book_info(args.book_id))


def _cmd_books_upload(args: argparse.Namespace) -> int:
    return _handle(lambda: service.upload_book(args.path))


def _cmd_books_delete(args: argparse.Namespace) -> int:
    def _run() -> dict:
        service.delete_book(args.book_id)
        return {"status": "ok", "book_id": args.book_id}

    return _handle(_run)


def _cmd_books_search(args: argparse.Namespace) -> int:
    return _handle(lambda: service.search_book(args.book_id, args.query, top_k=args.top_k))


def _cmd_books_ask(args: argparse.Namespace) -> int:
    return _handle(lambda: service.answer_question(args.book_id, args.question, top_k=args.top_k))


def _cmd_books_embeddings_status(args: argparse.Namespace) -> int:
    return _handle(lambda: service.embeddings_status(args.book_id))


def _cmd_books_embeddings_generate(args: argparse.Namespace) -> int:
    return _handle(lambda: service.generate_embeddings(args.book_id))


def _cmd_frameworks_list(args: argparse.Namespace) -> int:
    def _run() -> List[dict]:
        rows = service.framework_list(args.book_id)
        return [
            {
                "id": f.get("id"),
                "book_id": f.get("book_id"),
                "name": f.get("name"),
                "generation_status": f.get("generation_status"),
                "created_at": f.get("created_at"),
                "updated_at": f.get("updated_at"),
            }
            for f in rows
        ]

    return _handle(_run)


def _cmd_frameworks_get(args: argparse.Namespace) -> int:
    def _run() -> dict:
        return service.framework_get(
            args.book_id, args.framework_id, view=args.view
        )

    try:
        data = _run()
    except ValueError as exc:
        output.print_error(f"error: {exc}")
        return 1

    if args.markdown:
        if data.get("view") == "job":
            output.print_error(
                "error: framework is not ready (poll with frameworks wait, then retry)"
            )
            return 1
        output.print_markdown_document(data)
        return 0

    print_json(data, compact=args.compact)
    return 0


def _cmd_frameworks_generate(args: argparse.Namespace) -> int:
    mc = args.max_chunks if args.max_chunks and args.max_chunks > 0 else None
    wait = not args.async_start

    def _run() -> dict:
        cb = _progress_cb if wait else None
        return service.framework_generate(
            args.book_id,
            args.name,
            max_chunks=mc,
            progress_callback=cb,
            wait=wait,
        )

    return _handle(_run)


def _cmd_frameworks_regenerate(args: argparse.Namespace) -> int:
    mc = args.max_chunks if args.max_chunks and args.max_chunks > 0 else None
    wait = not args.async_start

    def _run() -> dict:
        cb = _progress_cb if wait else None
        return service.framework_regenerate(
            args.book_id,
            args.framework_id,
            max_chunks=mc,
            progress_callback=cb,
            wait=wait,
        )

    return _handle(_run)


def _cmd_frameworks_wait(args: argparse.Namespace) -> int:
    """Poll framework_get until completed or failed."""
    book_id = args.book_id
    framework_id = args.framework_id
    interval = max(5, args.interval)
    deadline = time.monotonic() + max(60, args.timeout)

    while time.monotonic() < deadline:
        try:
            data = service.framework_get(book_id, framework_id, view="definitive")
        except ValueError as exc:
            output.print_error(f"error: {exc}")
            return 1

        if data.get("view") == "job":
            status = (data.get("generation_status") or "running").strip().lower()
            if status == "failed":
                print_json(data, compact=args.compact)
                return 1
            line = data.get("generation_last_log_line") or data.get("note") or "running…"
            output.progress_line(f"[{status}] {line}")
            time.sleep(interval)
            continue

        print_json(data, compact=args.compact)
        return 0

    output.print_error("error: timed out waiting for framework generation")
    return 1


def _cmd_frameworks_delete(args: argparse.Namespace) -> int:
    def _run() -> dict:
        service.framework_delete(args.book_id, args.framework_id)
        return {
            "status": "ok",
            "book_id": args.book_id,
            "framework_id": args.framework_id,
        }

    return _handle(_run)


def _cmd_frameworks_ask(args: argparse.Namespace) -> int:
    return _handle(
        lambda: service.framework_answer_question(
            args.book_id,
            args.framework_id,
            args.question,
            top_k=args.top_k,
        )
    )


def _cmd_frameworks_export_docx(args: argparse.Namespace) -> int:
    def _run() -> dict:
        service.framework_export_docx(args.book_id, args.framework_id, args.output)
        return {
            "status": "ok",
            "book_id": args.book_id,
            "framework_id": args.framework_id,
            "path": args.output,
        }

    return _handle(_run)


def _cmd_frameworks_export_pdf(args: argparse.Namespace) -> int:
    def _run() -> dict:
        service.framework_export_pdf(args.book_id, args.framework_id, args.output)
        return {
            "status": "ok",
            "book_id": args.book_id,
            "framework_id": args.framework_id,
            "path": args.output,
        }

    return _handle(_run)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description=(
            "Proper Thinking AI CLI — books, frameworks, search, and Q&A "
            "(same backend as the desktop app and MCP)."
        ),
    )
    sub = parser.add_subparsers(dest="group", required=True)

    books = sub.add_parser("books", help="Book library operations")
    books_sub = books.add_subparsers(dest="command", required=True)

    p = books_sub.add_parser("list", help="List all books")
    p.set_defaults(handler=_cmd_books_list)

    p = books_sub.add_parser("show", help="Show one book")
    p.add_argument("book_id", type=int)
    p.set_defaults(handler=_cmd_books_show)

    p = books_sub.add_parser("upload", help="Upload a PDF")
    p.add_argument("path", help="Path to PDF file")
    p.set_defaults(handler=_cmd_books_upload)

    p = books_sub.add_parser("delete", help="Delete a book and related data")
    p.add_argument("book_id", type=int)
    p.set_defaults(handler=_cmd_books_delete)

    p = books_sub.add_parser("search", help="Semantic search in a book")
    p.add_argument("book_id", type=int)
    p.add_argument("-q", "--query", required=True)
    p.add_argument("-k", "--top-k", type=int, default=5)
    p.set_defaults(handler=_cmd_books_search)

    p = books_sub.add_parser("ask", help="RAG Q&A on a book")
    p.add_argument("book_id", type=int)
    p.add_argument("-q", "--question", required=True)
    p.add_argument("-k", "--top-k", type=int, default=5)
    p.set_defaults(handler=_cmd_books_ask)

    emb = books_sub.add_parser("embeddings", help="Embedding operations")
    emb_sub = emb.add_subparsers(dest="emb_command", required=True)

    p = emb_sub.add_parser("status", help="Check embedding status")
    p.add_argument("book_id", type=int)
    p.set_defaults(handler=_cmd_books_embeddings_status)

    p = emb_sub.add_parser("generate", help="Generate embeddings for a book")
    p.add_argument("book_id", type=int)
    p.set_defaults(handler=_cmd_books_embeddings_generate)

    fw = sub.add_parser("frameworks", help="Framework operations")
    fw_sub = fw.add_subparsers(dest="command", required=True)

    p = fw_sub.add_parser("list", help="List frameworks for a book")
    p.add_argument("book_id", type=int)
    p.set_defaults(handler=_cmd_frameworks_list)

    p = fw_sub.add_parser("get", help="Get framework (default: definitive view)")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument(
        "--view",
        choices=("definitive", "full"),
        default="definitive",
        help="definitive = nine-section markdown only; full = graph + audits",
    )
    p.add_argument(
        "--markdown",
        action="store_true",
        help="Print definitive_document markdown to stdout (for piping)",
    )
    _add_json_flags(p)
    p.set_defaults(handler=_cmd_frameworks_get)

    p = fw_sub.add_parser("generate", help="Start framework generation")
    p.add_argument("book_id", type=int)
    p.add_argument("--name", required=True)
    p.add_argument(
        "--async",
        action="store_true",
        dest="async_start",
        help="Return immediately; job runs in a detached process (poll with frameworks wait)",
    )
    p.add_argument("--max-chunks", type=int, default=0, help="0 = default")
    p.set_defaults(handler=_cmd_frameworks_generate, async_start=False)

    p = fw_sub.add_parser("regenerate", help="Regenerate an existing framework")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument("--async", action="store_true", dest="async_start")
    p.add_argument("--max-chunks", type=int, default=0)
    p.set_defaults(handler=_cmd_frameworks_regenerate, async_start=False)

    p = fw_sub.add_parser(
        "wait",
        help="Poll until generation completes or fails",
    )
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between polls (default 30)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Max wait seconds (default 7200)",
    )
    _add_json_flags(p)
    p.set_defaults(handler=_cmd_frameworks_wait)

    p = fw_sub.add_parser("delete", help="Delete a framework")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.set_defaults(handler=_cmd_frameworks_delete)

    p = fw_sub.add_parser("ask", help="Q&A grounded in a framework")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument("-q", "--question", required=True)
    p.add_argument("-k", "--top-k", type=int, default=5)
    p.set_defaults(handler=_cmd_frameworks_ask)

    p = fw_sub.add_parser("export-docx", help="Export framework to DOCX")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(handler=_cmd_frameworks_export_docx)

    p = fw_sub.add_parser("export-pdf", help="Export framework to PDF")
    p.add_argument("book_id", type=int)
    p.add_argument("framework_id", type=int)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(handler=_cmd_frameworks_export_pdf)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))


if __name__ == "__main__":
    sys.exit(main())
