"""Document Quality and Normalization Pipeline."""

import hashlib
import logging
import re
from typing import Any, AsyncGenerator, Dict, Set
from urllib.parse import urlparse, urlunparse

from app.ingestion.models import CleanDocument, RawDocument

logger = logging.getLogger(__name__)


class DocumentQualityPipeline:
    """A pipeline that processes raw documents into cleaned, scored, deduplicated documents."""

    def __init__(self):
        self.seen_hashes: Set[str] = set()
        self.stats = {
            "total_processed": 0,
            "duplicates_removed": 0,
            "low_quality_pages": 0,
            "empty_pages": 0,
            "failed_pages": 0,
            "avg_quality_score": 0.0,
        }
        self._total_score = 0

    def _canonicalize_url(self, url: str) -> str:
        """Stage 1: Normalize incoming URLs."""
        if not url or url == "unknown":
            return url
            
        parsed = urlparse(url)
        path = parsed.path
        
        # Remove trailing slash
        if path.endswith('/') and len(path) > 1:
            path = path[:-1]
            
        # Strip index.php or index.html from the end of the path
        if path.endswith('/index.php'):
            path = path[:-10]
        elif path.endswith('/index.html'):
            path = path[:-11]
            
        if not path:
            path = '/'
            
        # Reconstruct URL without fragments
        canonical = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ''))
        return canonical

    def _clean_markdown(self, markdown: str) -> str:
        """Stage 2: Deterministic markdown cleaning."""
        if not markdown:
            return ""
            
        # Remove empty links e.g., []() or [](https://...)
        cleaned = re.sub(r'\[\s*\]\([^\)]*\)', '', markdown)
        
        # Fix excessive newlines (more than 2 to just 2)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Extension point: LLMCleaner could be injected here in the future
        
        return cleaned.strip()

    def _hash_content(self, text: str) -> str:
        """Stage 3 helper: Hash content for deduplication."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def _calculate_quality_score(self, markdown: str, title: str, is_duplicate: bool) -> int:
        """Stage 4: Assign a quality score (0-100)."""
        if is_duplicate:
            return 0
            
        score = 100
        length = len(markdown)
        
        if length == 0:
            return 0
            
        # Penalty for very short documents
        if length < 50:
            score -= 50
        elif length < 200:
            score -= 20
            
        # Penalty for lack of title
        if not title or title.lower() == "untitled":
            score -= 10
            
        return max(0, min(100, score))

    async def process(
        self, raw_stream: AsyncGenerator[RawDocument, None]
    ) -> AsyncGenerator[CleanDocument, None]:
        """Process a stream of raw documents."""
        
        async for raw_doc in raw_stream:
            self.stats["total_processed"] += 1
            
            canonical_url = self._canonicalize_url(raw_doc.source_url)
            cleaned_md = self._clean_markdown(raw_doc.markdown)
            
            if not cleaned_md:
                self.stats["empty_pages"] += 1
                continue
                
            content_hash = self._hash_content(cleaned_md)
            
            # Stage 3: Duplicate Detection
            is_duplicate = content_hash in self.seen_hashes
            if is_duplicate:
                self.stats["duplicates_removed"] += 1
            else:
                self.seen_hashes.add(content_hash)
                
            # Title extraction
            title = raw_doc.metadata.get("title", "")
            
            # Stage 4: Quality Scoring
            score = self._calculate_quality_score(cleaned_md, title, is_duplicate)
            
            if score < 50 and not is_duplicate:
                self.stats["low_quality_pages"] += 1
                
            if not is_duplicate:
                self._total_score += score
                
            clean_doc = CleanDocument(
                canonical_url=canonical_url,
                markdown=cleaned_md,
                title=title,
                content_hash=content_hash,
                quality_score=score,
                is_duplicate=is_duplicate,
                metadata=raw_doc.metadata,
                processed_at=raw_doc.extracted_at,
            )
            
            yield clean_doc

    def get_report(self) -> Dict[str, Any]:
        """Stage 5: Generate the final quality report."""
        non_dupes = self.stats["total_processed"] - self.stats["duplicates_removed"] - self.stats["empty_pages"]
        
        if non_dupes > 0:
            self.stats["avg_quality_score"] = round(self._total_score / non_dupes, 2)
            
        return self.stats
