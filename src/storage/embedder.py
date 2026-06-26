from __future__ import annotations

from typing import List, Optional, Any

# Generates embeddings for text using Sentence Transformers
class Embedder:
    
    # Initialize embedding model
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            # Lazy import: keeps the GUI/MCP responsive and prevents hard-crash at startup in frozen apps.
            from sentence_transformers import SentenceTransformer  # type: ignore

            self.model = SentenceTransformer(model_name)
            self.model.eval()
        except Exception as exc:
            message = (
                "Failed to load embedding model. This usually happens when the model "
                "cannot be downloaded from Hugging Face (no internet connection, DNS issues, "
                "or blocked access). Embedding generation and semantic search will not work "
                "until the model is available.\n\n"
                f"Original error: {exc}"
            )
            raise RuntimeError(message) from exc
    
    # Generate embedding for a single text
    def embed_text(self, text: str) -> List[float]:
        embedding = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return embedding.tolist()
    
    # Generate embeddings for multiple texts efficiently
    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            # Keep this disabled for frozen/windowed builds where stderr/stdout may
            # not be attached to a TTY and tqdm can crash on `.isatty()`.
            show_progress_bar=False,
        )
        return embeddings.tolist()
