"""LLM provider interface and implementations.

Provides:
- Abstract ``LLMProvider`` base class
- ``MockProvider`` — keyword-based responses for testing without API keys
- ``AntigravityProvider`` — OpenAI-compatible API for production use
- ``get_llm_provider()`` factory to select the active provider
"""

from abc import ABC, abstractmethod
from typing import Dict, List

import httpx

from app.config import settings
from app.utils.logger import logger


class LLMProvider(ABC):
    """Abstract base class that all LLM providers must implement."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a text response given conversation history and a system prompt."""
        ...


# ── Mock Provider ─────────────────────────────────────────────────────────


class MockProvider(LLMProvider):
    """Keyword-based mock LLM for local testing without API keys.

    Returns plausible canned responses so you can verify the full
    pipeline end-to-end before connecting a real LLM.
    """

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        if not messages:
            return "Hello! How can I help you today?"

        last_message = messages[-1].get("content", "").lower()

        # Greetings
        if any(w in last_message for w in ("hi", "hello", "hey", "greetings")):
            return (
                "Hello! Welcome to our Placement & Training Services. 😊\n\n"
                "How can I assist you today? I can help with information about "
                "our training programs, placement process, fees, and more."
            )

        # Training
        if any(w in last_message for w in ("training", "course", "program", "learn")):
            return (
                "We offer various training programs designed to enhance your skills "
                "and improve your placement prospects. Could you tell me which area "
                "you're interested in? I'll check our knowledge base for details."
            )

        # Placement
        if any(w in last_message for w in ("placement", "job", "career", "hire")):
            return (
                "Our placement services connect trained candidates with top employers. "
                "We have a strong track record of successful placements. Would you like "
                "to know more about our placement process, eligibility, or success rates?"
            )

        # Fees
        if any(w in last_message for w in ("fee", "cost", "price", "payment")):
            return (
                "For detailed fee information, I'd recommend checking with our "
                "admissions team. I can share general information from our documents. "
                "Is there a specific program you're asking about?"
            )

        # Contact
        if any(w in last_message for w in ("contact", "phone", "email", "reach")):
            return (
                "You can reach our team through the contact information provided "
                "in our official communications. Would you like help with anything "
                "specific about our services?"
            )

        # Farewell
        if any(w in last_message for w in ("thank", "thanks", "bye", "goodbye")):
            return (
                "You're welcome! Don't hesitate to reach out if you have more "
                "questions. Have a great day! 😊"
            )

        # Default
        return (
            "Thank you for your question. Based on our available information, "
            "I'd be happy to help you with queries about our training programs, "
            "placement services, fees, and general information. Could you please "
            "be more specific about what you'd like to know?"
        )


# ── Antigravity Provider ─────────────────────────────────────────────────


class AntigravityProvider(LLMProvider):
    """Production LLM provider using an OpenAI-compatible API.

    Configure via environment variables:
    - ANTIGRAVITY_API_KEY
    - ANTIGRAVITY_API_URL
    - ANTIGRAVITY_MODEL
    """

    def __init__(self) -> None:
        self.api_key = settings.antigravity_api_key
        self.api_url = settings.antigravity_api_url.rstrip("/")
        self.model = settings.antigravity_model

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        if not self.api_key:
            logger.error("Antigravity API key not configured")
            return (
                "I'm sorry, the AI service is not properly configured. "
                "Please contact support."
            )

        # Prepend system prompt
        full_messages = [{"role": "system", "content": system_prompt}]
        full_messages.extend(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Antigravity API error: {e.response.status_code} — {e.response.text}"
            )
            return "I'm experiencing a temporary issue. Please try again in a moment."
        except Exception as e:
            logger.error(f"Error calling Antigravity API: {e}")
            return "I'm experiencing a temporary issue. Please try again in a moment."


class GeminiProvider(LLMProvider):
    """Production LLM provider using the official Google Gemini GenAI SDK.

    Configure via environment variables:
    - GEMINI_API_KEY
    - GEMINI_MODEL (e.g. gemini-2.5-flash)
    """

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini GenAI Client: {e}")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        if not self.api_key or not self._client:
            logger.error("Gemini API key not configured")
            return (
                "I'm sorry, the Google Gemini AI service is not configured. "
                "Please configure GEMINI_API_KEY in your environment."
            )

        from google.genai import types

        # Map conversation messages to Gemini's Contents format
        contents = []
        for msg in messages:
            role = msg["role"]
            if role == "assistant":
                gemini_role = "model"
            elif role == "system":
                continue
            else:
                gemini_role = "user"

            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=msg["content"])]
                )
            )

        try:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
            )

            # Call async generation
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            return response.text or "I'm sorry, I couldn't generate a response."
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return "I'm experiencing a temporary issue. Please try again in a moment."


# ── Factory ───────────────────────────────────────────────────────────────


def get_llm_provider() -> LLMProvider:
    """Return the LLM provider specified by ``LLM_PROVIDER`` in config."""
    provider_name = settings.llm_provider.lower()

    providers = {
        "mock": MockProvider,
        "antigravity": AntigravityProvider,
        "gemini": GeminiProvider,
    }

    provider_class = providers.get(provider_name)
    if provider_class is None:
        logger.warning(
            f"Unknown LLM provider '{provider_name}', falling back to mock"
        )
        provider_class = MockProvider

    logger.info(f"Using LLM provider: {provider_class.__name__}")
    return provider_class()

