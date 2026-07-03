"""Tests for the chat service."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_full_conversation_flow():
    """Simulate a complete conversation: greet → name → question."""
    transport = ASGITransport(app=app)
    phone = "919999900010"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. First message — should greet and ask for name
        r1 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Hello"},
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["user_name"] is None  # Name not yet captured
        assert "name" in d1["bot_response"].lower()

        # 2. Provide name
        r2 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Arun"},
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert "Arun" in d2["bot_response"]

        # 3. Ask a question (after name is captured)
        r3 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "What training programs do you offer?"},
        )
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["user_name"] == "Arun"
        assert len(d3["bot_response"]) > 10  # Non-empty response


@pytest.mark.anyio
async def test_user_persistence():
    """Same phone number should reuse existing user."""
    transport = ASGITransport(app=app)
    phone = "919999900020"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First interaction
        r1 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Hey"},
        )
        cid1 = r1.json()["conversation_id"]

        # Second interaction — same conversation
        r2 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Test"},
        )
        cid2 = r2.json()["conversation_id"]

        # Should be the same conversation (within timeout)
        assert cid1 == cid2


@pytest.mark.anyio
async def test_name_not_asked_again():
    """Once name is captured, bot should not ask for it again."""
    transport = ASGITransport(app=app)
    phone = "919999900030"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Greet
        await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Hi"},
        )

        # Provide name
        await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Priya"},
        )

        # Third message — should NOT ask for name
        r3 = await client.post(
            "/api/test-chat",
            json={"phone_number": phone, "message": "Tell me about fees"},
        )
        assert "name" not in r3.json()["bot_response"].lower() or "your name" not in r3.json()["bot_response"].lower()
