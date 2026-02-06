import logging
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.pdf_processor import TextChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "pdf_documents"


@dataclass
class QueryResult:
    """A single result from a vector store query."""
    text: str
    pdf_name: str
    page_number: int
    chunk_id: int
    score: float


def _get_embedding_function():
    """Select embedding function based on configuration.

    If OPENAI_API_KEY is set, uses OpenAI text-embedding-3-small.
    Otherwise, falls back to sentence-transformers/all-MiniLM-L6-v2.
    """
    if settings.use_openai_embeddings:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        logger.info("Using OpenAI embeddings (text-embedding-3-small)")
        return OpenAIEmbeddingFunction(
            api_key=settings.OPENAI_API_KEY,
            model_name=settings.OPENAI_EMBEDDING_MODEL,
        )
    else:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        logger.info("Using local sentence-transformers embeddings (all-MiniLM-L6-v2)")
        return SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )


class VectorStore:
    """ChromaDB-based vector store for PDF document chunks."""

    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embedding_fn = _get_embedding_function()
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"Vector store initialized. Collection '{COLLECTION_NAME}' "
            f"has {self._collection.count()} documents."
        )

    def add_documents(self, chunks: list[TextChunk]) -> int:
        """Add text chunks to the vector store.

        Args:
            chunks: List of TextChunk objects to add.

        Returns:
            Number of chunks added.
        """
        if not chunks:
            return 0

        ids = [f"{c.pdf_name}_{c.chunk_id}" for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [
            {
                "pdf_name": c.pdf_name,
                "page_number": c.page_number,
                "chunk_id": c.chunk_id,
            }
            for c in chunks
        ]

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Added {len(chunks)} chunks to vector store.")
        return len(chunks)

    def query(self, query_text: str, top_k: int | None = None) -> list[QueryResult]:
        """Query the vector store for similar documents.

        Args:
            query_text: The question or search text.
            top_k: Number of top results to return. Defaults to settings.TOP_K.

        Returns:
            List of QueryResult objects sorted by relevance.
        """
        if top_k is None:
            top_k = settings.TOP_K

        if self._collection.count() == 0:
            logger.warning("Vector store is empty. No results returned.")
            return []

        results = self._collection.query(
            query_texts=[query_text],
            n_results=min(top_k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        query_results: list[QueryResult] = []
        if results and results["documents"]:
            for doc, meta, distance in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                # ChromaDB returns cosine distance; convert to similarity
                similarity = 1 - distance
                query_results.append(
                    QueryResult(
                        text=doc,
                        pdf_name=meta["pdf_name"],
                        page_number=meta["page_number"],
                        chunk_id=meta["chunk_id"],
                        score=similarity,
                    )
                )

        # Sort by score descending
        query_results.sort(key=lambda r: r.score, reverse=True)
        return query_results

    def clear(self) -> None:
        """Delete all documents from the vector store."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector store cleared.")

    @property
    def document_count(self) -> int:
        """Return the number of documents in the vector store."""
        return self._collection.count()
