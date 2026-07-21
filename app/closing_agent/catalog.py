"""Course catalogue for the Closing Agent.

Loads purchasable courses from company configuration (config/company.yaml)
instead of hardcoding them. Provides fuzzy matching against course names
and aliases for intent detection.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Course:
    """A purchasable course in the catalogue."""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    price: int = 0          # in smallest currency unit (paise for INR)
    currency: str = "INR"
    duration: str = ""
    short_description: str = ""
    is_available: bool = True

    @property
    def price_display(self) -> str:
        """Human-readable price string."""
        if self.currency == "INR":
            return f"₹{self.price / 100:,.0f}"
        return f"{self.price / 100:,.2f} {self.currency}"

    def to_summary(self) -> str:
        """One-line summary for WhatsApp messages."""
        return (
            f"*{self.name}*\n\n"
            f"💰 Price: {self.price_display}\n"
            f"⏱️ Duration: {self.duration}\n\n"
            f"{self.short_description}"
        )


def _load_courses_from_config() -> List[Course]:
    """Load courses from company configuration."""
    from app.company_config import company_config

    raw_courses = company_config._data.get("courses", [])
    courses = []
    for c in raw_courses:
        courses.append(Course(
            id=c.get("id", ""),
            name=c.get("name", ""),
            aliases=c.get("aliases", []),
            price=c.get("price_paise", 0),
            currency=c.get("currency", "INR"),
            duration=c.get("duration", ""),
            short_description=c.get("short_description", ""),
            is_available=c.get("is_available", True),
        ))
    return courses


def get_courses() -> List[Course]:
    """Retrieve all available courses."""
    return [c for c in _load_courses_from_config() if c.is_available]


def get_course_by_id(course_id: str) -> Optional[Course]:
    """Retrieve a specific course by its ID."""
    for course in _load_courses_from_config():
        if course.id == course_id:
            return course
    return None


def match_course(user_text: str) -> Optional[Course]:
    """Match user text against course names and aliases.

    Uses case-insensitive substring matching. Returns the first match.
    Checks aliases first (more specific), then course names.
    """
    text_lower = user_text.lower().strip()
    if not text_lower:
        return None

    courses = get_courses()

    # Pass 1: exact alias match
    for course in courses:
        for alias in course.aliases:
            if alias.lower() == text_lower:
                return course

    # Pass 2: alias contained in text
    for course in courses:
        for alias in course.aliases:
            if alias.lower() in text_lower:
                return course

    # Pass 3: course name contained in text
    for course in courses:
        if course.name.lower() in text_lower:
            return course

    return None
