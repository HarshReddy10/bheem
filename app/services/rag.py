"""RAG (Retrieval-Augmented Generation) pipeline.

Uses ChromaDB (embedded/persistent) as the vector store.
ChromaDB's default embedding function handles embeddings internally,
so no separate sentence-transformers import is needed at query time.
"""

from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.company_config import company_config
from app.utils.document_loader import chunk_text, load_all_documents
from app.utils.logger import logger


class RAGService:
    """Retrieval-Augmented Generation service.

    Lifecycle:
    1. ``initialize()`` — connect to ChromaDB, create/load collection
    2. ``ingest_documents()`` — parse files → chunk → upsert into vector store
    3. ``retrieve()`` / ``build_context()`` — find relevant chunks for a query
    """

    def __init__(self) -> None:
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection = None
        self._initialized = False

    # ── Initialization ────────────────────────────────────────────────

    def initialize(self) -> None:
        """Connect to ChromaDB and create/load the knowledge base collection."""
        try:
            persist_dir = Path(settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )

            self._collection = self._client.get_or_create_collection(
                name="knowledge_base",
                metadata={"hnsw:space": "cosine"},
            )

            self._initialized = True
            doc_count = self._collection.count()
            logger.info(
                f"RAG service initialized. Documents in store: {doc_count}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize RAG service: {e}")
            self._initialized = False

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def document_count(self) -> int:
        if self._collection is None:
            return 0
        return self._collection.count()

    # ── Document Ingestion ────────────────────────────────────────────

    def ingest_documents(self, directory: Optional[str] = None) -> int:
        """Parse all documents in *directory*, chunk them, and upsert.

        Returns the total number of chunks ingested.
        """
        if not self._initialized:
            logger.error("RAG service not initialized")
            return 0

        doc_dir = directory or company_config.knowledge_repository_directory or settings.knowledge_repository_dir
        documents = load_all_documents(doc_dir)

        if not documents:
            logger.warning("No documents found to ingest")
            return 0

        total_chunks = 0
        for doc in documents:
            chunks = chunk_text(
                doc["content"],
                chunk_size=settings.rag_chunk_size,
                chunk_overlap=settings.rag_chunk_overlap,
            )
            if not chunks:
                continue

            ids = [f"{doc['filename']}_{i}" for i in range(len(chunks))]
            metadatas = [
                {"source": doc["filename"], "chunk_index": i}
                for i in range(len(chunks))
            ]

            # Upsert so re-ingestion is idempotent
            self._collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas,
            )
            total_chunks += len(chunks)
            logger.info(f"Ingested {len(chunks)} chunks from {doc['filename']}")

        logger.info(f"Total chunks ingested: {total_chunks}")
        return total_chunks

    # ── Retrieval ─────────────────────────────────────────────────────

    def retrieve(
        self, query: str, top_k: Optional[int] = None
    ) -> List[dict]:
        """Return the top-k most relevant chunks for *query*.

        Each result dict contains: content, source, relevance_score.
        """
        if not self._initialized or self._collection is None:
            logger.warning("RAG service not initialized — returning empty")
            return []

        if self._collection.count() == 0:
            logger.warning("Knowledge base is empty — nothing to search")
            return []

        k = top_k or settings.rag_top_k

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(k, self._collection.count()),
            )

            retrieved: List[dict] = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    metadata = (
                        results["metadatas"][0][i] if results["metadatas"] else {}
                    )
                    distance = (
                        results["distances"][0][i] if results["distances"] else 0.0
                    )
                    retrieved.append(
                        {
                            "content": doc,
                            "source": metadata.get("source", "unknown"),
                            "relevance_score": round(1 - distance, 4),
                        }
                    )

            logger.info(
                f"Retrieved {len(retrieved)} chunks for: '{query[:50]}...'"
            )
            return retrieved
        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []

    def build_context(
        self, query: str, top_k: Optional[int] = None
    ) -> str:
        """Build a single context string from the retrieved chunks.

        Suitable for injecting directly into an LLM system prompt.
        """
        chunks = self.retrieve(query, top_k)
        if not chunks:
            return ""

        parts = [
            f"[Source: {c['source']}]\n{c['content']}" for c in chunks
        ]
        return "\n\n---\n\n".join(parts)


# Singleton instance
rag_service = RAGService()
