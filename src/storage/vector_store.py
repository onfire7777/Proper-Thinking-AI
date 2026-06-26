import os
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from .embedder import Embedder

# Manages ChromaDB collections for book embeddings with isolation
class VectorStore:
    
    # Initialize ChromaDB client and embedding model
    def __init__(self, persist_directory: str = "data/chroma_db", embedding_model: str = "all-MiniLM-L6-v2"):
        os.makedirs(persist_directory, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.embedding_model = embedding_model
        self._embedder = None
        self.persist_directory = persist_directory
    
    # Lazy load embedder only when needed
    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(self.embedding_model)
        return self._embedder
    
    # Generate collection name for a book
    def _get_collection_name(self, book_id: int) -> str:
        return f"book_{book_id}"
    
    # Create or get collection for a book
    def create_collection(self, book_id: int) -> chromadb.Collection:
        
        collection_name = self._get_collection_name(book_id)
        try:
            collection = self.client.get_collection(name=collection_name)
        except:
            collection = self.client.create_collection(
                name=collection_name,
                metadata={"book_id": book_id}
            )
        return collection
    
    # Add chunk embeddings to book's collection
    def add_chunks(self, book_id: int, chunks: List[Dict[str, any]]):
        if self.collection_exists(book_id):
            self.delete_collection(book_id)
        
        collection = self.create_collection(book_id)
        
        texts = [chunk['chunk_text'] for chunk in chunks]
        embedder = self._get_embedder()
        embeddings = embedder.embed_batch(texts)
        
        ids = [f"chunk_{chunk['id']}" for chunk in chunks]
        metadatas = [
            {
                "chunk_id": str(chunk['id']),
                "page_number": str(chunk['page_number']),
                "chunk_index": str(chunk['chunk_index'])
            }
            for chunk in chunks
        ]
        
        collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )
    
    # Search for relevant chunks in a book
    def search(self, book_id: int, query: str, top_k: int = 5) -> List[Dict[str, any]]:
        
        collection = self.create_collection(book_id)
        
        embedder = self._get_embedder()
        query_embedding = embedder.embed_text(query)
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        if not results['ids'] or not results['ids'][0]:
            return []
        
        search_results = []
        for i in range(len(results['ids'][0])):
            metadata = results['metadatas'][0][i]
            chunk_id = metadata['chunk_id']
            if isinstance(chunk_id, str):
                chunk_id = int(chunk_id)
            search_results.append({
                'chunk_id': chunk_id,
                'page_number': int(metadata['page_number']),
                'chunk_index': int(metadata['chunk_index']),
                'text': results['documents'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None
            })
        
        return search_results
    
    # Delete collection for a book
    def delete_collection(self, book_id: int):
        collection_name = self._get_collection_name(book_id)
        try:
            self.client.delete_collection(name=collection_name)
        except:
            pass
    
    # Check if collection exists for a book
    def collection_exists(self, book_id: int) -> bool:
        collection_name = self._get_collection_name(book_id)
        try:
            self.client.get_collection(name=collection_name)
            return True
        except:
            return False
