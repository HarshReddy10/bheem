"""FastAPI routes for the Closing Agent.

Only the Razorpay webhook lives here. The WhatsApp webhook has been
consolidated into the main /webhook endpoint.
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.closing_agent.payments import verify_webhook_signature
from app.closing_agent.response import BotResponse, after_payment_buttons
from app.closing_agent.session import get_or_create_session, update_session
from app.closing_agent.state_machine import State
from app.database.connection import get_session
from app.models.database import (
    ClosingSession,
    Conversation,
    Order,
    User,
    WebhookEvent,
)
from app.services.whatsapp import whatsapp_client
from app.utils.logger import logger

router = APIRouter(prefix="/closing-agent", tags=["closing_agent"])


@router.post("/razorpay-webhook")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """Receive and process Razorpay webhook events.

    Processing order (per Correction 4):
      1. Read raw body
      2. Verify HMAC signature → 401 on failure
      3. Parse JSON, extract external event ID
      4. Check WebhookEvent for deduplication → 200 if already processed
      5. Locate internal order by payment_link_id
      6. Update order (status, payment_id, paid_at)
      7. Update ClosingSession state
      8. Mark WebhookEvent as processed
      9. COMMIT database transaction
     10. Attempt WhatsApp confirmation (failure logged, not rolled back)
     11. Return 200
    """
    # Step 1: Read raw body
    body = await request.body()

    # Step 2: Verify signature
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_webhook_signature(body, signature):
        logger.warning("Razorpay webhook: invalid signature")
        return Response(status_code=401)

    # Step 3: Parse JSON
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Razorpay webhook: invalid JSON")
        return Response(status_code=400)

    event_type = data.get("event", "")
    # Build a unique external event ID from account_id + event id
    account_id = data.get("account_id", "")
    # Razorpay webhooks don't always have a top-level "id", so we
    # construct one from the payload for uniqueness
    payload_section = data.get("payload", {})
    payment_link_entity = (
        payload_section.get("payment_link", {}).get("entity", {})
    )
    payment_entity = (
        payload_section.get("payment", {}).get("entity", {})
    )

    # Use payment.entity.id + event type as the dedup key
    razorpay_payment_id = payment_entity.get("id", "")
    link_id = payment_link_entity.get("id", "")
    external_event_id = f"{account_id}:{event_type}:{link_id}:{razorpay_payment_id}"

    if not external_event_id.strip(":"):
        logger.warning("Razorpay webhook: could not construct event ID")
        return Response(status_code=200)

    # Step 4: Check deduplication
    existing_event = await db.execute(
        select(WebhookEvent).where(
            WebhookEvent.external_event_id == external_event_id
        )
    )
    existing = existing_event.scalar_one_or_none()
    if existing and existing.status == "processed":
        logger.info(f"Razorpay webhook: duplicate event {external_event_id} — skipping")
        return Response(status_code=200)

    # Record the event
    if existing is None:
        webhook_event = WebhookEvent(
            provider="razorpay",
            external_event_id=external_event_id,
            event_type=event_type,
            payload_json=body.decode("utf-8", errors="replace"),
            status="received",
        )
        db.add(webhook_event)
        await db.flush()
    else:
        webhook_event = existing

    # Only process payment events
    if event_type not in ("payment_link.paid", "payment_link.failed"):
        webhook_event.status = "processed"
        webhook_event.processed_at = datetime.utcnow()
        await db.commit()
        return Response(status_code=200)

    # Step 5: Locate order
    # Try razorpay_payment_link_id first, then fall back to payment_link_id
    order = None
    if link_id:
        result = await db.execute(
            select(Order).where(Order.razorpay_payment_link_id == link_id)
        )
        order = result.scalar_one_or_none()

        if order is None:
            # Fall back to old column name
            result = await db.execute(
                select(Order).where(Order.payment_link_id == link_id)
            )
            order = result.scalar_one_or_none()

    if order is None:
        logger.warning(f"Razorpay webhook: no order found for link {link_id}")
        webhook_event.status = "failed"
        webhook_event.processed_at = datetime.utcnow()
        await db.commit()
        return Response(status_code=200)

    # Step 6: Update order
    phone_number = None
    confirmation_response = None

    if event_type == "payment_link.paid":
        # Don't re-apply if already paid (idempotent)
        if order.status != "paid":
            order.status = "paid"
            order.razorpay_payment_id = razorpay_payment_id
            order.paid_at = datetime.utcnow()

    elif event_type == "payment_link.failed":
        if order.status not in ("paid",):  # don't downgrade paid → failed
            order.status = "failed"

    # Step 7: Update ClosingSession
    closing_result = await db.execute(
        select(ClosingSession).where(
            ClosingSession.conversation_id == order.conversation_id
        )
    )
    closing_session = closing_result.scalar_one_or_none()

    if closing_session:
        if event_type == "payment_link.paid":
            closing_session.state = State.PAID.value
            closing_session.updated_at = datetime.utcnow()
        elif event_type == "payment_link.failed":
            closing_session.state = State.AWAITING_PURCHASE_CONFIRMATION.value
            closing_session.updated_at = datetime.utcnow()

    # Resolve user phone number for WhatsApp notification
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == order.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if conversation:
        user_result = await db.execute(
            select(User).where(User.id == conversation.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            phone_number = user.phone_number

    # Build confirmation message
    if event_type == "payment_link.paid":
        amount_display = f"₹{order.amount / 100:,.0f}" if order.amount else "N/A"
        confirmation_response = BotResponse(
            message=(
                f"🎉 *Payment Successful!*\n\n"
                f"Course: {order.course_name}\n"
                f"Amount: {amount_display}\n"
                f"Order ID: {order.internal_order_id}\n"
                f"Payment ID: {order.razorpay_payment_id}\n\n"
                f"Thank you for your enrolment! We'll be in touch shortly "
                f"with your access details."
            ),
            state=State.PAID.value,
            interactive=after_payment_buttons(),
        )
    elif event_type == "payment_link.failed":
        confirmation_response = BotResponse(
            message=(
                "❌ It looks like your payment didn't go through.\n\n"
                "Please try again using the payment link, or contact "
                "our support team for assistance."
            ),
            state=State.AWAITING_PURCHASE_CONFIRMATION.value,
        )

    # Step 8: Mark webhook event as processed
    webhook_event.status = "processed"
    webhook_event.processed_at = datetime.utcnow()

    # Step 9: COMMIT database transaction
    await db.commit()

    # ── DB transaction boundary ──────────────────────────────────────
    # Everything below this point is best-effort. A failure here does
    # NOT roll back the committed payment record.

    # Step 10: Attempt WhatsApp confirmation
    if phone_number and confirmation_response:
        try:
            await whatsapp_client.send_structured_response(
                to=phone_number,
                bot_response=confirmation_response,
            )
            logger.info(
                f"Payment confirmation sent to {phone_number} "
                f"for order {order.internal_order_id}"
            )
        except Exception as e:
            logger.error(
                f"FAILED to send WhatsApp confirmation to {phone_number} "
                f"for order {order.internal_order_id}: {e}. "
                f"Payment is committed — manual retry required.",
                exc_info=True,
            )

    # Step 11: Return 200
    return Response(status_code=200)
