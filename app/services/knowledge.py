"""Knowledge Service for managing ingestion and indexing commands."""

import json
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any

from app.company_config import company_config
from app.config import settings

logger = logging.getLogger(__name__)

class KnowledgeService:
    """Service handling commands for the Knowledge Repository."""

    async def trigger_ingestion(self, source_type: str, url: str) -> Dict[str, Any]:
        """Trigger content ingestion (e.g., website crawling)."""
        base_repo_dir = Path(company_config.knowledge_repository_directory)
        
        if source_type != "website":
            raise ValueError(f"Unsupported ingestion type: {source_type}")

        ingestion_config = company_config._data.get("knowledge_repository", {}).get("ingestion", {})
        fc_config = ingestion_config.get("firecrawl", {})
        
        output_dir = base_repo_dir / "websites"
        
        from app.ingestion.firecrawl_ingestor import FirecrawlIngestor
        from app.ingestion.pipeline import DocumentQualityPipeline
        
        ingestor = FirecrawlIngestor(api_key=settings.firecrawl_api_key)
        pipeline = DocumentQualityPipeline()
        
        # 1. Get raw stream
        raw_stream = ingestor.extract(source=url, config=fc_config)
        
        # 2. Process through pipeline
        clean_stream = pipeline.process(raw_stream)
        
        # 3. Save to disk
        domain = urlparse(url).netloc or urlparse(url).path
        domain_dir = output_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        
        saved_count = 0
        
        async for doc in clean_stream:
            if doc.is_duplicate:
                continue
                
            parsed_doc_url = urlparse(doc.canonical_url)
            safe_path = parsed_doc_url.path.strip("/").replace("/", "_")
            if not safe_path:
                safe_path = "index"
            filename = f"{safe_path}.md"
            
            file_path = domain_dir / filename
            
            frontmatter = (
                "---\n"
                f"title: {doc.title}\n"
                f"source_url: {doc.canonical_url}\n"
                f"crawled_at: {doc.processed_at.isoformat()}\n"
                f"quality_score: {doc.quality_score}\n"
                f"content_hash: {doc.content_hash}\n"
                "---\n\n"
            )
            
            file_path.write_text(frontmatter + doc.markdown, encoding="utf-8")
            saved_count += 1
            
        report = pipeline.get_report()
        report["source_url"] = url
        report["saved_pages"] = saved_count
        
        metadata_file = domain_dir / "crawl_metadata.json"
        metadata_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        
        # Publish event
        from app.services.events import event_bus, DomainEvent
        event_bus.publish(DomainEvent(
            event_type="KnowledgeRepositoryUpdated",
            payload={"source": url, "report": report}
        ))
        
        return report

    async def rebuild_index(self, directory: str = None) -> Dict[str, Any]:
        """Trigger a rebuild of the RAG vector index."""
        from app.services.rag import rag_service
        from app.config import settings
        
        target_dir = directory or settings.knowledge_base_dir
        
        rag_service.initialize()
        if not rag_service.is_initialized:
            raise RuntimeError("Failed to initialize RAG service")
            
        chunks = rag_service.ingest_documents(target_dir)
        
        payload = {
            "status": "rebuilt", 
            "directory": target_dir,
            "chunks_ingested": chunks,
            "document_count": rag_service.document_count
        }
        
        # Publish event
        from app.services.events import event_bus, DomainEvent
        event_bus.publish(DomainEvent(
            event_type="KnowledgeRepositoryUpdated",
            payload={"action": "rebuild", "stats": payload}
        ))
        
        return payload

# Singleton instance
knowledge_service = KnowledgeService()
