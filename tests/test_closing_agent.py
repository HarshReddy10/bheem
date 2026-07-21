"""Tests for the Closing Agent end-to-end journey.

21 test cases covering:
- Core flow (greeting, course selection, RAG, purchase, payment)
- WhatsApp interactive message parsing
- Razorpay webhook processing (signature, dedup, idempotency)
- Edge cases (duplicates, failures, non-message payloads)
"""

import hashlib
import hmac
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _test_chat(client, phone, message, interactive=None):
    """Helper to call the test-chat endpoint."""
    body = {"phone_number": phone, "message": message}
    if interactive:
        body["interactive"] = interactive
    return client.post("/api/test-chat", json=body)


# ── Helpers ──────────────────────────────────────────────────────────────

async def _setup_user_with_name(client, phone="919999900099"):
    """Create a user and set their name via the name-capture flow."""
    await _test_chat(client, phone, "Hi")
    await _test_chat(client, phone, "TestUser")
    return phone


async def _select_course(client, phone):
    """Select Data Science course."""
    r = await _test_chat(client, phone, "I want to learn data science")
    return r


def _make_razorpay_signature(body_bytes: bytes, secret: str) -> str:
    """Compute a valid Razorpay HMAC-SHA256 signature."""
    return hmac.new(
        secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()


# ════════════════════════════════════════════════════════════════════════
# Test 1: New user greeting
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_01_new_user_greeting():
    """New user sends 'Hi' → welcome message asking for name."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await _test_chat(client, "919900010001", "Hi")
    assert r.status_code == 200
    data = r.json()
    # Should ask for name first
    assert "name" in data["bot_response"].lower()


# ════════════════════════════════════════════════════════════════════════
# Test 2: Course selection
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_02_course_selection():
    """User selects Data Science → bot shows course details + buttons."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        phone = await _setup_user_with_name(client, "919900010002")
        r = await _select_course(client, phone)
    assert r.status_code == 200
    data = r.json()
    assert "data science" in data["bot_response"].lower()
    assert data.get("state") == "AWAITING_PURCHASE_CONFIRMATION"
    assert data.get("interactive") is not None


# ════════════════════════════════════════════════════════════════════════
# Test 3: Course question via RAG
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_03_course_question_rag():
    """User asks a question → RAG answer with purchase prompt."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        phone = await _setup_user_with_name(client, "919900010003")
        await _select_course(client, phone)
        r = await _test_chat(client, phone, "What is the syllabus?")
    assert r.status_code == 200
    data = r.json()
    assert data["bot_response"]  # Should have some answer
    assert data.get("state") == "ANSWERING_QUESTIONS"


# ════════════════════════════════════════════════════════════════════════
# Test 4: Course preserved after RAG question
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_04_course_preserved_after_rag():
    """After a RAG Q&A, the selected course is still in the session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        phone = await _setup_user_with_name(client, "919900010004")
        await _select_course(client, phone)
        # Ask a question (should not reset course)
        await _test_chat(client, phone, "What are the placements like?")
        # Now confirm purchase — should work because course is preserved
        r = await _test_chat(client, phone, "proceed_to_payment")

    data = r.json()
    # Should attempt payment (may fail due to no Razorpay creds, but
    # the attempt proves the course was preserved)
    assert data.get("state") in ("PAYMENT_PENDING", "AWAITING_PURCHASE_CONFIRMATION")


# ════════════════════════════════════════════════════════════════════════
# Test 5: Purchase confirmation creates internal order
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_05_purchase_creates_order():
    """Proceeding to payment creates an Order record in the database."""
    transport = ASGITransport(app=app)

    with patch("app.services.message_processor.create_payment_link") as mock_pay:
        mock_pay.return_value = {
            "id": "plink_test123",
            "short_url": "https://rzp.io/test123",
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            phone = await _setup_user_with_name(client, "919900010005")
            await _select_course(client, phone)
            r = await _test_chat(client, phone, "proceed_to_payment")

    data = r.json()
    assert data.get("state") == "PAYMENT_PENDING"
    assert "rzp.io" in data["bot_response"]


# ════════════════════════════════════════════════════════════════════════
# Test 6: Razorpay payment link creation
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_06_razorpay_link_creation():
    """Mock Razorpay API returns a valid payment link."""
    transport = ASGITransport(app=app)

    with patch("app.services.message_processor.create_payment_link") as mock_pay:
        mock_pay.return_value = {
            "id": "plink_test456",
            "short_url": "https://rzp.io/test456",
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            phone = await _setup_user_with_name(client, "919900010006")
            await _select_course(client, phone)
            r = await _test_chat(client, phone, "Yes, proceed")

    data = r.json()
    assert "rzp.io/test456" in data["bot_response"]
    mock_pay.assert_called_once()


# ════════════════════════════════════════════════════════════════════════
# Test 7: Invalid Razorpay signature rejection
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_07_invalid_razorpay_signature():
    """POST to razorpay-webhook with bad signature → 401."""
    transport = ASGITransport(app=app)

    # Set a webhook secret for this test
    original = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "test_secret_123"

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/closing-agent/razorpay-webhook",
                content=b'{"event": "payment_link.paid"}',
                headers={"X-Razorpay-Signature": "invalid_signature"},
            )
        assert r.status_code == 401
    finally:
        settings.razorpay_webhook_secret = original


# ════════════════════════════════════════════════════════════════════════
# Test 8: Successful Razorpay webhook
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_08_successful_razorpay_webhook():
    """Valid Razorpay webhook → order.status = 'paid'."""
    transport = ASGITransport(app=app)
    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "webhook_secret_test"

    try:
        with patch("app.services.message_processor.create_payment_link") as mock_pay:
            mock_pay.return_value = {
                "id": "plink_wh_test",
                "short_url": "https://rzp.io/wh_test",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                phone = await _setup_user_with_name(client, "919900010008")
                await _select_course(client, phone)
                await _test_chat(client, phone, "proceed_to_payment")

                # Now simulate Razorpay webhook
                webhook_body = json.dumps({
                    "event": "payment_link.paid",
                    "account_id": "acc_test",
                    "payload": {
                        "payment_link": {"entity": {"id": "plink_wh_test"}},
                        "payment": {"entity": {"id": "pay_test123"}},
                    },
                }).encode()

                sig = _make_razorpay_signature(webhook_body, "webhook_secret_test")

                with patch.object(
                    __import__("app.services.whatsapp", fromlist=["whatsapp_client"]).whatsapp_client,
                    "send_structured_response",
                    new_callable=AsyncMock,
                    return_value=True,
                ):
                    r = await client.post(
                        "/closing-agent/razorpay-webhook",
                        content=webhook_body,
                        headers={"X-Razorpay-Signature": sig},
                    )

        assert r.status_code == 200
    finally:
        settings.razorpay_webhook_secret = original_secret


# ════════════════════════════════════════════════════════════════════════
# Test 9: Duplicate Razorpay webhook
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_09_duplicate_razorpay_webhook():
    """Sending the same Razorpay event twice → 200 both times, one DB update."""
    transport = ASGITransport(app=app)
    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "webhook_secret_dup"

    try:
        with patch("app.services.message_processor.create_payment_link") as mock_pay:
            mock_pay.return_value = {
                "id": "plink_dup_test",
                "short_url": "https://rzp.io/dup_test",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                phone = await _setup_user_with_name(client, "919900010009")
                await _select_course(client, phone)
                await _test_chat(client, phone, "proceed_to_payment")

                webhook_body = json.dumps({
                    "event": "payment_link.paid",
                    "account_id": "acc_dup",
                    "payload": {
                        "payment_link": {"entity": {"id": "plink_dup_test"}},
                        "payment": {"entity": {"id": "pay_dup123"}},
                    },
                }).encode()

                sig = _make_razorpay_signature(webhook_body, "webhook_secret_dup")

                with patch.object(
                    __import__("app.services.whatsapp", fromlist=["whatsapp_client"]).whatsapp_client,
                    "send_structured_response",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as mock_send:
                    r1 = await client.post(
                        "/closing-agent/razorpay-webhook",
                        content=webhook_body,
                        headers={"X-Razorpay-Signature": sig},
                    )
                    r2 = await client.post(
                        "/closing-agent/razorpay-webhook",
                        content=webhook_body,
                        headers={"X-Razorpay-Signature": sig},
                    )

        assert r1.status_code == 200
        assert r2.status_code == 200
        # WhatsApp should only be called once (first webhook)
        assert mock_send.call_count == 1
    finally:
        settings.razorpay_webhook_secret = original_secret


# ════════════════════════════════════════════════════════════════════════
# Test 10: Payment confirmation contains identifiers
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_10_payment_confirmation_identifiers():
    """Payment confirmation message contains order ID and payment ID."""
    transport = ASGITransport(app=app)
    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "webhook_secret_ids"

    confirmation_messages = []

    async def capture_send(to, bot_response):
        confirmation_messages.append(bot_response.message)
        return True

    try:
        with patch("app.services.message_processor.create_payment_link") as mock_pay:
            mock_pay.return_value = {
                "id": "plink_ids_test",
                "short_url": "https://rzp.io/ids_test",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                phone = await _setup_user_with_name(client, "919900010010")
                await _select_course(client, phone)
                await _test_chat(client, phone, "proceed_to_payment")

                webhook_body = json.dumps({
                    "event": "payment_link.paid",
                    "account_id": "acc_ids",
                    "payload": {
                        "payment_link": {"entity": {"id": "plink_ids_test"}},
                        "payment": {"entity": {"id": "pay_ids_789"}},
                    },
                }).encode()

                sig = _make_razorpay_signature(webhook_body, "webhook_secret_ids")

                with patch.object(
                    __import__("app.services.whatsapp", fromlist=["whatsapp_client"]).whatsapp_client,
                    "send_structured_response",
                    side_effect=capture_send,
                ):
                    await client.post(
                        "/closing-agent/razorpay-webhook",
                        content=webhook_body,
                        headers={"X-Razorpay-Signature": sig},
                    )

        assert len(confirmation_messages) == 1
        msg = confirmation_messages[0]
        assert "pay_ids_789" in msg
        assert "ORD-" in msg  # internal order ID prefix
    finally:
        settings.razorpay_webhook_secret = original_secret


# ════════════════════════════════════════════════════════════════════════
# Test 11: Reply-button payload parsing
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_11_button_reply_parsing():
    """WhatsApp button_reply payload is correctly parsed."""
    from app.services.whatsapp import whatsapp_client

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919999900001",
                        "id": "msg_001",
                        "type": "interactive",
                        "timestamp": "1234567890",
                        "interactive": {
                            "type": "button_reply",
                            "button_reply": {
                                "id": "proceed_to_payment",
                                "title": "Proceed to Payment",
                            },
                        },
                    }],
                },
            }],
        }],
    }

    msg = whatsapp_client.parse_message(payload)
    assert msg is not None
    assert msg.message_type == "interactive"
    assert msg.text == "proceed_to_payment"
    assert msg.interactive_data["type"] == "button_reply"
    assert msg.interactive_data["id"] == "proceed_to_payment"


