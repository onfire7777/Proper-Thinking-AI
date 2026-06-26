# Phase A: LangChain retriever wrapping our VectorStore (per-book, closed-world).
# Used by RAG chain (Phase B) and framework extraction pipeline (Phase C).

import logging
from typing import List

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from pydantic import ConfigDict

from ..storage.vector_store import VectorStore

log = logging.getLogger(__name__)


class BookRetriever(BaseRetriever):
    """LangChain retriever that searches only a single book's vector store."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: VectorStore
    book_id: int
    top_k: int = 5

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> List[Document]:
        results = self.vector_store.search(self.book_id, query, self.top_k)
        docs = []
        for r in results:
            docs.append(
                Document(
                    page_content=r["text"],
                    metadata={
                        "page_number": r["page_number"],
                        "chunk_index": r["chunk_index"],
                        "book_id": self.book_id,
                    },
                )
            )
        if run_manager:
            log.debug("BookRetriever book_id=%s top_k=%s hits=%s", self.book_id, self.top_k, len(docs))
        return docs
