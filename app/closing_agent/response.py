"""Provider-independent structured response for the Closing Agent.

The message processor returns a BotResponse; the WhatsApp client's
UI renderer converts it into the correct Meta Cloud API payload.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BotResponse:
    """Structured bot response — provider-independent.

    Attributes:
        message:     Text body of the reply.
        state:       The closing-session state after this response.
        interactive: Optional dict describing buttons or list UI.
                     Example for buttons:
                       {"type": "buttons", "buttons": [
                           {"id": "proceed_to_payment", "title": "Proceed to Payment"},
                           {"id": "ask_question", "title": "Ask a Question"},
                       ]}
                     Example for list:
                       {"type": "list", "button_label": "View Courses", "sections": [
                           {"title": "Available Courses", "rows": [
                               {"id": "course_data_science", "title": "Data Science",
                                "description": "6 months • ₹40,000"},
                           ]}
                       ]}
    """
    message: str
    state: str
    interactive: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for API responses (e.g. /api/test-chat)."""
        result = {"message": self.message, "state": self.state}
        if self.interactive:
            result["interactive"] = self.interactive
        return result


# ── Button Presets ─────────────────────────────────────────────────────────


def greeting_buttons() -> Dict[str, Any]:
    """Interactive buttons for the initial greeting."""
    return {
        "type": "buttons",
        "buttons": [
            {"id": "view_courses", "title": "View Courses"},
            {"id": "ask_question", "title": "Ask a Question"},
            {"id": "talk_to_advisor", "title": "Talk to an Advisor"},
        ],
    }


def course_selected_buttons() -> Dict[str, Any]:
    """Interactive buttons after a course is selected."""
    return {
        "type": "buttons",
        "buttons": [
            {"id": "proceed_to_payment", "title": "Proceed to Payment"},
            {"id": "ask_question", "title": "Ask a Question"},
            {"id": "other_courses", "title": "View Other Courses"},
        ],
    }


def after_rag_buttons() -> Dict[str, Any]:
    """Interactive buttons after answering a RAG question."""
    return {
        "type": "buttons",
        "buttons": [
            {"id": "proceed_to_payment", "title": "Proceed to Payment"},
            {"id": "ask_question", "title": "Ask Another Question"},
            {"id": "not_now", "title": "Not Now"},
        ],
    }


def after_payment_buttons() -> Dict[str, Any]:
    """Interactive buttons after successful payment."""
    return {
        "type": "buttons",
        "buttons": [
            {"id": "view_receipt", "title": "View Receipt"},
            {"id": "contact_support", "title": "Contact Support"},
        ],
    }


def course_list(courses: list) -> Dict[str, Any]:
    """Interactive list for course browsing."""
    rows = []
    for c in courses:
        rows.append({
            "id": c.id,
            "title": c.name[:24],  # WhatsApp limit
            "description": f"{c.duration} • {c.price_display}"[:72],
        })
    return {
        "type": "list",
        "button_label": "View Courses",
        "sections": [
            {"title": "Available Courses", "rows": rows},
        ],
    }
