"""
Shared BookManager access and response shaping for HTTP + MCP.

Bootstraps env the same way as ``main.py`` (dotenv + ``load_json_into_env``)
before constructing ``BookManager``.
"""

from __future__ import annotations

import json
import logging
import threading
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

_book_manager_lock = threading.Lock()
_book_manager = None


def bind_book_manager(bm) -> None:
    """Attach an existing ``BookManager`` (e.g. desktop app). API/MCP-only processes can omit this."""
    global _book_manager
    with _book_manager_lock:
        _book_manager = bm
        log.info("BookManager bound for API/service layer")


def get_book_manager():
    """Lazily construct a single ``BookManager`` (thread-safe)."""
    global _book_manager
    with _book_manager_lock:
        if _book_manager is None:
            from dotenv import load_dotenv

            from src.core.app_config import load_json_into_env
            from src.core.book_manager import BookManager

            load_dotenv()
            load_json_into_env()
            _book_manager = BookManager()
            log.info("BookManager initialized for API/MCP")
        return _book_manager


def sanitize_book_info(info: Dict[str, Any], *, include_file_path: bool) -> Dict[str, Any]:
    """Return a copy of book info, optionally stripping ``file_path`` for external clients."""
    out = deepcopy(info)
    if not include_file_path:
        out.pop("file_path", None)
    return out


def list_books() -> List[Dict[str, Any]]:
    return get_book_manager().list_books()


def get_book_info(book_id: int, *, include_file_path: bool = False) -> Dict[str, Any]:
    info = get_book_manager().get_book_info(book_id)
    return sanitize_book_info(info, include_file_path=include_file_path)


