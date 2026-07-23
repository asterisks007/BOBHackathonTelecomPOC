"""
ChromaDB vector store wrapper for RAG (Retrieval-Augmented Generation).

ChromaDB runs locally — no API calls, no cost, no credentials needed.
Uses sentence-transformers for embedding generation (all-MiniLM-L6-v2, 384-dim).

Collections:
  - telecom_knowledge_base : embedded incident descriptions + resolution patterns
  - outage_patterns        : known outage signatures for clustering
"""

import logging
from typing import Any, Dict, List, Optional

from core.config import get_settings

logger = logging.getLogger(__name__)

# Lazy-loaded ChromaDB client (avoids import cost if not used)
_chroma_client: Optional[Any] = None
_embedding_fn: Optional[Any] = None


def _get_chroma_client() -> Any:
    """Lazy-initialise and return the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        import chromadb
        settings = get_settings()
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        logger.info("ChromaDB client initialised at %s", settings.chroma_persist_dir)
    return _chroma_client


def _get_embedding_fn() -> Any:
    """Lazy-initialise the sentence-transformers embedding function."""
    global _embedding_fn
    if _embedding_fn is None:
        from chromadb.utils import embedding_functions
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        logger.info("Embedding function loaded: all-MiniLM-L6-v2 (384-dim)")
    return _embedding_fn


class VectorStore:
    """
    Manages ChromaDB collections for telecom knowledge base RAG.

    Usage:
        store = VectorStore()
        store.ingest(documents, ids, metadatas, collection_name)
        results = store.query("fiber cut in sector 4", k=3)
    """

    def __init__(self, collection_name: Optional[str] = None) -> None:
        settings = get_settings()
        self._collection_name = collection_name or settings.chroma_collection_kb
        self._collection: Optional[Any] = None

    def _get_collection(self) -> Any:
        """Return (or create) the ChromaDB collection."""
        if self._collection is None:
            client = _get_chroma_client()
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=_get_embedding_fn(),
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def ingest(
        self,
        documents: List[str],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        Ingest documents into the vector store.

        Existing IDs are skipped (upsert behaviour).

        Args:
            documents:  List of plain-text strings to embed and store.
            ids:        Unique string ID per document.
            metadatas:  Optional metadata dicts (same length as documents).

        Returns:
            Number of documents ingested.
        """
        collection = self._get_collection()
        metas = metadatas or [{} for _ in documents]
        collection.upsert(documents=documents, ids=ids, metadatas=metas)
        logger.info(
            "VectorStore.ingest: collection=%s count=%d",
            self._collection_name,
            len(documents),
        )
        return len(documents)

    def query(self, query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Find the top-k most semantically similar documents.

        Args:
            query_text: Natural language query string.
            k:          Number of results to return.

        Returns:
            List of dicts with keys: id, document, metadata, distance.
            Sorted by ascending distance (most similar first).
        """
        collection = self._get_collection()
        results = collection.query(
            query_texts=[query_text],
            n_results=min(k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        output = []
        if results and results.get("ids"):
            for idx, doc_id in enumerate(results["ids"][0]):
                output.append(
                    {
                        "id": doc_id,
                        "document": results["documents"][0][idx],
                        "metadata": results["metadatas"][0][idx],
                        "distance": results["distances"][0][idx],
                    }
                )
        return output

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self._get_collection().count()

    def delete_collection(self) -> None:
        """Drop the entire collection (test cleanup only)."""
        client = _get_chroma_client()
        client.delete_collection(self._collection_name)
        self._collection = None
        logger.warning("VectorStore: collection %s deleted", self._collection_name)
