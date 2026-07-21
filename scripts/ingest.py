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


import asyncio

async def async_main() -> None:
    directory = sys.argv[1] if len(sys.argv) > 1 else settings.knowledge_base_dir
    print(f"\n📂  Knowledge base directory: {directory}")
    print("\n🔄  Rebuilding index...\n")
    
    from app.services.knowledge import knowledge_service
    try:
        report = await knowledge_service.rebuild_index(directory)
        print(f"\n✅  Done! Ingested {report['chunks_ingested']} chunks.")
        print(f"📊  Total documents in store:  {report['document_count']}")
    except Exception as e:
        print(f"❌  Failed: {e}")
        sys.exit(1)

def main() -> None:
    """Ingest documents from the knowledge base into ChromaDB."""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