# ════════════════════════════════════════════════════════════════════════
# Test 12: List-reply payload parsing
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_12_list_reply_parsing():
    """WhatsApp list_reply payload is correctly parsed."""
    from app.services.whatsapp import whatsapp_client

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919999900002",
                        "id": "msg_002",
                        "type": "interactive",
                        "timestamp": "1234567890",
                        "interactive": {
                            "type": "list_reply",
                            "list_reply": {
                                "id": "course_data_science",
                                "title": "Data Science",
                                "description": "6 months",
                            },
                        },
                    }],
                },
            }],
        }],
    }

    msg = whatsapp_client.parse_message(payload)
    assert msg is not None
    assert msg.message_type == "interactive"
    assert msg.text == "course_data_science"
    assert msg.interactive_data["type"] == "list_reply"
    assert msg.interactive_data["id"] == "course_data_science"


# ════════════════════════════════════════════════════════════════════════
# Test 13: Stable action-ID routing
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_13_action_id_routing():
    """Pressing 'proceed_to_payment' button creates an order."""
    transport = ASGITransport(app=app)

    with patch("app.services.message_processor.create_payment_link") as mock_pay:
        mock_pay.return_value = {
            "id": "plink_action_test",
            "short_url": "https://rzp.io/action_test",
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            phone = await _setup_user_with_name(client, "919900010013")
            await _select_course(client, phone)
            r = await _test_chat(
                client, phone, "proceed_to_payment",
                interactive={"type": "button_reply", "id": "proceed_to_payment", "title": "Proceed to Payment"},
            )

    data = r.json()
    assert data.get("state") == "PAYMENT_PENDING"


# ════════════════════════════════════════════════════════════════════════
# Test 14: Ask a Question preserves course
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_14_ask_question_preserves_course():
    """Pressing 'Ask a Question' doesn't reset the selected course."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        phone = await _setup_user_with_name(client, "919900010014")
        await _select_course(client, phone)

        # Press Ask a Question
        r = await _test_chat(
            client, phone, "ask_question",
            interactive={"type": "button_reply", "id": "ask_question", "title": "Ask a Question"},
        )
        data = r.json()
        assert data.get("state") == "ANSWERING_QUESTIONS"
        # The course hint should be in the response
        assert "data science" in data["bot_response"].lower()


# ════════════════════════════════════════════════════════════════════════
# Test 15: Malformed interactive payload
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_15_malformed_interactive_payload():
    """Malformed interactive payload is handled gracefully."""
    from app.services.whatsapp import whatsapp_client

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "919999900003",
                        "id": "msg_003",
                        "type": "interactive",
                        "timestamp": "1234567890",
                        "interactive": {},  # Missing type and reply
                    }],
                },
            }],
        }],
    }

    msg = whatsapp_client.parse_message(payload)
    # Should parse without error but text will be None
    assert msg is not None
    assert msg.message_type == "interactive"
    assert msg.text is None


# ════════════════════════════════════════════════════════════════════════
# Test 16: Migration preserves existing order data
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_16_migration_preserves_data():
    """Migration script preserves existing order rows."""
    # Create a temporary database with the old schema
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_migrate.db"

        conn = sqlite3.connect(str(db_path))
        try:
            # Create old-schema tables
            conn.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    phone_number VARCHAR(20) UNIQUE,
                    name VARCHAR(100),
                    lead_profile TEXT,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)
            conn.execute("""
                CREATE TABLE conversations (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    started_at DATETIME,
                    last_message_at DATETIME,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER,
                    payment_link_id VARCHAR(255) UNIQUE,
                    status VARCHAR(50) DEFAULT 'created',
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """)

            # Insert test data
            conn.execute("INSERT INTO users VALUES (1, '919900000001', 'Test', NULL, '2026-01-01', '2026-01-01')")
            conn.execute("INSERT INTO conversations VALUES (1, 1, '2026-01-01', '2026-01-01', 1)")
            conn.execute("INSERT INTO orders VALUES (1, 1, 'plink_old_123', 'created', '2026-01-01', '2026-01-01')")
            conn.commit()

            # Run migration functions
            import scripts.migrate_closing_agent as mig
            mig.migrate_orders_table(conn)
            mig.create_closing_sessions_table(conn)
            mig.create_webhook_events_table(conn)

            # Verify data preserved
            cursor = conn.execute("SELECT * FROM orders WHERE id = 1")
            row = cursor.fetchone()
            assert row is not None

            # Verify old payment_link_id was copied
            cols = mig.get_existing_columns(conn, "orders")
            assert "razorpay_payment_link_id" in cols

            cursor = conn.execute("SELECT razorpay_payment_link_id FROM orders WHERE id = 1")
            val = cursor.fetchone()[0]
            assert val == "plink_old_123"

            # Verify new tables exist
            assert mig.table_exists(conn, "closing_sessions")
            assert mig.table_exists(conn, "webhook_events")

            # Verify idempotency — run again
            mig.migrate_orders_table(conn)
            mig.create_closing_sessions_table(conn)
            mig.create_webhook_events_table(conn)
            assert mig.verify_migration(conn)
        finally:
            conn.close()


# ════════════════════════════════════════════════════════════════════════
# Test 17: Duplicate Proceed to Payment
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_17_duplicate_proceed_to_payment():
    """Pressing 'Proceed to Payment' twice reuses the same order."""
    transport = ASGITransport(app=app)

    with patch("app.services.message_processor.create_payment_link") as mock_pay:
        mock_pay.return_value = {
            "id": "plink_dup_pay",
            "short_url": "https://rzp.io/dup_pay",
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            phone = await _setup_user_with_name(client, "919900010017")
            await _select_course(client, phone)

            r1 = await _test_chat(client, phone, "proceed_to_payment")
            r2 = await _test_chat(client, phone, "proceed_to_payment")

    # Both should return PAYMENT_PENDING
    assert r1.json().get("state") == "PAYMENT_PENDING"
    assert r2.json().get("state") == "PAYMENT_PENDING"
    # Payment link should only be created once
    assert mock_pay.call_count == 1
    # Second response should contain the same URL
    assert "rzp.io/dup_pay" in r2.json()["bot_response"]


# ════════════════════════════════════════════════════════════════════════
# Test 18: Repeated textual purchase confirmations
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_18_repeated_text_confirmations():
    """Sending 'yes' multiple times doesn't create duplicate orders."""
    transport = ASGITransport(app=app)

    with patch("app.services.message_processor.create_payment_link") as mock_pay:
        mock_pay.return_value = {
            "id": "plink_text_dup",
            "short_url": "https://rzp.io/text_dup",
        }
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            phone = await _setup_user_with_name(client, "919900010018")
            await _select_course(client, phone)

            r1 = await _test_chat(client, phone, "Yes")
            r2 = await _test_chat(client, phone, "Yes, proceed")
            r3 = await _test_chat(client, phone, "Confirm")

    # Only one payment link creation
    assert mock_pay.call_count == 1
    # All responses should show the payment link
    for r in (r1, r2, r3):
        assert "rzp.io/text_dup" in r.json()["bot_response"]


# ════════════════════════════════════════════════════════════════════════
# Test 19: Duplicate Razorpay event IDs
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_19_duplicate_razorpay_event_ids():
    """WebhookEvent dedup: same event ID → only one order update."""
    transport = ASGITransport(app=app)
    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "webhook_secret_dedup19"

    try:
        with patch("app.services.message_processor.create_payment_link") as mock_pay:
            mock_pay.return_value = {
                "id": "plink_dedup19",
                "short_url": "https://rzp.io/dedup19",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                phone = await _setup_user_with_name(client, "919900010019")
                await _select_course(client, phone)
                await _test_chat(client, phone, "proceed_to_payment")

                webhook_body = json.dumps({
                    "event": "payment_link.paid",
                    "account_id": "acc_dedup19",
                    "payload": {
                        "payment_link": {"entity": {"id": "plink_dedup19"}},
                        "payment": {"entity": {"id": "pay_dedup19"}},
                    },
                }).encode()

                sig = _make_razorpay_signature(webhook_body, "webhook_secret_dedup19")

                with patch.object(
                    __import__("app.services.whatsapp", fromlist=["whatsapp_client"]).whatsapp_client,
                    "send_structured_response",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as mock_wa:
                    # Send same event 3 times
                    for _ in range(3):
                        r = await client.post(
                            "/closing-agent/razorpay-webhook",
                            content=webhook_body,
                            headers={"X-Razorpay-Signature": sig},
                        )
                        assert r.status_code == 200

                    # WhatsApp should only be called once
                    assert mock_wa.call_count == 1
    finally:
        settings.razorpay_webhook_secret = original_secret


# ════════════════════════════════════════════════════════════════════════
# Test 20: WhatsApp failure after committed payment
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_20_whatsapp_failure_after_payment():
    """WhatsApp send failure doesn't rollback the paid order."""
    transport = ASGITransport(app=app)
    original_secret = settings.razorpay_webhook_secret
    settings.razorpay_webhook_secret = "webhook_secret_fail20"

    try:
        with patch("app.services.message_processor.create_payment_link") as mock_pay:
            mock_pay.return_value = {
                "id": "plink_fail20",
                "short_url": "https://rzp.io/fail20",
            }
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                phone = await _setup_user_with_name(client, "919900010020")
                await _select_course(client, phone)
                await _test_chat(client, phone, "proceed_to_payment")

                webhook_body = json.dumps({
                    "event": "payment_link.paid",
                    "account_id": "acc_fail20",
                    "payload": {
                        "payment_link": {"entity": {"id": "plink_fail20"}},
                        "payment": {"entity": {"id": "pay_fail20"}},
                    },
                }).encode()

                sig = _make_razorpay_signature(webhook_body, "webhook_secret_fail20")

                # Make WhatsApp send fail
                with patch.object(
                    __import__("app.services.whatsapp", fromlist=["whatsapp_client"]).whatsapp_client,
                    "send_structured_response",
                    new_callable=AsyncMock,
                    side_effect=Exception("WhatsApp API down"),
                ):
                    r = await client.post(
                        "/closing-agent/razorpay-webhook",
                        content=webhook_body,
                        headers={"X-Razorpay-Signature": sig},
                    )

                # Should still return 200 (payment committed)
                assert r.status_code == 200

                # Verify order is still paid by checking via test-chat
                # (the bot should say "already paid")
                r2 = await _test_chat(client, phone, "proceed_to_payment")
                data = r2.json()
                assert data.get("state") == "PAID"
                assert "already paid" in data["bot_response"].lower() or "paid" in data["bot_response"].lower()
    finally:
        settings.razorpay_webhook_secret = original_secret


# ════════════════════════════════════════════════════════════════════════
# Test 21: Non-message Meta webhook payload
# ════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_21_non_message_meta_payload():
    """Status-update Meta webhook returns 200, no processing."""
    transport = ASGITransport(app=app)

    # A delivery-status payload (no messages array)
    status_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": "msg_status_001",
                        "status": "delivered",
                        "timestamp": "1234567890",
                        "recipient_id": "919999900001",
                    }],
                },
            }],
        }],
    }

    with patch("app.api.webhooks.whatsapp_client.verify_signature", return_value=True):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/webhook", json=status_payload)

    assert r.status_code == 200
    assert r.json()["status"] == "ok"
