"""WhatsApp webhook endpoints.

GET  /webhook  — Meta verification challenge
POST /webhook  — Incoming message handler (canonical entry point)

All inbound messages (text, interactive buttons, interactive lists) flow
through the POST handler and are processed by the message_processor.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.services.message_processor import message_processor
from app.services.whatsapp import whatsapp_client
from app.utils.logger import logger

router = APIRouter(prefix="/webhook", tags=["WhatsApp"])


@router.get("", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Handle the one-time webhook verification request from Meta.

    Meta sends a GET request with hub.mode, hub.verify_token, and
    hub.challenge query parameters. We must return the challenge
    value if the verify token matches.
    """
    if not all([hub_mode, hub_token, hub_challenge]):
        raise HTTPException(
            status_code=400, detail="Missing verification parameters"
        )

    challenge = whatsapp_client.verify_webhook(
        hub_mode, hub_token, hub_challenge
    )
    if challenge:
        return challenge

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def handle_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Receive and process incoming WhatsApp messages.

    Supports text messages, interactive button replies, and
    interactive list replies.  Non-message payloads (delivery
    receipts, status updates) are silently acknowledged.

    Flow:
    1. Verify signature (if app secret is configured)
    2. Parse the incoming message from Meta's payload
    3. Skip non-message payloads and unsupported types
    4. Process through the canonical message processor
    5. Send the structured response back via WhatsApp
    """
    # Signature verification
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not whatsapp_client.verify_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse message
    payload = await request.json()
    message = whatsapp_client.parse_message(payload)

    if message is None:
        # Status update, delivery receipt, or unrecognised payload
        return {"status": "ok"}

    # Only process text and interactive messages
    if message.message_type not in ("text", "interactive"):
        logger.info(f"Ignoring message type: {message.message_type}")
        return {"status": "ok"}

    if not message.text:
        logger.info("Empty message text — ignoring")
        return {"status": "ok"}

    logger.info(
        f"Received message from {message.from_number}: {message.text[:100]}"
    )

    # Mark as read (blue ticks)
    await whatsapp_client.mark_as_read(message.message_id)

    # Process & respond
    try:
        result = await message_processor.process_message(
            db=session,
            phone_number=message.from_number,
            user_message=message.text,
            interactive_data=message.interactive_data,
        )

        # Build BotResponse for structured sending
        from app.closing_agent.response import BotResponse
        bot_response = BotResponse(
            message=result["bot_response"],
            state=result.get("state", ""),
            interactive=result.get("interactive"),
        )

        await whatsapp_client.send_structured_response(
            to=message.from_number,
            bot_response=bot_response,
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await whatsapp_client.send_message(
            to=message.from_number,
            text="I'm sorry, I encountered an error processing your message. Please try again.",
        )

    return {"status": "ok"}
