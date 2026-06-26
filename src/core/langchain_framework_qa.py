# Framework Q&A via LangChain (governed flow: Evidence Agent + strict prompt).
# Same pattern as book Q&A: retrieve chunks, LLM with evidence rules.

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .langchain_retriever import BookRetriever
from ..storage.vector_store import VectorStore
from .app_config import OPENROUTER_BASE_URL, resolve_model_for_task

log = logging.getLogger(__name__)


# Build context string and used_chunks from LangChain documents.
def _format_context_and_chunks(docs: List[Any]) -> tuple[str, List[Dict[str, Any]]]:
    context_lines = []
    used_chunks = []
    for idx, doc in enumerate(docs, 1):
        meta = getattr(doc, "metadata", {}) or {}
        page = meta.get("page_number")
        chunk_index = meta.get("chunk_index")
        text = getattr(doc, "page_content", "") or ""
        context_lines.append(f"[Source {idx}] Page {page}, Chunk {chunk_index}")
        context_lines.append(text)
        context_lines.append("")
        used_chunks.append({
            "page_number": page,
            "chunk_index": chunk_index,
            "text": text,
        })
    return "\n".join(context_lines), used_chunks

# Run framework Q&A using LangChain (Evidence Agent = BookRetriever + governed prompt).
def run_framework_qa(
    vector_store: VectorStore,
    book_id: int,
    framework_content: str,
    framework_name: str,
    question: str,
    top_k: int = 5,
    max_completion_tokens: int = 8192,
) -> Dict[str, Any]:
    retriever = BookRetriever(
        vector_store=vector_store,
        book_id=book_id,
        top_k=top_k,
    )
    docs = retriever.invoke(question)
    if not docs:
        log.info("LangChain Framework Q&A: no docs for book_id=%s", book_id)
        return {
            "status": "not_supported",
            "answer": "Not supported by the source.",
            "used_chunks": [],
        }

    book_context, used_chunks = _format_context_and_chunks(docs)
    context_text = (
        f"## Framework: {framework_name}\n{framework_content}\n\n"
        f"## Book excerpts (only material you may use):\n{book_context}"
    )
    num_sources = len(docs)
    max_words = min(300 + 80 * num_sources, 2000)

    system_prompt = (
        "You are a strictly source-grounded assistant. Use ONLY the framework and book excerpts below.\n"
        "Rules:\n"
        "1) Do NOT use outside knowledge.\n"
        "2) If the question cannot be answered from these sources, reply exactly: 'Not supported by the source.'\n"
        "3) Prefer framework content; use book excerpts to support or clarify. Include page numbers when quoting.\n"
        "4) Keep reasoning clear and grounded in the framework and excerpts; do not invent facts.\n"
        f"5) Be concise. Keep your response under {max_words} words.\n"
    )
    user_prompt = (
        f"Question:\n{question}\n\nSources:\n{context_text}\n\n"
        f"Answer using ONLY the sources above. Keep response under {max_words} words."
    )

    llm = ChatOpenAI(
        model=resolve_model_for_task("default"),
        max_tokens=max_completion_tokens,
        temperature=0,
        openai_api_base=OPENROUTER_BASE_URL,
    )
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        response = llm.invoke(messages)
    except Exception as e:
        log.exception("LangChain Framework Q&A LLM invoke failed")
        raise RuntimeError(f"OpenRouter call failed: {e}") from e

    content = getattr(response, "content", None) or ""
    answer_text = (content or "").strip()
    if "Not supported by the source" in answer_text:
        status = "not_supported"
    else:
        status = "ok"

    log.info("LangChain Framework Q&A: book_id=%s status=%s chunks=%s", book_id, status, len(used_chunks))
    return {
        "status": status,
        "answer": answer_text,
        "used_chunks": used_chunks,
    }
