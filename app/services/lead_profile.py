"""Lead profile management for the Lead Intelligence Agent.

Provides:
- ``LeadProfile`` class with dynamic fields loaded from company config
- Serialization/deserialization to/from JSON (stored on User.lead_profile)
- LLM-based extraction of lead info from user messages
- Merge logic that never overwrites existing values
- System-prompt section builder for natural follow-up questioning
"""

import json
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import logger


# ── Dynamic Lead Profile ─────────────────────────────────────────────────


class LeadProfile:
    """Dynamic lead qualification profile.

    Fields are defined by company configuration, not hardcoded.
    All fields default to ``None`` — they are populated incrementally
    as the user reveals information during conversation.

    Supports both attribute-style (``profile.education``) and dict-style
    (``profile["education"]``) access for backward compatibility.
    """

    def __init__(
        self,
        field_names: Optional[List[str]] = None,
        field_descriptions: Optional[Dict[str, str]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        from app.lead_intelligence.models import LeadField
        
        self._field_names = field_names or _get_field_names()
        self._field_descriptions = field_descriptions or _get_field_descriptions()
        self._data: Dict[str, Optional[LeadField]] = {}

        # Initialize all fields to None
        for name in self._field_names:
            self._data[name] = None

        # Override with provided data
        if data:
            for key, value in data.items():
                if key not in self._data:
                    continue
                if value is None:
                    continue
                
                # Backward compatibility: if it's a raw string from the old system
                if isinstance(value, str):
                    self._data[key] = LeadField(value=value, status="confirmed", confidence=1.0)
                elif isinstance(value, dict):
                    self._data[key] = LeadField(**value)
                elif isinstance(value, LeadField):
                    self._data[key] = value

    # ── Dict-style access ─────────────────────────────────────────────

    def __getitem__(self, key: str) -> Optional[str]:
        field = self._data.get(key)
        return field.value if field else None

    def __setitem__(self, key: str, value: Optional[str]) -> None:
        """Backward compatibility setter. Creates a confirmed field."""
        from app.lead_intelligence.models import LeadField
        
        if key in self._data:
            if value is None:
                self._data[key] = None
            else:
                self._data[key] = LeadField(value=value, status="confirmed", confidence=1.0)

    def get_field(self, key: str) -> Optional[Any]: # Any to avoid circular import if needed
        """Get the rich LeadField object instead of just the value."""
        return self._data.get(key)

    def set_field(self, key: str, field: Any) -> None:
        if key in self._data:
            self._data[key] = field

    # ── Attribute-style access (backward compat) ──────────────────────

    def __getattr__(self, name: str) -> Optional[str]:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._data:
            field = self._data[name]
            return field.value if field else None
        raise AttributeError(f"'{type(self).__name__}' has no field '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        elif hasattr(self, "_data") and name in self._data:
            self.__setitem__(name, value)
        else:
            super().__setattr__(name, value)

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict (for JSON storage)."""
        return {
            k: (v.model_dump() if v else None) 
            for k, v in self._data.items()
        }

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        field_names: Optional[List[str]] = None,
        field_descriptions: Optional[Dict[str, str]] = None,
    ) -> "LeadProfile":
        """Deserialize from a dict, ignoring unknown keys."""
        return cls(
            field_names=field_names,
            field_descriptions=field_descriptions,
            data=data,
        )

    # ── Profile status ────────────────────────────────────────────────

    @property
    def missing_fields(self) -> Dict[str, str]:
        """Return field names and descriptions for fields still None."""
        return {
            name: self._field_descriptions.get(name, "")
            for name in self._field_names
            if self._data.get(name) is None
        }

    @property
    def known_fields(self) -> Dict[str, str]:
        """Return field names and their collected values."""
        return {
            name: self._data[name]
            for name in self._field_names
            if self._data.get(name) is not None
        }

    @property
    def is_complete(self) -> bool:
        """True when every profile field has a value."""
        return len(self.missing_fields) == 0


# ── Field Access Helpers ─────────────────────────────────────────────────
# These lazily access company_config to avoid circular imports at module load.


def _get_field_names() -> List[str]:
    """Get lead field names from company config."""
    from app.company_config import company_config

    return company_config.lead_field_names


def _get_field_descriptions() -> Dict[str, str]:
    """Get lead field descriptions from company config."""
    from app.company_config import company_config

    return company_config.lead_field_descriptions


# ── Persistence Helpers ──────────────────────────────────────────────────


def load_profile(user) -> LeadProfile:
    """Deserialize the lead profile from a User ORM object.

    Returns an empty LeadProfile if the user has no profile data yet.
    """
    if user.lead_profile:
        try:
            data = json.loads(user.lead_profile)
            return LeadProfile.from_dict(data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"Corrupt lead_profile JSON for user {user.id}, resetting."
            )
    return LeadProfile()


async def save_profile(
    session: AsyncSession, user, profile: LeadProfile
) -> None:
    """Serialize and persist the lead profile on the User record."""
    from datetime import datetime

    user.lead_profile = json.dumps(profile.to_dict())
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    logger.info(f"Updated lead profile for user {user.id}")


# ── System Prompt Section ────────────────────────────────────────────────


def build_profile_prompt_section(
    profile: LeadProfile, user_name: str = "this person"
) -> str:
    """Build the Conversation Memory section for the system prompt.

    Uses a 'what you know' framing instead of a 'what's missing' checklist.
    This shifts the LLM's mindset from form-filling to understanding.
    """
    known = profile.known_fields

    if not known:
        # Nothing known yet — keep it light
        return (
            "CONVERSATION MEMORY:\n"
            f"You don't know much about {user_name} yet — and that's fine.\n"
            "Focus on being helpful. You'll learn about them naturally as "
            "the conversation unfolds."
        )

    # Format known fields
    known_lines = "\n".join(
        f"  - {k.replace('_', ' ').title()}: {v}"
        for k, v in known.items()
    )

    if profile.is_complete:
        return (
            "CONVERSATION MEMORY:\n"
            f"Here is what you know about {user_name}:\n"
            f"{known_lines}\n\n"
            f"You have a thorough understanding of {user_name}. Use this knowledge to "
            "personalise every response — recommend specific options, reference their "
            "background, and help them take their next step."
        )

    # Partial profile — show what's known, no checklist of what's missing
    return (
        "CONVERSATION MEMORY:\n"
        f"Here is what you currently know about {user_name}:\n"
        f"{known_lines}\n\n"
        "If additional information naturally becomes available during conversation, "
        "remember it. \n"
        "IMPORTANT RULES FOR LEAD QUALIFICATION:\n"
        "1. You MUST answer the user's question first.\n"
        "2. Do NOT interrogate the user.\n"
        "3. If learning something would genuinely help you provide better guidance, you may naturally ask at most ONE follow-up question.\n"
        "4. Avoid repetitive questioning. Otherwise, continue helping normally."
    )
