"""Data models for Lead Intelligence."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FieldProvenance(BaseModel):
    """Metadata about where and how a field was extracted."""
    model: str
    conversation_id: int
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    method: str = "llm_extraction"


class LeadField(BaseModel):
    """A single piece of lead information with confidence and provenance."""
    value: Optional[str] = None
    status: str = "unknown"  # unknown, partially_known, confirmed
    confidence: float = 0.0
    provenance: Optional[FieldProvenance] = None
