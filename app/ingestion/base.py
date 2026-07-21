"""Base interface for content ingestors."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict

from app.ingestion.models import RawDocument


class ContentIngestor(ABC):
    """Abstract base class for all content ingestors.
    
    Ingestors are responsible for fetching content from a source
    (e.g., a website, a PDF folder, a Notion workspace), normalizing
    it into clean Markdown, and saving it to the specified output directory.
    
    They do NOT handle embeddings or ChromaDB interactions.
    """
    
    @abstractmethod
    async def extract(
        self, source: str, config: Dict[str, Any]
    ) -> AsyncGenerator[RawDocument, None]:
        """
        Extracts content from the source and yields RawDocument objects.
        
        Args:
            source: The identifier for the source (e.g., a URL or file path).
            config: A dictionary of configuration options specific to the ingestor.
            
        Yields:
            RawDocument objects containing the uncleaned markdown and metadata.
        """
        yield  # type: ignore
