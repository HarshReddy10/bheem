"""LLM-based extraction logic for lead intelligence."""

import json
import logging
import re
from datetime import datetime
from typing import Dict, Optional

from app.lead_intelligence.models import FieldProvenance, LeadField
from app.lead_intelligence.confidence import determine_status

logger = logging.getLogger(__name__)

async def extract_lead_info(
    llm,
    conversation_text: str,
    missing_fields: Dict[str, str],
    conversation_id: int
) -> Dict[str, LeadField]:
    """Use the LLM to extract lead qualification data from conversation context.

    Returns a dict of {field_name: LeadField}.
    """
    from app.company_config import company_config
    
    if not missing_fields:
        return {}

    # Skip trivially short context
    stripped = conversation_text.strip()
    if len(stripped) < 10 or len(stripped.split()) < 3:
        return {}

    field_descriptions = "\n".join(
        f"- {k}: {desc}" for k, desc in missing_fields.items()
    )

    # We will override the default prompt from company_config or use a new one
    # that asks for confidence scores. Since we want to remain compatible, we can append instructions.
    
    base_prompt = company_config.render_lead_extraction_prompt(
        field_descriptions=field_descriptions,
        user_message=conversation_text,
    )
    
    enhanced_prompt = (
        f"{base_prompt}\n\n"
        "CRITICAL INSTRUCTION: For each field you extract, provide a JSON object with 'value' and 'confidence'.\n"
        "The 'confidence' should be a float between 0.0 and 1.0 (e.g., 0.95 for high confidence, 0.5 for a guess).\n"
        "Example output format:\n"
        "{\n"
        '  "education": {"value": "B.Tech Computer Science", "confidence": 0.95},\n'
        '  "budget": {"value": "$500", "confidence": 0.6}\n'
        "}"
    )

    try:
        response = await llm.generate(
            messages=[{"role": "user", "content": enhanced_prompt}],
            system_prompt=(
                "You are an AI data extraction assistant analyzing a conversation.\n"
                "Extract structured information and confidence scores. Return ONLY valid JSON."
            ),
            temperature=0.1,
            max_tokens=300,
        )

        response_clean = response.strip()
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_clean, re.DOTALL)
        if match:
            response_clean = match.group(1).strip()

        extracted = json.loads(response_clean)
        
        if not isinstance(extracted, dict):
            return {}

        valid_fields: Dict[str, LeadField] = {}
        extracted_at = datetime.utcnow()
        model_name = getattr(llm, "model", "unknown_model") # try to get model name

        for key, data in extracted.items():
            if key not in missing_fields:
                continue
                
            # Backward compat: if the LLM just returned a string instead of dict
            if isinstance(data, str) and data.strip():
                value = data.strip()
                confidence = 0.8  # Default assumed confidence
            elif isinstance(data, dict):
                value = data.get("value")
                confidence = float(data.get("confidence", 0.8))
                if not value or not isinstance(value, str) or not value.strip():
                    continue
            else:
                continue

            status = determine_status(confidence)
            
            provenance = FieldProvenance(
                model=model_name,
                conversation_id=conversation_id,
                extracted_at=extracted_at,
                method="llm_extraction"
            )
            
            valid_fields[key] = LeadField(
                value=value.strip(),
                status=status,
                confidence=confidence,
                provenance=provenance
            )

        if valid_fields:
            logger.info(f"Extracted lead info: {list(valid_fields.keys())}")
            
        return valid_fields

    except json.JSONDecodeError:
        logger.warning(f"Failed to parse extraction response as JSON: {response[:100]}")
        return {}
    except Exception as e:
        logger.error(f"Lead extraction failed: {e}")
        return {}
