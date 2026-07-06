"""WhatsApp Cloud API client for sending/receiving messages.

Handles:
- Webhook verification (GET challenge from Meta)
- Incoming message parsing
- Outgoing text messages
- Read receipts
- Request signature verification
"""

import hashlib
import hmac
from typing import Optional

import httpx

from app.config import settings
from app.models.schemas import WhatsAppMessage
from app.utils.logger import logger

WHATSAPP_API_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppClient:
    """Client for the Meta WhatsApp Cloud API."""

    def __init__(self) -> None:
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.access_token = settings.whatsapp_access_token
        self.verify_token = settings.whatsapp_verify_token
        self.app_secret = settings.whatsapp_app_secret
        self.api_url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"

    # ── Configuration Check ───────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """Return True if the minimum WhatsApp credentials are set."""
        return bool(self.phone_number_id and self.access_token)

    # ── Webhook Verification ──────────────────────────────────────────

    def verify_webhook(
        self, mode: str, token: str, challenge: str
    ) -> Optional[str]:
        """Verify a webhook subscription request from Meta.

        Returns the challenge string on success, or None on failure.
        """
        if mode == "subscribe" and token == self.verify_token:
            logger.info("Webhook verified successfully")
            return challenge
        logger.warning(f"Webhook verification failed: mode={mode}")
        return None

    # ── Signature Verification ────────────────────────────────────────

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the X-Hub-Signature-256 header from Meta."""
        if not self.app_secret or self.app_secret == "your_app_secret":
            if settings.app_env.lower() == "production":
                logger.error("App secret not configured or default in production — rejecting signature")
                return False
            logger.warning(
                "App secret not configured or default — skipping signature verification"
            )
            return True

        if not signature:
            return False

        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)

    # ── Message Parsing ───────────────────────────────────────────────

    def parse_message(self, body: dict) -> Optional[WhatsAppMessage]:
        """Extract a user message from an incoming webhook payload.

        Returns None for status updates or unsupported payloads.
        """
        try:
            entry = body.get("entry", [])
            if not entry:
                return None

            changes = entry[0].get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            msg_type = msg.get("type", "")
            text = None
            if msg_type == "text":
                text = msg.get("text", {}).get("body", "")

            return WhatsAppMessage(
                from_number=msg.get("from", ""),
                message_id=msg.get("id", ""),
                message_type=msg_type,
                text=text,
                timestamp=msg.get("timestamp", ""),
            )
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing WhatsApp message: {e}")
            return None

    # ── Sending Messages ──────────────────────────────────────────────

    async def send_message(self, to: str, text: str) -> bool:
        """Send a text message to a WhatsApp number.

        Returns True on success, False otherwise.
        """
        if not self.is_configured:
            logger.warning("WhatsApp not configured — message not sent")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url, headers=headers, json=payload, timeout=30.0
                )
                if response.status_code == 200:
                    logger.info(f"Message sent to {to}")
                    return True
                logger.error(
                    f"Failed to send message: {response.status_code} — {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return False

    # ── Read Receipts ─────────────────────────────────────────────────

    async def mark_as_read(self, message_id: str) -> bool:
        """Mark an incoming message as read (blue ticks)."""
        if not self.is_configured:
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url, headers=headers, json=payload, timeout=30.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Error marking message as read: {e}")
            return False


# Singleton instance
whatsapp_client = WhatsAppClient()
