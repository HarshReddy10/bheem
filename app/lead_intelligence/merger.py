"""Logic for merging newly extracted lead fields into the existing profile."""

import logging
from typing import Dict, Optional

from app.lead_intelligence.models import LeadField

logger = logging.getLogger(__name__)

def merge_field(existing: Optional[LeadField], new_field: LeadField) -> LeadField:
    """Merge a newly extracted LeadField into an existing one.
    
    Rules:
    - If no existing field, accept the new one.
    - If existing is 'confirmed', never overwrite it with a lower-confidence or 'partially_known' guess.
    - If existing is 'confirmed' and new is 'confirmed', we can update the value if confidence is strictly higher,
      though generally we prefer to keep the original confirmed value. Let's only update if new confidence > existing confidence.
    - If existing is 'partially_known' or 'unknown', overwrite if new confidence > existing confidence.
    """
    if existing is None or existing.status == "unknown":
        return new_field
        
    if existing.status == "confirmed":
        if new_field.status == "confirmed" and new_field.confidence > existing.confidence:
            return new_field
        return existing
        
    # existing is partially_known
    if new_field.confidence > existing.confidence or new_field.status == "confirmed":
        return new_field
        
    return existing

def merge_extracted_fields(
    existing_profile_data: Dict[str, LeadField],
    extracted: Dict[str, LeadField]
) -> Dict[str, LeadField]:
    """Merge newly extracted fields into the existing profile data dict."""
    for key, new_field in extracted.items():
        if not new_field.value or not isinstance(new_field.value, str):
            continue
            
        existing_field = existing_profile_data.get(key)
        merged = merge_field(existing_field, new_field)
        
        # We also want to trim long values
        if merged.value:
            merged.value = merged.value.strip()[:200]
            
        existing_profile_data[key] = merged
        
    return existing_profile_data
