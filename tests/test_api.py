"""Tests for the API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_root_endpoint():
    """Root endpoint should return app name and status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "name" in data


@pytest.mark.anyio
async def test_health_endpoint():
    """Health check should return 200 with RAG status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "rag_initialized" in data
    assert "documents_loaded" in data


@pytest.mark.anyio
async def test_stats_endpoint():
    """Stats endpoint should return counts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_users" in data
    assert "total_conversations" in data
    assert "total_messages" in data


@pytest.mark.anyio
async def test_test_chat_endpoint():
    """Test-chat should create a user and return a greeting."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/test-chat",
            json={
                "phone_number": "919999900001",
                "message": "Hello",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["phone_number"] == "919999900001"
    assert "bot_response" in data
    assert data["conversation_id"] >= 1


@pytest.mark.anyio
async def test_test_chat_name_flow():
    """After greeting, bot should ask for name, then capture it."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First message — should ask for name
        r1 = await client.post(
            "/api/test-chat",
            json={"phone_number": "919999900002", "message": "Hi"},
        )
        assert r1.status_code == 200
        assert "name" in r1.json()["bot_response"].lower()

        # Second message — provide the name
        r2 = await client.post(
            "/api/test-chat",
            json={"phone_number": "919999900002", "message": "Ravi"},
        )
        assert r2.status_code == 200
        assert "Ravi" in r2.json()["bot_response"]


@pytest.mark.anyio
async def test_webhook_verify_missing_params():
    """Webhook GET with missing params should return 400."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/webhook")
    assert response.status_code == 400


@pytest.mark.anyio
async def test_webhook_post_empty_body():
    """Webhook POST with an empty entry should return ok."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/webhook", json={"entry": []})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_ingest_endpoint():
    """Admin ingest should succeed and return chunk count."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/admin/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "chunks_ingested" in data


@pytest.mark.anyio
async def test_conversation_not_found():
    """Requesting a non-existent conversation should return 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/admin/conversations/99999")
    assert response.status_code == 404
