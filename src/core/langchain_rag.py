# Phase B: Book-level Q&A via a single LangChain RAG flow.
# Uses BookRetriever + ChatOpenAI; preserves Phase 1 rules (quotes, pages, "Not supported by the source").

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from .langchain_retriever import BookRetriever
from ..storage.vector_store import VectorStore
from .model_client import create_chat_model

log = logging.getLogger(__name__)


def _format_context_and_chunks(docs: List[Any]) -> tuple[str, List[Dict[str, Any]]]:
    """Build context string and used_chunks list from LangChain documents."""
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


def run_qa(
    vector_store: VectorStore,
    book_id: int,
    question: str,
    top_k: int = 5,
    max_completion_tokens: int = 8192,
) -> Dict[str, Any]:
    """
    Run book-level Q&A using LangChain retriever + OpenAI.
    Returns { status, answer, used_chunks } in the same shape as ReasoningEngine.answer_question.
    """
    retriever = BookRetriever(
        vector_store=vector_store,
        book_id=book_id,
        top_k=top_k,
    )
    docs = retriever.invoke(question)
    if not docs:
        log.info("LangChain RAG: no docs for book_id=%s", book_id)
        return {
            "status": "not_supported",
            "answer": "Not supported by the source.",
            "used_chunks": [],
        }

    context_text, used_chunks = _format_context_and_chunks(docs)
    num_sources = len(docs)
    max_words = min(300 + 80 * num_sources, 2000)

    system_prompt = (
        "You are a strictly source-grounded reasoning assistant. "
        "You may ONLY use the provided source excerpts from the selected book to answer. "
        "Rules:\n"
        "1) Do NOT use any outside knowledge, training data, or assumptions.\n"
        "2) If the question cannot be answered from the sources, reply exactly: 'Not supported by the source.'\n"
        "3) Separate your response into two sections:\n"
        "   - 'What the book says:' use only direct quotes with page references.\n"
        "   - 'What is inferred:' explicit logical inferences based ONLY on the quotes; keep reasoning clear.\n"
        "4) Always include page numbers when quoting.\n"
        "5) Do not invent citations, facts, or authors.\n"
        f"6) Be concise. Keep your response under {max_words} words.\n"
    )
    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Sources from the book (only material you may use):\n{context_text}\n\n"
        f"Using ONLY the sources above, answer the question following the rules. Keep response under {max_words} words."
    )

    llm = create_chat_model("default", max_completion_tokens)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        response = llm.invoke(messages)
    except Exception as e:
        log.exception("LangChain RAG LLM invoke failed")
        raise RuntimeError(f"AI provider call failed: {e}") from e

    content = getattr(response, "content", None) or ""
    answer_text = (content or "").strip()
    if "Not supported by the source" in answer_text:
        status = "not_supported"
    else:
        status = "ok"

    log.info("LangChain RAG: book_id=%s status=%s chunks=%s", book_id, status, len(used_chunks))
    return {
        "status": status,
        "answer": answer_text,
        "used_chunks": used_chunks,
    }
