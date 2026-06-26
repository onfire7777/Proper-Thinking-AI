"""
MCP (stdio) server — mirrors the HTTP API (books, RAG, chat, frameworks).

Run: ``python -m src.api mcp`` from repo root.
Do not log to stdout (stdio is the MCP protocol stream); use stderr / logging only.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from src.api import service

log = logging.getLogger(__name__)


def build_mcp() -> FastMCP:
    mcp = FastMCP(
        "proper-thinking-ai",
        instructions=(
            "Proper Thinking AI: books, semantic search, RAG Q&A (OpenRouter), per-book chat, and "
            "frameworks (list/get/generate/regenerate/delete, plus framework-grounded Q&A). "
            "Framework AI context: use framework_get with view=definitive (default). Read "
            "definitive_document verbatim — the nine-section canonical framework (Metadata through "
            "Scope and Limits). Do not summarize or rewrite it. Do not use nodes/edges for text "
            "context; use mindmap_* tools only when graph structure is required. "
            "framework_get view=full returns audits, display.*, nodes, and edges (large payload). "
            "framework_generate and framework_regenerate return immediately (generation_status=running, "
            "generation_started_at, generation_last_log_line). Poll framework_get until completed or failed; "
            "while running or failed, framework_get returns job status only (view=job, no partial content). "
            "Embeddings required for search, book QA, and framework QA. "
            "Scoped routes validate framework_id belongs to book_id."
        ),
    )

    @mcp.tool()
    def list_books() -> str:
        """List all uploaded books (id, title, filename, pages, chunk_count, embeddings_generated)."""
        try:
            return service.json_dumps(service.list_books())
        except Exception as exc:  # noqa: BLE001
            log.exception("list_books")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def get_book_info(book_id: int, include_file_path: bool = False) -> str:
        """Get one book's metadata. Set include_file_path true only if you need the local file path."""
        try:
            return service.json_dumps(
                service.get_book_info(book_id, include_file_path=include_file_path)
            )
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("get_book_info")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def search_book(book_id: int, query: str, top_k: int = 5) -> str:
        """Semantic search: returns matching chunks (requires embeddings for the book)."""
        try:
            return service.json_dumps(service.search_book(book_id, query, top_k=top_k))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("search_book")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def answer_book_question(book_id: int, question: str, top_k: int = 5) -> str:
        """Ask a question answered only from book sources (RAG via OpenRouter). Returns status, answer, used_chunks."""
        try:
            return service.json_dumps(service.answer_question(book_id, question, top_k=top_k))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except RuntimeError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("answer_book_question")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def settings_get(include_api_key: bool = False) -> str:
        """Get current OpenRouter settings (API key masked unless include_api_key=true)."""
        try:
            return service.json_dumps(service.settings_get(include_api_key=include_api_key))
        except Exception as exc:  # noqa: BLE001
            log.exception("settings_get")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def settings_save(api_key: str = "", model: str = "", routing_preset: str = "") -> str:
        """Persist OpenRouter key/model/preset to data/config.json and apply to this process."""
        try:
            rp = (routing_preset or "").strip() or None
            return service.json_dumps(service.settings_save(api_key or "", model or "", routing_preset=rp))
        except Exception as exc:  # noqa: BLE001
            log.exception("settings_save")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def settings_test_connection(api_key: str = "", model: str = "") -> str:
        """Test OpenRouter connectivity for the provided key/model (falls back to env if omitted)."""
        try:
            k = (api_key or "").strip() or None
            m = (model or "").strip() or None
            return service.json_dumps(service.settings_test_connection(k, m))
        except Exception as exc:  # noqa: BLE001
            log.exception("settings_test_connection")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def delete_book(book_id: int) -> str:
        """Delete a book and all associated data (chunks, embeddings, frameworks)."""
        try:
            service.delete_book(book_id)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("delete_book")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def embeddings_status(book_id: int) -> str:
        """Check whether embeddings are generated for a book."""
        try:
            return service.json_dumps(service.embeddings_status(book_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("embeddings_status")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def generate_embeddings(book_id: int) -> str:
        """Generate embeddings for a book's chunks (required for search/QA/frameworks)."""
        try:
            return service.json_dumps(service.generate_embeddings(book_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("generate_embeddings")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def upload_book(file_path: str) -> str:
        """Upload and process a PDF by local file path; returns book_id/title/pages/chunk_count."""
        try:
            return service.json_dumps(service.upload_book(file_path))
        except FileNotFoundError as e:
            return service.json_dumps({"error": str(e)})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("upload_book")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_list_conversations(book_id: int) -> str:
        """List chat threads for a book (newest first)."""
        try:
            return service.json_dumps(service.chat_list_conversations(book_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_list_conversations")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_create_conversation(book_id: int, title: str = "") -> str:
        """Create a new chat thread; returns JSON with id."""
        try:
            cid = service.chat_create_conversation(book_id, title)
            return service.json_dumps({"id": cid})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_create_conversation")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_get_conversation(book_id: int, conversation_id: int) -> str:
        """Get one conversation row (id, book_id, title, timestamps)."""
        try:
            return service.json_dumps(service.chat_get_conversation(book_id, conversation_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_get_conversation")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_update_conversation_title(book_id: int, conversation_id: int, title: str) -> str:
        """Rename a chat thread."""
        try:
            service.chat_update_conversation_title(book_id, conversation_id, title)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_update_conversation_title")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_delete_conversation(book_id: int, conversation_id: int) -> str:
        """Delete a chat thread and its messages."""
        try:
            service.chat_delete_conversation(book_id, conversation_id)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_delete_conversation")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_list_messages(book_id: int, conversation_id: int) -> str:
        """List messages in a thread (role, content, used_chunks, status)."""
        try:
            return service.json_dumps(service.chat_list_messages(book_id, conversation_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_list_messages")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def chat_add_message(
        book_id: int,
        conversation_id: int,
        role: str,
        content: str,
        used_chunks_json: str = "",
        status: str = "",
    ) -> str:
        """Append a user or assistant message. Optional used_chunks_json: JSON array of chunk dicts; empty omits."""
        try:
            chunks: Optional[List[Dict[str, Any]]] = None
            raw = (used_chunks_json or "").strip()
            if raw:
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    return service.json_dumps({"error": "used_chunks_json must be a JSON array"})
                chunks = parsed
            st = (status or "").strip() or None
            mid = service.chat_add_message(
                book_id, conversation_id, role, content, used_chunks=chunks, status=st
            )
            return service.json_dumps({"id": mid})
        except json.JSONDecodeError as e:
            return service.json_dumps({"error": f"used_chunks_json: {e}"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("chat_add_message")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def framework_list(book_id: int) -> str:
        """List saved frameworks for a book (summary rows)."""
        try:
            return service.json_dumps(service.framework_list(book_id))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("framework_list")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def framework_get(book_id: int, framework_id: int, view: str = "definitive") -> str:
        """Load one framework. Default view=definitive returns only definitive_document (nine canonical sections) plus metadata — use this for AI context. view=full adds nodes, edges, audits, and display.* (large). While running or failed, returns job status only regardless of view."""
        try:
            return service.json_dumps(
                service.framework_get(book_id, framework_id, view=view)
            )
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("framework_get")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def framework_generate(book_id: int, name: str, max_chunks: int = 0) -> str:
        """Start framework generation (async). Returns job status immediately; poll framework_get. max_chunks 0 = default."""
        try:
            mc = None if max_chunks <= 0 else max_chunks
            out = service.framework_generate(book_id, name, max_chunks=mc, wait=False)
            return service.json_dumps(out)
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("framework_generate")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def framework_regenerate(book_id: int, framework_id: int, max_chunks: int = 0) -> str:
        """Start framework regeneration (async). Returns job status immediately; poll framework_get. max_chunks 0 = default."""
        try:
            mc = None if max_chunks <= 0 else max_chunks
            out = service.framework_regenerate(book_id, framework_id, max_chunks=mc, wait=False)
            return service.json_dumps(out)
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("framework_regenerate")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def framework_delete(book_id: int, framework_id: int) -> str:
        """Delete a framework and its stored nodes/edges."""
        try:
            service.framework_delete(book_id, framework_id)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("framework_delete")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def answer_framework_question(book_id: int, framework_id: int, question: str, top_k: int = 5) -> str:
        """Ask about a framework using definitive document + book RAG (OpenRouter). Returns status, answer, used_chunks."""
        try:
            return service.json_dumps(
                service.framework_answer_question(book_id, framework_id, question, top_k=top_k)
            )
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except RuntimeError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("answer_framework_question")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def export_framework_docx(book_id: int, framework_id: int, output_path: str) -> str:
        """Export a framework to DOCX at output_path."""
        try:
            service.framework_export_docx(book_id, framework_id, output_path)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("export_framework_docx")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def export_framework_pdf(book_id: int, framework_id: int, output_path: str) -> str:
        """Export a framework to PDF at output_path."""
        try:
            service.framework_export_pdf(book_id, framework_id, output_path)
            return service.json_dumps({"status": "ok"})
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("export_framework_pdf")
            return service.json_dumps({"error": str(exc)})

    def _mindmap_graph_payload(book_id: int, framework_id: int) -> str:
        fid = None if framework_id <= 0 else int(framework_id)
        return service.json_dumps(service.mindmap_graph(book_id, framework_id=fid))

    @mcp.tool()
    def mindmap_get_graph(book_id: int, framework_id: int = 0) -> str:
        """Mindmap canvas: full vis-network JSON (version, nodes, edges). Filtered view, not raw framework rows. framework_id 0 = newest framework for the book."""
        try:
            return _mindmap_graph_payload(book_id, framework_id)
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("mindmap_get_graph")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def mindmap_graph_summary(book_id: int, framework_id: int = 0) -> str:
        """Mindmap: small JSON with framework_id resolved, name, node/edge counts, large_graph hint. Call before mindmap_get_graph for big books."""
        try:
            fid = None if framework_id <= 0 else int(framework_id)
            return service.json_dumps(service.mindmap_graph_summary(book_id, framework_id=fid))
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("mindmap_graph_summary")
            return service.json_dumps({"error": str(exc)})

    @mcp.tool()
    def mindmap_graph(book_id: int, framework_id: int = 0) -> str:
        """Deprecated: same payload as mindmap_get_graph. Prefer mindmap_get_graph + mindmap_graph_summary."""
        try:
            return _mindmap_graph_payload(book_id, framework_id)
        except ValueError as e:
            return service.json_dumps({"error": str(e)})
        except Exception as exc:  # noqa: BLE001
            log.exception("mindmap_graph")
            return service.json_dumps({"error": str(exc)})

    return mcp


def run_stdio() -> None:
    # Human feedback only on stderr — stdout is reserved for MCP JSON-RPC.
    print("MCP server started. Press Ctrl+C to stop.", file=sys.stderr)
    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    build_mcp().run(transport="stdio")
