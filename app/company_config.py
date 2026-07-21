"""Company configuration loader for multi-tenant AI Lead Qualification Platform.

Loads company-specific settings (branding, lead fields, prompts) from YAML
config files and Jinja2 templates, making the platform company-agnostic.

Usage:
    from app.company_config import company_config
    company_config.initialize()  # Called once at startup

    name = company_config.company_name
    prompt = company_config.render_system_prompt(context=..., ...)
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.config import settings
from app.utils.logger import logger


# ── Built-in Defaults ────────────────────────────────────────────────────
# Used when config files are missing, so the app always starts.

_DEFAULT_COMPANY: Dict[str, Any] = {
    "company": {
        "name": "AI Lead Qualification Platform",
        "short_name": "",
        "description": "An AI-powered lead qualification chatbot",
        "website": "",
        "contact_email": "",
        "contact_phone": "",
    },
    "branding": {
        "bot_persona": "a friendly, knowledgeable assistant",
        "user_term": "customer",
        "welcome_emoji": "👋",
        "offering_term": "products and services",
        "escalation_message": "I'd recommend reaching out to our team for more details.",
    },
    "menu_items": [
        "Our products & services",
        "Pricing information",
        "General inquiries",
    ],
    "lead_fields": [
        {
            "name": "interest",
            "description": "What product or service they are interested in",
            "example": "Enterprise plan",
        },
        {
            "name": "budget",
            "description": "Their budget or spending expectations",
            "example": "$5,000/month",
        },
        {
            "name": "timeline",
            "description": "When they want to get started",
            "example": "Next quarter",
        },
    ],
    "knowledge_repository": {
        "directory": "./knowledge_repository/default",
        "ingestion": {
            "firecrawl": {
                "max_depth": 2,
                "limit": 50,
                "includes": ["/*"],
                "excludes": ["/admin", "/login"],
            }
        }
    },
}

_DEFAULT_NAME_CAPTURE: Dict[str, str] = {
    "welcome": (
        "Welcome! {{ welcome_emoji }}\n\n"
        "I'm your AI assistant, here to help you.\n\n"
        "Before we begin, may I know your name?"
    ),
    "confirmation": (
        "Nice to meet you, {{ name }}! 😊\n\n"
        "How can I help you today?"
    ),
    "retry": (
        "I'd love to address you by name! "
        "Could you please share just your name?"
    ),
}

# ── Fallback prompt strings (used when template files are missing) ────────

_FALLBACK_SYSTEM_PROMPT = (
    "You are {{ bot_persona }} for {{ company_name }}. "
    "Answer the user's question using the knowledge base context below. "
    "Be helpful and conversational.\n\n"
    "{{ name_instruction }}\n\n"
    "{{ lead_profile_section }}\n\n"
    "KNOWLEDGE BASE CONTEXT:\n{{ context }}"
)

_FALLBACK_QUERY_REWRITE = (
    "Given the conversation history and the latest user message, rewrite "
    "the user message into a standalone search query.\n\n"
    "CONVERSATION HISTORY:\n{{ history_text }}\n\n"
    "LATEST USER MESSAGE:\n{{ user_message }}\n\n"
    "STANDALONE SEARCH QUERY:"
)

_FALLBACK_LEAD_EXTRACTION = (
    "Analyze the user's message and extract lead qualification information.\n\n"
    "FIELDS TO LOOK FOR:\n{{ field_descriptions }}\n\n"
    'USER MESSAGE:\n"{{ user_message }}"\n\n'
    "Return ONLY valid JSON with extracted fields. "
    "If nothing found, return: {}\n\nJSON OUTPUT:"
)


class CompanyConfig:
    """Loads and provides access to company-specific configuration.

    Lifecycle:
        1. ``initialize(config_dir)`` — load YAML + compile Jinja2 templates
        2. Access properties (``company_name``, ``lead_fields``, etc.)
        3. Render prompts (``render_system_prompt()``, etc.)
    """

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._name_capture: Dict[str, str] = {}
        self._jinja_env: Optional[Environment] = None
        self._initialized = False

    # ── Initialization ────────────────────────────────────────────────

    def initialize(self, config_dir: Optional[str] = None) -> None:
        """Load configuration from the specified directory.

        Falls back to built-in defaults if files are missing.
        """
        config_path = Path(config_dir or settings.company_config_dir)

        # Load company.yaml
        company_yaml = config_path / "company.yaml"
        if company_yaml.exists():
            try:
                with open(company_yaml, "r", encoding="utf-8") as f:
                    self._data = yaml.safe_load(f) or {}
                logger.info(f"Loaded company config from {company_yaml}")
            except Exception as e:
                logger.error(f"Error loading {company_yaml}: {e}")
                self._data = {}
        else:
            logger.warning(
                f"Company config not found at {company_yaml}, "
                "using built-in defaults"
            )
            self._data = {}

        # Merge with defaults (deep merge for nested dicts)
        self._data = _deep_merge(_DEFAULT_COMPANY, self._data)

        # Load name capture messages
        name_capture_yaml = config_path / "prompts" / "name_capture.yaml"
        if name_capture_yaml.exists():
            try:
                with open(name_capture_yaml, "r", encoding="utf-8") as f:
                    self._name_capture = yaml.safe_load(f) or {}
                logger.info(f"Loaded name capture config from {name_capture_yaml}")
            except Exception as e:
                logger.error(f"Error loading {name_capture_yaml}: {e}")
                self._name_capture = {}
        else:
            self._name_capture = {}

        # Merge with defaults
        for key, default_val in _DEFAULT_NAME_CAPTURE.items():
            if key not in self._name_capture:
                self._name_capture[key] = default_val

        # Initialize Jinja2 environment
        prompts_dir = config_path / "prompts"
        if prompts_dir.exists():
            self._jinja_env = Environment(
                loader=FileSystemLoader(str(prompts_dir)),
                keep_trailing_newline=True,
            )
            logger.info(f"Loaded prompt templates from {prompts_dir}")
        else:
            self._jinja_env = None
            logger.warning(
                f"Prompts directory not found at {prompts_dir}, "
                "using fallback prompts"
            )

        self._initialized = True
        logger.info(
            f"Company config initialized: {self.company_name} "
            f"({len(self.lead_fields)} lead fields)"
        )

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # Company
    @property
    def company_name(self) -> str:
        return self._data["company"]["name"]

    @property
    def company_short_name(self) -> str:
        return self._data["company"].get("short_name", "")

    @property
    def company_description(self) -> str:
        return self._data["company"].get("description", "")

    @property
    def company_website(self) -> str:
        return self._data["company"].get("website", "")

    @property
    def company_contact_email(self) -> str:
        return self._data["company"].get("contact_email", "")

    @property
    def company_contact_phone(self) -> str:
        return self._data["company"].get("contact_phone", "")

    # Branding
    @property
    def bot_persona(self) -> str:
        return self._data["branding"]["bot_persona"]

    @property
    def user_term(self) -> str:
        return self._data["branding"]["user_term"]

    @property
    def welcome_emoji(self) -> str:
        return self._data["branding"]["welcome_emoji"]

    @property
    def offering_term(self) -> str:
        return self._data["branding"]["offering_term"]

    @property
    def escalation_message(self) -> str:
        return self._data["branding"]["escalation_message"]

    # Menu items
    @property
    def menu_items(self) -> List[str]:
        return self._data.get("menu_items", [])

    # Lead fields
    @property
    def lead_fields(self) -> List[Dict[str, str]]:
        return self._data.get("lead_fields", [])

    @property
    def lead_field_names(self) -> List[str]:
        """Return just the field name keys."""
        return [f["name"] for f in self.lead_fields]

    @property
    def lead_field_descriptions(self) -> Dict[str, str]:
        """Return {field_name: description} mapping."""
        return {f["name"]: f["description"] for f in self.lead_fields}

    # Knowledge repository
    @property
    def knowledge_repository_directory(self) -> str:
        return self._data.get("knowledge_repository", {}).get(
            "directory", "./knowledge_repository/default"
        )

    # ── Prompt Rendering ──────────────────────────────────────────────

    def _render_template(
        self, template_name: str, fallback: str, **kwargs: Any
    ) -> str:
        """Render a Jinja2 template with fallback to inline string."""
        if self._jinja_env is not None:
            try:
                template = self._jinja_env.get_template(template_name)
                return template.render(**kwargs)
            except TemplateNotFound:
                logger.warning(
                    f"Template '{template_name}' not found, using fallback"
                )
            except Exception as e:
                logger.error(
                    f"Error rendering template '{template_name}': {e}"
                )

        # Fallback: render inline string as a Jinja2 template
        from jinja2 import Template

        return Template(fallback).render(**kwargs)

    def render_system_prompt(
        self,
        *,
        name_instruction: str,
        lead_profile_section: str,
        context: str,
    ) -> str:
        """Render the main system prompt with all dynamic sections."""
        return self._render_template(
            "system_prompt.j2",
            _FALLBACK_SYSTEM_PROMPT,
            company_name=self.company_name,
            company_short_name=self.company_short_name,
            bot_persona=self.bot_persona,
            user_term=self.user_term,
            offering_term=self.offering_term,
            escalation_message=self.escalation_message,
            name_instruction=name_instruction,
            lead_profile_section=lead_profile_section,
            context=context,
        )

    def render_query_rewrite_prompt(
        self, *, history_text: str, user_message: str
    ) -> str:
        """Render the query rewriting prompt."""
        return self._render_template(
            "query_rewrite.j2",
            _FALLBACK_QUERY_REWRITE,
            history_text=history_text,
            user_message=user_message,
        )

    def render_lead_extraction_prompt(
        self, *, field_descriptions: str, user_message: str
    ) -> str:
        """Render the lead extraction prompt."""
        return self._render_template(
            "lead_extraction.j2",
            _FALLBACK_LEAD_EXTRACTION,
            field_descriptions=field_descriptions,
            user_message=user_message,
        )

    def render_name_capture_message(
        self, message_key: str, **kwargs: Any
    ) -> str:
        """Render a name capture flow message (welcome, confirmation, retry).

        Supports template variables: {{ name }}, {{ company_name }},
        {{ welcome_emoji }}, {{ menu_items }}.
        """
        template_str = self._name_capture.get(
            message_key,
            _DEFAULT_NAME_CAPTURE.get(message_key, ""),
        )

        from jinja2 import Template

        # Prepare kwargs without duplicates
        render_kwargs = {
            "name": kwargs.get("name", ""),
            "company_name": self.company_name,
            "welcome_emoji": self.welcome_emoji,
            "menu_items": self.menu_items,
        }
        for k, v in kwargs.items():
            if k not in render_kwargs:
                render_kwargs[k] = v

        return Template(template_str).render(**render_kwargs)

    # ── Full Config Access ────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Return the full configuration as a dict (for debugging/admin)."""
        return {
            "company": self._data.get("company", {}),
            "branding": self._data.get("branding", {}),
            "menu_items": self.menu_items,
            "lead_fields": self.lead_fields,
            "knowledge_repository": self._data.get("knowledge_repository", {}),
        }


# ── Helpers ───────────────────────────────────────────────────────────────


def _deep_merge(defaults: Dict, overrides: Dict) -> Dict:
    """Recursively merge overrides into defaults.

    - Dict values are merged recursively.
    - Non-dict values in overrides replace defaults.
    - Keys only in defaults are preserved.
    """
    result = defaults.copy()
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ── Singleton ─────────────────────────────────────────────────────────────

company_config = CompanyConfig()
