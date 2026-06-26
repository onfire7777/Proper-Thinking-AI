"""FastAPI REST API: books, RAG Q&A, chat, and frameworks (same logic as MCP + desktop)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from src.api import service

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(x_api_key: Optional[str] = Depends(_api_key_header)) -> None:
    expected = (os.getenv("PTA_API_KEY") or "").strip()
    if not expected:
        return
    if (x_api_key or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service.get_book_manager()
        yield

    app = FastAPI(
        title="Proper Thinking AI API",
        description="Books, search, RAG Q&A, chat, and frameworks (OpenRouter RAG where applicable).",
        version="1.2.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/settings", dependencies=[Depends(require_api_key)])
    def settings_get(include_api_key: bool = Query(False, description="If true, include API key (sensitive).")) -> Dict[str, Any]:
        return service.settings_get(include_api_key=include_api_key)

    class SettingsSaveBody(BaseModel):
        api_key: str = ""
        model: str = ""
        routing_preset: Optional[str] = None

    @app.post("/v1/settings", dependencies=[Depends(require_api_key)])
    def settings_save(body: SettingsSaveBody) -> Dict[str, Any]:
        return service.settings_save(body.api_key, body.model, routing_preset=body.routing_preset)

    class SettingsTestBody(BaseModel):
        api_key: Optional[str] = None
        model: Optional[str] = None

    @app.post("/v1/settings/test", dependencies=[Depends(require_api_key)])
    def settings_test(body: SettingsTestBody) -> Dict[str, Any]:
        try:
            return service.settings_test_connection(body.api_key, body.model)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/v1/books", dependencies=[Depends(require_api_key)])
    def list_books() -> List[Dict[str, Any]]:
        return service.list_books()

    @app.get("/v1/books/{book_id}", dependencies=[Depends(require_api_key)])
    def get_book(
        book_id: int,
        include_file_path: bool = Query(
            False,
            description="If true, include server filesystem path (sensitive). Default false.",
        ),
    ) -> Dict[str, Any]:
        try:
            return service.get_book_info(book_id, include_file_path=include_file_path)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.delete("/v1/books/{book_id}", dependencies=[Depends(require_api_key)])
    def delete_book(book_id: int) -> Dict[str, str]:
        try:
            service.delete_book(book_id)
            return {"status": "ok"}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/v1/books/{book_id}/search", dependencies=[Depends(require_api_key)])
    def search_book(
        book_id: int,
        q: str = Query(..., min_length=1, description="Natural language search query"),
        top_k: int = Query(5, ge=1, le=50),
    ) -> List[Dict[str, Any]]:
        try:
            return service.search_book(book_id, q, top_k=top_k)
        except ValueError as e:
            msg = str(e)
            code = 404 if "not found" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg) from e

    class QuestionBody(BaseModel):
        question: str = Field(..., min_length=1)
        top_k: int = Field(5, ge=1, le=50)

    @app.post("/v1/books/{book_id}/qa", dependencies=[Depends(require_api_key)])
    def book_qa(book_id: int, body: QuestionBody) -> Dict[str, Any]:
        try:
            return service.answer_question(book_id, body.question, top_k=body.top_k)
        except ValueError as e:
            msg = str(e)
            code = 404 if "not found" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    @app.get("/v1/books/{book_id}/embeddings", dependencies=[Depends(require_api_key)])
    def embeddings_status(book_id: int) -> Dict[str, Any]:
        try:
            return service.embeddings_status(book_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.post("/v1/books/{book_id}/embeddings", dependencies=[Depends(require_api_key)])
    def generate_embeddings(book_id: int) -> Dict[str, Any]:
        try:
            return service.generate_embeddings(book_id)
        except ValueError as e:
            msg = str(e)
            code = 404 if "not found" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg) from e

    class UploadBookBody(BaseModel):
        file_path: str = Field(..., min_length=1, description="Local filesystem path to a PDF")

    @app.post("/v1/books/upload", dependencies=[Depends(require_api_key)])
    def upload_book(body: UploadBookBody) -> Dict[str, Any]:
        try:
            return service.upload_book(body.file_path)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e

    def _chat_http_error(exc: ValueError) -> HTTPException:
        msg = str(exc)
        low = msg.lower()
        code = 404 if ("not found" in low or "does not belong" in low) else 400
        return HTTPException(status_code=code, detail=msg)

    class CreateConversationBody(BaseModel):
        title: str = ""

    class PatchConversationTitleBody(BaseModel):
        title: str = Field(..., min_length=1)

    class ChatMessageBody(BaseModel):
        role: Literal["user", "assistant"]
        content: str = Field(..., min_length=1)
        used_chunks: Optional[List[Dict[str, Any]]] = None
        status: Optional[str] = None

    @app.get(
        "/v1/books/{book_id}/conversations",
        dependencies=[Depends(require_api_key)],
    )
    def chat_list_conversations(book_id: int) -> List[Dict[str, Any]]:
        try:
            return service.chat_list_conversations(book_id)
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.post(
        "/v1/books/{book_id}/conversations",
        dependencies=[Depends(require_api_key)],
    )
    def chat_create_conversation(book_id: int, body: CreateConversationBody) -> Dict[str, int]:
        try:
            cid = service.chat_create_conversation(book_id, body.title)
            return {"id": cid}
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.get(
        "/v1/books/{book_id}/conversations/{conversation_id}",
        dependencies=[Depends(require_api_key)],
    )
    def chat_get_conversation(book_id: int, conversation_id: int) -> Dict[str, Any]:
        try:
            return service.chat_get_conversation(book_id, conversation_id)
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.patch(
        "/v1/books/{book_id}/conversations/{conversation_id}",
        dependencies=[Depends(require_api_key)],
    )
    def chat_patch_title(
        book_id: int, conversation_id: int, body: PatchConversationTitleBody
    ) -> Dict[str, str]:
        try:
            service.chat_update_conversation_title(book_id, conversation_id, body.title)
            return {"status": "ok"}
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.delete(
        "/v1/books/{book_id}/conversations/{conversation_id}",
        dependencies=[Depends(require_api_key)],
    )
    def chat_delete(book_id: int, conversation_id: int) -> Dict[str, str]:
        try:
            service.chat_delete_conversation(book_id, conversation_id)
            return {"status": "ok"}
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.get(
        "/v1/books/{book_id}/conversations/{conversation_id}/messages",
        dependencies=[Depends(require_api_key)],
    )
    def chat_messages(book_id: int, conversation_id: int) -> List[Dict[str, Any]]:
        try:
            return service.chat_list_messages(book_id, conversation_id)
        except ValueError as e:
            raise _chat_http_error(e) from e

    @app.post(
        "/v1/books/{book_id}/conversations/{conversation_id}/messages",
        dependencies=[Depends(require_api_key)],
    )
    def chat_add_message(
        book_id: int, conversation_id: int, body: ChatMessageBody
    ) -> Dict[str, int]:
        try:
            mid = service.chat_add_message(
                book_id,
                conversation_id,
                body.role,
                body.content,
                used_chunks=body.used_chunks,
                status=body.status,
            )
            return {"id": mid}
        except ValueError as e:
            raise _chat_http_error(e) from e

    class GenerateFrameworkBody(BaseModel):
        name: str = Field(..., min_length=1)
        max_chunks: Optional[int] = Field(None, ge=1)

    class FrameworkQuestionBody(BaseModel):
        question: str = Field(..., min_length=1)
        top_k: int = Field(5, ge=1, le=50)

    @app.get(
        "/v1/books/{book_id}/frameworks",
        dependencies=[Depends(require_api_key)],
    )
    def framework_list(book_id: int) -> List[Dict[str, Any]]:
        try:
            return service.framework_list(book_id)
        except ValueError as e:
            raise _framework_http_error(e) from e

    @app.post(
        "/v1/books/{book_id}/frameworks",
        dependencies=[Depends(require_api_key)],
    )
    def framework_create(book_id: int, body: GenerateFrameworkBody) -> Dict[str, Any]:
        try:
            return service.framework_generate(
                book_id, body.name, max_chunks=body.max_chunks, wait=False
            )
        except ValueError as e:
            raise _framework_http_error(e) from e

    @app.get(
        "/v1/books/{book_id}/frameworks/{framework_id}",
        dependencies=[Depends(require_api_key)],
    )
    def framework_detail(
        book_id: int,
        framework_id: int,
        view: str = Query(
            "full",
            description="definitive = nine-section markdown only (AI-safe); full = nodes, edges, audits, display",
        ),
    ) -> Dict[str, Any]:
        try:
            return service.framework_get(book_id, framework_id, view=view)
        except ValueError as e:
            raise _framework_http_error(e) from e

    @app.delete(
        "/v1/books/{book_id}/frameworks/{framework_id}",
        dependencies=[Depends(require_api_key)],
    )
    def framework_remove(book_id: int, framework_id: int) -> Dict[str, str]:
        try:
            service.framework_delete(book_id, framework_id)
            return {"status": "ok"}
        except ValueError as e:
            raise _framework_http_error(e) from e

    @app.post(
        "/v1/books/{book_id}/frameworks/{framework_id}/regenerate",
        dependencies=[Depends(require_api_key)],
    )
    def framework_regenerate(
        book_id: int,
        framework_id: int,
        max_chunks: Optional[int] = Query(None, ge=1),
    ) -> Dict[str, Any]:
        try:
            return service.framework_regenerate(
                book_id, framework_id, max_chunks=max_chunks, wait=False
            )
        except ValueError as e:
            raise _framework_http_error(e) from e

    @app.post(
        "/v1/books/{book_id}/frameworks/{framework_id}/qa",
        dependencies=[Depends(require_api_key)],
    )
    def framework_qa(
        book_id: int, framework_id: int, body: FrameworkQuestionBody
    ) -> Dict[str, Any]:
        try:
            return service.framework_answer_question(
                book_id, framework_id, body.question, top_k=body.top_k
            )
        except ValueError as e:
            raise _framework_http_error(e) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    class ExportFrameworkBody(BaseModel):
        output_path: str = Field(..., min_length=1, description="Local filesystem output path")

    @app.post(
        "/v1/books/{book_id}/frameworks/{framework_id}/export/docx",
        dependencies=[Depends(require_api_key)],
    )
    def framework_export_docx(book_id: int, framework_id: int, body: ExportFrameworkBody) -> Dict[str, str]:
        try:
            service.framework_export_docx(book_id, framework_id, body.output_path)
            return {"status": "ok"}
        except ValueError as e:
            raise _framework_http_error(e) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.post(
        "/v1/books/{book_id}/frameworks/{framework_id}/export/pdf",
        dependencies=[Depends(require_api_key)],
    )
    def framework_export_pdf(book_id: int, framework_id: int, body: ExportFrameworkBody) -> Dict[str, str]:
        try:
            service.framework_export_pdf(book_id, framework_id, body.output_path)
            return {"status": "ok"}
        except ValueError as e:
            raise _framework_http_error(e) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e

    @app.get(
        "/v1/books/{book_id}/mindmap",
        dependencies=[Depends(require_api_key)],
    )
    def mindmap_graph(
        book_id: int,
        framework_id: Optional[int] = Query(
            None, description="Optional framework_id; defaults to the first framework for the book."
        ),
    ) -> Dict[str, Any]:
        try:
            return service.mindmap_graph(book_id, framework_id=framework_id)
        except ValueError as e:
            msg = str(e)
            code = 404 if "not found" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e

    return app
