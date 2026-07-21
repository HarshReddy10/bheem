# Company Configuration Guide

This directory contains all company-specific configuration for the Bheem AI Lead Qualification Platform. To onboard a new company, copy this entire directory, edit the files below, and point the `COMPANY_CONFIG_DIR` environment variable to your copy.

**No source code changes are required.**

## Directory Structure

```
config/
├── company.yaml              # Company identity, branding, lead fields
├── README.md                 # This file
└── prompts/
    ├── system_prompt.j2      # Main AI system prompt (Jinja2)
    ├── query_rewrite.j2      # RAG query rewriting prompt
    ├── lead_extraction.j2    # Lead data extraction prompt
    └── name_capture.yaml     # Name capture flow messages
```

## Quick Start

1. Copy `config/` to a new directory (e.g., `config_acme/`).
2. Edit `company.yaml` with your company's details.
3. Optionally customize the prompt templates.
4. Set `COMPANY_CONFIG_DIR=./config_acme` in your `.env` file.
5. Restart the application.

## company.yaml Reference

### `company` section

| Field | Required | Description | Example |
|---|---|---|---|
| `name` | Yes | Full company name | `"Acme Corp"` |
| `short_name` | No | Abbreviation used in prompts | `"Acme"` |
| `description` | No | One-line company description | `"Enterprise SaaS provider"` |
| `website` | No | Company website URL | `"https://acme.com"` |
| `contact_email` | No | Public contact email | `"hello@acme.com"` |
| `contact_phone` | No | Public contact phone | `"+1 555-0100"` |

### `branding` section

| Field | Default | Description |
|---|---|---|
| `bot_persona` | `"a friendly, knowledgeable assistant"` | How the bot describes itself in the system prompt |
| `user_term` | `"customer"` | How the bot internally refers to the user (e.g., "student", "prospect", "client") |
| `welcome_emoji` | `"👋"` | Emoji used in the welcome message |
| `offering_term` | `"products and services"` | Generic term for what the company offers |
| `escalation_message` | `"I'd recommend reaching out to our team..."` | What the bot says when it can't answer |

### `menu_items` section

A list of strings shown to the user after name capture. These should reflect the main categories the bot can help with.

```yaml
menu_items:
  - "Product catalog & pricing"
  - "Implementation timeline"
  - "Support & documentation"
  - "General questions"
```

### `lead_fields` section

Defines what lead qualification data to collect passively from conversations. Each field has:

| Property | Required | Description |
|---|---|---|
| `name` | Yes | Internal key (used in JSON storage, must be a valid identifier) |
| `description` | Yes | Human-readable description (shown to the LLM for extraction) |
| `example` | No | Example value (for documentation) |

```yaml
lead_fields:
  - name: "company_size"
    description: "How many employees their company has"
    example: "500 employees"

  - name: "budget"
    description: "Their budget range for this purchase"
    example: "$50,000 annually"

  - name: "decision_timeline"
    description: "When they plan to make a purchasing decision"
    example: "End of Q3"

  - name: "current_solution"
    description: "What tool or process they currently use"
    example: "Spreadsheets and email"
```

### `knowledge_base` section

| Field | Default | Description |
|---|---|---|
| `directory` | `"./knowledge_base"` | Path to the folder containing knowledge base documents |

## Prompt Templates

Prompt templates use [Jinja2](https://jinja.palletsprojects.com/) syntax. Available variables vary by template:

### `system_prompt.j2`

The main AI personality and behavior prompt.

| Variable | Description |
|---|---|
| `{{ company_name }}` | From `company.name` |
| `{{ company_short_name }}` | From `company.short_name` |
| `{{ bot_persona }}` | From `branding.bot_persona` |
| `{{ user_term }}` | From `branding.user_term` |
| `{{ offering_term }}` | From `branding.offering_term` |
| `{{ escalation_message }}` | From `branding.escalation_message` |
| `{{ name_instruction }}` | Auto-generated: "The user's name is X..." |
| `{{ lead_profile_section }}` | Auto-generated: conversation memory |
| `{{ context }}` | RAG-retrieved knowledge base chunks |

### `query_rewrite.j2`

Rewrites follow-up questions into standalone search queries.

| Variable | Description |
|---|---|
| `{{ history_text }}` | Recent conversation history |
| `{{ user_message }}` | The user's latest message |

### `lead_extraction.j2`

Extracts structured data from user messages.

| Variable | Description |
|---|---|
| `{{ field_descriptions }}` | Formatted list of missing fields to look for |
| `{{ user_message }}` | The user's message to analyze |

### `name_capture.yaml`

Three message templates for the name capture flow:

| Key | Variables | Purpose |
|---|---|---|
| `welcome` | `{{ company_name }}`, `{{ welcome_emoji }}` | First message to a new user |
| `confirmation` | `{{ name }}`, `{{ menu_items }}` | After the user provides their name |
| `retry` | `{{ company_name }}` | When the response doesn't look like a name |

## Fallback Behavior

If `config/` is missing or incomplete:
- The platform starts with generic built-in defaults.
- Missing YAML fields are filled from defaults.
- Missing template files fall back to inline prompt strings.
- The application **always starts** — no config file is strictly required.
