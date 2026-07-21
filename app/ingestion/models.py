"""Data models for the Document Quality Pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RawDocument:
    """A raw document extracted by an ingestor before quality processing."""
    
    source_url: str
    markdown: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    extracted_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CleanDocument:
    """A processed document that has passed through the quality pipeline."""
    
    canonical_url: str
    markdown: str
    title: str
    content_hash: str
    quality_score: int
    is_duplicate: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    processed_at: datetime = field(default_factory=datetime.utcnow)
