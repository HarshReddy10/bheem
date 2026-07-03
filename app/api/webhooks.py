"""WhatsApp webhook endpoints.

GET  /webhook  — Meta verification challenge
POST /webhook  — Incoming message handler
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.services.chat import chat_service
from app.services.whatsapp import whatsapp_client
from app.utils.logger import logger

router = APIRouter(prefix="/webhook", tags=["WhatsApp"])


@router.get("")
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
        return int(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def handle_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Receive and process incoming WhatsApp messages.

    Flow:
    1. Verify signature (if app secret is configured)
    2. Parse the incoming message from Meta's payload
    3. Skip non-text messages
    4. Process through the chat service
    5. Send the response back via WhatsApp
    """
    # Signature verification
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if whatsapp_client.app_secret and not whatsapp_client.verify_signature(
        body, signature
    ):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse message
    payload = await request.json()
    message = whatsapp_client.parse_message(payload)

    if message is None:
        # Status update or unrecognised payload — acknowledge silently
        return {"status": "ok"}

    if message.message_type != "text" or not message.text:
        logger.info(f"Ignoring non-text message type: {message.message_type}")
        return {"status": "ok"}

    logger.info(
        f"Received message from {message.from_number}: {message.text[:100]}"
    )

    # Mark as read (blue ticks)
    await whatsapp_client.mark_as_read(message.message_id)

    # Process & respond
    try:
        result = await chat_service.handle_message(
            session=session,
            phone_number=message.from_number,
            user_message=message.text,
        )

        await whatsapp_client.send_message(
            to=message.from_number,
            text=result["bot_response"],
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await whatsapp_client.send_message(
            to=message.from_number,
            text="I'm sorry, I encountered an error processing your message. Please try again.",
        )

    return {"status": "ok"}
