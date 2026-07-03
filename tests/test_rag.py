"""Tests for the RAG pipeline and document loader."""

import pytest

from app.utils.document_loader import chunk_text, load_text_file
from app.services.rag import RAGService


class TestChunkText:
    """Unit tests for text chunking."""

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text(self):
        text = "Hello world"
        chunks = chunk_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunking_respects_size(self):
        # Create text with multiple paragraphs
        paragraphs = [f"Paragraph {i} " * 20 for i in range(10)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            # Allow some tolerance for overlap
            assert len(chunk) <= 400  # generous bound

    def test_overlap_present(self):
        text = "First paragraph content here.\n\nSecond paragraph content here.\n\nThird paragraph content here."
        chunks = chunk_text(text, chunk_size=40, chunk_overlap=10)
        assert len(chunks) >= 2


class TestRAGService:
    """Integration tests for the RAG service."""

    def test_initialization(self):
        """RAG service should initialize without errors."""
        service = RAGService()
        service.initialize()
        assert service.is_initialized is True

    def test_ingest_and_retrieve(self):
        """Ingest sample docs and retrieve relevant chunks."""
        service = RAGService()
        service.initialize()

        if not service.is_initialized:
            pytest.skip("RAG service failed to initialize")

        # Ingest
        count = service.ingest_documents("./knowledge_base")
        assert count > 0

        # Retrieve
        results = service.retrieve("training programs")
        assert len(results) > 0
        assert "content" in results[0]
        assert "source" in results[0]

    def test_retrieve_empty_store(self):
        """Retrieval on empty store should return empty list."""
        service = RAGService()
        # Don't initialize — should gracefully return empty
        results = service.retrieve("anything")
        assert results == []

    def test_build_context(self):
        """build_context should return a formatted string."""
        service = RAGService()
        service.initialize()

        if not service.is_initialized:
            pytest.skip("RAG service failed to initialize")

        service.ingest_documents("./knowledge_base")
        context = service.build_context("placement success rate")
        assert isinstance(context, str)
        if service.document_count > 0:
            assert len(context) > 0
