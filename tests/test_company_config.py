"""Tests for the company configuration loader."""

import pytest
import yaml
import os
from pathlib import Path
from unittest.mock import patch

from app.company_config import CompanyConfig, _deep_merge


class TestDeepMerge:
    """Unit tests for the _deep_merge helper."""

    def test_simple_override(self):
        defaults = {"a": 1, "b": 2}
        overrides = {"b": 3}
        result = _deep_merge(defaults, overrides)
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self):
        defaults = {"a": {"x": 1, "y": 2}, "b": 3}
        overrides = {"a": {"y": 99}}
        result = _deep_merge(defaults, overrides)
        assert result == {"a": {"x": 1, "y": 99}, "b": 3}

    def test_new_keys_added(self):
        defaults = {"a": 1}
        overrides = {"b": 2}
        result = _deep_merge(defaults, overrides)
        assert result == {"a": 1, "b": 2}

    def test_empty_overrides(self):
        defaults = {"a": 1, "b": {"c": 3}}
        result = _deep_merge(defaults, {})
        assert result == defaults

    def test_list_replaced_not_merged(self):
        defaults = {"items": [1, 2, 3]}
        overrides = {"items": [4, 5]}
        result = _deep_merge(defaults, overrides)
        assert result == {"items": [4, 5]}


class TestCompanyConfig:
    """Tests for CompanyConfig loading and rendering."""

    def test_initialization_with_defaults(self, tmp_path):
        """Config should initialize with built-in defaults when no files exist."""
        config = CompanyConfig()
        config.initialize(str(tmp_path))  # Empty directory
        assert config.is_initialized
        assert config.company_name == "AI Lead Qualification Platform"
        assert len(config.lead_fields) > 0

    def test_initialization_with_yaml(self, tmp_path):
        """Config should load values from company.yaml."""
        company_data = {
            "company": {
                "name": "Test Corp",
                "short_name": "TC",
            },
            "branding": {
                "bot_persona": "a helpful sales rep",
                "user_term": "prospect",
            },
            "menu_items": ["Product A", "Product B"],
            "lead_fields": [
                {
                    "name": "budget",
                    "description": "Their budget",
                    "example": "$10k",
                },
            ],
        }
        yaml_file = tmp_path / "company.yaml"
        yaml_file.write_text(yaml.dump(company_data))

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        assert config.company_name == "Test Corp"
        assert config.company_short_name == "TC"
        assert config.bot_persona == "a helpful sales rep"
        assert config.user_term == "prospect"
        assert config.menu_items == ["Product A", "Product B"]
        assert len(config.lead_fields) == 1
        assert config.lead_fields[0]["name"] == "budget"

    def test_defaults_preserved_when_partially_overridden(self, tmp_path):
        """Missing fields should fall back to defaults."""
        company_data = {
            "company": {
                "name": "Partial Corp",
            },
        }
        yaml_file = tmp_path / "company.yaml"
        yaml_file.write_text(yaml.dump(company_data))

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        assert config.company_name == "Partial Corp"
        # These should come from defaults
        assert config.bot_persona != ""
        assert config.user_term != ""
        assert len(config.menu_items) > 0

    def test_lead_field_names(self, tmp_path):
        """lead_field_names should return just the name keys."""
        company_data = {
            "lead_fields": [
                {"name": "budget", "description": "Budget"},
                {"name": "timeline", "description": "Timeline"},
            ],
        }
        yaml_file = tmp_path / "company.yaml"
        yaml_file.write_text(yaml.dump(company_data))

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        assert config.lead_field_names == ["budget", "timeline"]

    def test_lead_field_descriptions(self, tmp_path):
        """lead_field_descriptions should return {name: desc} mapping."""
        company_data = {
            "lead_fields": [
                {"name": "budget", "description": "Their budget range"},
            ],
        }
        yaml_file = tmp_path / "company.yaml"
        yaml_file.write_text(yaml.dump(company_data))

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        assert config.lead_field_descriptions == {"budget": "Their budget range"}

    def test_to_dict(self, tmp_path):
        """to_dict should return the full config as a serializable dict."""
        config = CompanyConfig()
        config.initialize(str(tmp_path))
        d = config.to_dict()
        assert "company" in d
        assert "branding" in d
        assert "lead_fields" in d
        assert "menu_items" in d


class TestPromptRendering:
    """Tests for Jinja2 prompt template rendering."""

    def test_system_prompt_with_templates(self, tmp_path):
        """System prompt should render with template variables."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "system_prompt.j2").write_text(
            "You are {{ bot_persona }} for {{ company_name }}. "
            "{{ name_instruction }} {{ lead_profile_section }} "
            "Context: {{ context }}"
        )

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        result = config.render_system_prompt(
            name_instruction="User is Alice.",
            lead_profile_section="Knows about budget.",
            context="Some RAG context.",
        )

        assert config.company_name in result
        assert "Alice" in result
        assert "Some RAG context" in result

    def test_system_prompt_fallback(self, tmp_path):
        """Should use fallback prompt when template file is missing."""
        config = CompanyConfig()
        config.initialize(str(tmp_path))  # No prompts dir

        result = config.render_system_prompt(
            name_instruction="User is Bob.",
            lead_profile_section="",
            context="Context here.",
        )

        assert "Bob" in result
        assert "Context here" in result

    def test_query_rewrite_prompt(self, tmp_path):
        """Query rewrite template should render correctly."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "query_rewrite.j2").write_text(
            "History: {{ history_text }}\nQuery: {{ user_message }}"
        )

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        result = config.render_query_rewrite_prompt(
            history_text="User asked about pricing.",
            user_message="How much?",
        )

        assert "pricing" in result
        assert "How much?" in result

    def test_name_capture_messages(self, tmp_path):
        """Name capture messages should render with variables."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        name_capture = {
            "welcome": "Welcome to {{ company_name }}! {{ welcome_emoji }}",
            "confirmation": "Hi {{ name }}! Menu:\n{% for item in menu_items %}• {{ item }}\n{% endfor %}",
            "retry": "Please share your name.",
        }
        (prompts_dir / "name_capture.yaml").write_text(yaml.dump(name_capture))

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        welcome = config.render_name_capture_message("welcome")
        assert config.company_name in welcome

        confirmation = config.render_name_capture_message("confirmation", name="Alice")
        assert "Alice" in confirmation

        retry = config.render_name_capture_message("retry")
        assert "name" in retry.lower()

    def test_lead_extraction_prompt(self, tmp_path):
        """Lead extraction template should render with field descriptions."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "lead_extraction.j2").write_text(
            "Fields: {{ field_descriptions }}\nMessage: {{ user_message }}"
        )

        config = CompanyConfig()
        config.initialize(str(tmp_path))

        result = config.render_lead_extraction_prompt(
            field_descriptions="- budget: Their budget",
            user_message="I have $5000 to spend",
        )

        assert "budget" in result
        assert "$5000" in result