def search_book(book_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    return get_book_manager().search_book(book_id, query, top_k=top_k)


def answer_question(book_id: int, question: str, top_k: int = 5) -> Dict[str, Any]:
    return get_book_manager().answer_question(book_id, question, top_k=top_k)


def embeddings_status(book_id: int) -> Dict[str, Any]:
    _assert_book_exists(book_id)
    bm = get_book_manager()
    return {"book_id": book_id, "embeddings_generated": bool(bm.db.get_embeddings_status(book_id))}


def generate_embeddings(book_id: int) -> Dict[str, Any]:
    _assert_book_exists(book_id)
    return get_book_manager().generate_embeddings(book_id)


def delete_book(book_id: int) -> None:
    _assert_book_exists(book_id)
    get_book_manager().delete_book(book_id)


def upload_book(file_path: str) -> Dict[str, Any]:
    # BookManager handles validation (exists, pdf extension) and copies into books_dir.
    return get_book_manager().upload_book(file_path)


def mindmap_graph(book_id: int, framework_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Return the same graph payload the Mindmap tab renders (nodes/edges).
    If framework_id is omitted, uses the newest/first framework for the book when present.
    """
    _assert_book_exists(book_id)
    if framework_id is None:
        fws = get_book_manager().list_frameworks(book_id)
        if not fws:
            return {"version": 1, "nodes": [], "edges": []}
        framework_id = int(fws[0]["id"])
    fw = _framework_for_book(book_id, int(framework_id))
    from src.ui.mindmap_graph_payload import build_graph_payload

    return build_graph_payload(fw)


def mindmap_graph_summary(book_id: int, framework_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Compact mindmap stats (same node/edge filtering as mindmap_graph).
    Use when you only need counts and which framework was resolved, not the full graph JSON.
    """
    _assert_book_exists(book_id)
    bm = get_book_manager()
    fws = bm.list_frameworks(book_id)
    if not fws:
        return {
            "book_id": book_id,
            "framework_id": None,
            "framework_name": None,
            "node_count": 0,
            "edge_count": 0,
            "large_graph": False,
            "graph_version": 1,
            "note": "No frameworks for this book; mindmap is empty.",
        }
    resolved: int
    fname: Optional[str] = None
    if framework_id is None:
        resolved = int(fws[0]["id"])
        fname = (fws[0].get("name") or "").strip() or None
    else:
        resolved = int(framework_id)
        for row in fws:
            if int(row.get("id", -1)) == resolved:
                fname = (row.get("name") or "").strip() or None
                break
    fw = _framework_for_book(book_id, resolved)
    from src.ui.mindmap_graph_payload import build_graph_payload

    g = build_graph_payload(fw)
    nodes = g.get("nodes") or []
    edges = g.get("edges") or []
    meta = g.get("meta") or {}
    return {
        "book_id": book_id,
        "framework_id": resolved,
        "framework_name": fname,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "large_graph": bool(meta.get("large_graph")),
        "graph_version": g.get("version", 1),
    }


def settings_get(*, include_api_key: bool = False) -> Dict[str, Any]:
    from src.core.app_config import get_effective_settings

    s = get_effective_settings()
    key = (s.get("openrouter_api_key") or "").strip()
    if not include_api_key and key:
        s = dict(s)
        s["openrouter_api_key"] = ("*" * 6) + key[-4:]
    return s


def settings_save(api_key: str, model: str, routing_preset: Optional[str] = None) -> Dict[str, Any]:
    from src.core.app_config import save_settings

    save_settings(api_key or "", model or "", routing_preset)
    return settings_get(include_api_key=False)


def settings_test_connection(api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    from src.core.llm_client import LLMClient

    client = LLMClient(api_key=(api_key or "").strip() or None, model=(model or "").strip() or None)
    ok, msg = client.test_connection()
    return {"ok": bool(ok), "message": msg}


def _assert_book_exists(book_id: int) -> None:
    bm = get_book_manager()
    if not bm.db.get_book_by_id(book_id):
        raise ValueError(f"Book with ID {book_id} not found")


def _conversation_for_book(book_id: int, conversation_id: int) -> Dict[str, Any]:
    _assert_book_exists(book_id)
    conv = get_book_manager().chat_get_conversation(conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found")
    if int(conv["book_id"]) != int(book_id):
        raise ValueError("Conversation does not belong to this book")
    return conv


def chat_list_conversations(book_id: int) -> List[Dict[str, Any]]:
    _assert_book_exists(book_id)
    return get_book_manager().chat_list_conversations(book_id)


def chat_create_conversation(book_id: int, title: str = "") -> int:
    _assert_book_exists(book_id)
    return get_book_manager().chat_create_conversation(book_id, title)


def chat_get_conversation(book_id: int, conversation_id: int) -> Dict[str, Any]:
    return _conversation_for_book(book_id, conversation_id)


def chat_update_conversation_title(book_id: int, conversation_id: int, title: str) -> None:
    _conversation_for_book(book_id, conversation_id)
    get_book_manager().chat_update_conversation_title(conversation_id, title)


def chat_delete_conversation(book_id: int, conversation_id: int) -> None:
    _conversation_for_book(book_id, conversation_id)
    get_book_manager().chat_delete_conversation(conversation_id)


def chat_list_messages(book_id: int, conversation_id: int) -> List[Dict[str, Any]]:
    _conversation_for_book(book_id, conversation_id)
    return get_book_manager().chat_list_messages(conversation_id)


def chat_add_message(
    book_id: int,
    conversation_id: int,
    role: str,
    content: str,
    used_chunks: Optional[List[Dict[str, Any]]] = None,
    status: Optional[str] = None,
) -> int:
    _conversation_for_book(book_id, conversation_id)
    r = (role or "").strip().lower()
    if r not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")
    return get_book_manager().chat_add_message(
        conversation_id, r, content, used_chunks=used_chunks, status=status
    )


def _framework_for_book(book_id: int, framework_id: int) -> Dict[str, Any]:
    _assert_book_exists(book_id)
    bm = get_book_manager()
    try:
        fw = bm.get_framework(framework_id)
    except ValueError as exc:
        raise ValueError(f"Framework {framework_id} not found for book {book_id}") from exc
    if int(fw["book_id"]) != int(book_id):
        raise ValueError(f"Framework {framework_id} not found for book {book_id}")
    return fw


def framework_list(book_id: int) -> List[Dict[str, Any]]:
    return get_book_manager().list_frameworks(book_id)


def framework_get(
    book_id: int,
    framework_id: int,
    *,
    view: str = "full",
) -> Dict[str, Any]:
    from src.core.framework_display import (
        FRAMEWORK_GET_VIEW_DEFINITIVE,
        build_framework_definitive_payload,
        build_framework_job_status_payload,
        enrich_framework_dict,
        is_framework_content_gated,
        normalize_framework_get_view,
    )

    resolved_view = normalize_framework_get_view(view, default="full")
    fw = _framework_for_book(book_id, framework_id)
    if is_framework_content_gated(fw):
        return build_framework_job_status_payload(fw)
    if resolved_view == FRAMEWORK_GET_VIEW_DEFINITIVE:
        return build_framework_definitive_payload(fw)
    return enrich_framework_dict(fw)


def framework_generate(
    book_id: int,
    name: str,
    max_chunks: Optional[int] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    *,
    wait: bool = True,
) -> Dict[str, Any]:
    _assert_book_exists(book_id)
    return get_book_manager().generate_framework(
        book_id,
        name,
        max_chunks=max_chunks,
        progress_callback=progress_callback,
        wait=wait,
    )


def framework_regenerate(
    book_id: int,
    framework_id: int,
    max_chunks: Optional[int] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    *,
    wait: bool = True,
) -> Dict[str, Any]:
    _framework_for_book(book_id, framework_id)
    return get_book_manager().regenerate_framework(
        framework_id,
        max_chunks=max_chunks,
        progress_callback=progress_callback,
        wait=wait,
    )


def framework_delete(book_id: int, framework_id: int) -> None:
    _framework_for_book(book_id, framework_id)
    get_book_manager().delete_framework(framework_id)


def framework_answer_question(
    book_id: int, framework_id: int, question: str, top_k: int = 5
) -> Dict[str, Any]:
    _framework_for_book(book_id, framework_id)
    return get_book_manager().answer_question_about_framework(
        book_id, framework_id, question, top_k
    )


def _markdown_to_simple_html(md: str) -> str:
    """Very small markdown→HTML for framework export (headings, bullets, paragraphs)."""
    import html as _html
    lines = (md or "").splitlines()
    parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in lines:
        s = (raw or "").rstrip()
        if not s.strip():
            close_list()
            continue
        if s.startswith("### "):
            close_list()
            parts.append(f"<h3>{_html.escape(s[4:].strip())}</h3>")
            continue
        if s.startswith("## "):
            close_list()
            parts.append(f"<h2>{_html.escape(s[3:].strip())}</h2>")
            continue
        if s.startswith("# "):
            close_list()
            parts.append(f"<h1>{_html.escape(s[2:].strip())}</h1>")
            continue
        if s.lstrip().startswith(("- ", "* ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_html.escape(s.lstrip()[2:].strip())}</li>")
            continue
        close_list()
        parts.append(f"<p>{_html.escape(s.strip())}</p>")
    close_list()
    return "".join(parts) or "<p></p>"


def framework_export_docx(book_id: int, framework_id: int, output_path: str) -> None:
    fw = _framework_for_book(book_id, framework_id)
    from src.ui.docx_export import export_framework_to_docx

    export_framework_to_docx(fw, output_path)


def framework_export_pdf(book_id: int, framework_id: int, output_path: str) -> None:
    fw = _framework_for_book(book_id, framework_id)
    name = (fw.get("name") or "Framework").strip() or "Framework"
    from src.core.mechanical_audit import definitive_document_for_export
    from src.ui.pdf_export import export_framework_to_pdf_file

    md = definitive_document_for_export(fw) or ""
    body_html = _markdown_to_simple_html(md)
    export_framework_to_pdf_file(name, body_html, output_path)


def json_dumps(obj: Any) -> str:
    """JSON for tool bodies (handles float from similarity scores)."""
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
