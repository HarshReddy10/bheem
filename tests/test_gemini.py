"""Unit tests for the GeminiProvider."""

from unittest.mock import MagicMock, patch
import pytest

from app.config import settings
from app.services.ai_service import GeminiProvider


@pytest.fixture
def mock_genai():
    """Mock the google-genai module."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        
        # Mock generate_content response
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini!"
        
        # Async mock for client.aio.models.generate_content
        async def mock_async_generate(*args, **kwargs):
            return mock_response
            
        mock_client.aio.models.generate_content = mock_async_generate
        
        yield mock_client


@pytest.mark.anyio
async def test_gemini_provider_unconfigured():
    """GeminiProvider should return a helpful error message when unconfigured."""
    # Temporarily clear key
    original_key = settings.gemini_api_key
    settings.gemini_api_key = ""
    
    try:
        provider = GeminiProvider()
        response = await provider.generate(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are an assistant.",
        )
        assert "not configured" in response.lower()
    finally:
        settings.gemini_api_key = original_key


@pytest.mark.anyio
async def test_gemini_provider_generate(mock_genai):
    """GeminiProvider should successfully call the Client and format messages."""
    original_key = settings.gemini_api_key
    original_model = settings.gemini_model
    
    settings.gemini_api_key = "test_key"
    settings.gemini_model = "gemini-2.5-flash"
    
    try:
        # Patch the Client inside GeminiProvider.__init__
        with patch("google.genai.Client", return_value=mock_genai):
            provider = GeminiProvider()
            
            messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "how are you?"},
            ]
            
            response = await provider.generate(
                messages=messages,
                system_prompt="System prompt context",
            )
            
            assert response == "Hello from Gemini!"
    finally:
        settings.gemini_api_key = original_key
        settings.gemini_model = original_model
