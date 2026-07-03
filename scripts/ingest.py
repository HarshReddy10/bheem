"""CLI script to ingest documents into the vector store.

Usage:
    python scripts/ingest.py                  # Ingest from default directory
    python scripts/ingest.py /path/to/docs    # Ingest from custom directory
"""

import sys
from pathlib import Path

# Add project root to path so we can import the app package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.rag import rag_service
from app.utils.logger import logger


def main() -> None:
    """Ingest documents from the knowledge base into ChromaDB."""
    directory = sys.argv[1] if len(sys.argv) > 1 else settings.knowledge_base_dir

    print(f"\n📂  Knowledge base directory: {directory}")
    print(f"💾  ChromaDB persist path:     {settings.chroma_persist_dir}")
    print(f"📐  Chunk size / overlap:      {settings.rag_chunk_size} / {settings.rag_chunk_overlap}")
    print()

    # Initialize
    logger.info("Initializing RAG service...")
    rag_service.initialize()

    if not rag_service.is_initialized:
        print("❌  Failed to initialize RAG service. Check logs for details.")
        sys.exit(1)

    print(f"📊  Documents already in store: {rag_service.document_count}")

    # Ingest
    print("\n🔄  Ingesting documents...\n")
    chunks = rag_service.ingest_documents(directory)

    print(f"\n✅  Done! Ingested {chunks} chunks.")
    print(f"📊  Total documents in store:  {rag_service.document_count}")


if __name__ == "__main__":
    main()
