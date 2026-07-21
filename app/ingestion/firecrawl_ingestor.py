"""Firecrawl implementation of the ContentIngestor."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict
from urllib.parse import urlparse

from firecrawl import FirecrawlApp
from firecrawl.types import ScrapeOptions

from app.ingestion.base import ContentIngestor
from app.ingestion.models import RawDocument

logger = logging.getLogger(__name__)


class FirecrawlIngestor(ContentIngestor):
    """Ingests websites using the Firecrawl API."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("FIRECRAWL_API_KEY is required to initialize FirecrawlIngestor.")
        self.app = FirecrawlApp(api_key=api_key)

    async def extract(
        self, source: str, config: Dict[str, Any]
    ) -> AsyncGenerator[RawDocument, None]:
        """
        Crawls the source URL using Firecrawl and yields raw markdown documents.
        """
        logger.info(f"Starting Firecrawl extraction for: {source}")
        
        limit = config.get("limit", 50)
        max_depth = config.get("max_depth", 2)
        includes = config.get("includes", [])
        excludes = config.get("excludes", [])
        
        start_time = datetime.utcnow()
        
        try:
            logger.info(f"Triggering crawl for {source} (limit={limit}, max_depth={max_depth})")
            
            crawl_kwargs = {
                "url": source,
                "limit": limit,
                "scrape_options": ScrapeOptions(formats=['markdown']),
            }
            if max_depth:
                crawl_kwargs["max_discovery_depth"] = max_depth
            if includes:
                crawl_kwargs["include_paths"] = includes
            if excludes:
                crawl_kwargs["exclude_paths"] = excludes
                
            crawl_job = self.app.crawl(**crawl_kwargs)
            
        except Exception as e:
            logger.error(f"Firecrawl crawl failed: {e}")
            raise

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Firecrawl job completed in {duration:.2f}s")
        
        if hasattr(crawl_job, "data") and crawl_job.data:
            for doc in crawl_job.data:
                if not doc.markdown:
                    continue
                
                url = doc.metadata.source_url if doc.metadata and doc.metadata.source_url else source
                title = doc.metadata.title if doc.metadata and doc.metadata.title else ""
                
                # Yield the raw document for the quality pipeline
                yield RawDocument(
                    source_url=url,
                    markdown=doc.markdown,
                    metadata={
                        "title": title,
                        "firecrawl_job_id": getattr(crawl_job, "id", "sync_job")
                    },
                    extracted_at=end_time
                )
