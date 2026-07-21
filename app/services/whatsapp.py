"""WhatsApp Cloud API client for sending/receiving messages.

Handles:
- Webhook verification (GET challenge from Meta)
- Incoming message parsing (text, interactive buttons, interactive lists)
- Outgoing text messages
- Outgoing interactive button messages
- Outgoing interactive list messages
- Template messages (stub for future CTA)
- Read receipts
- Request signature verification
- Structured response rendering (BotResponse → Meta API payload)
"""

import hashlib
import hmac
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.models.schemas import WhatsAppMessage
from app.utils.logger import logger

WHATSAPP_API_BASE = "https://graph.facebook.com/v20.0"


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

        Supports:
        - text messages
        - interactive.button_reply
        - interactive.list_reply

        Returns None for status updates, delivery receipts, or
        unsupported payloads (these are safely ignored).
        """
        try:
            entry = body.get("entry", [])
            if not entry:
                return None

            changes = entry[0].get("changes", [])
            if not changes:
                return None

            value = changes[0].get("value", {})

            # Explicitly ignore non-message payloads (status updates, etc.)
            if "statuses" in value and "messages" not in value:
                return None

            messages = value.get("messages", [])
            if not messages:
                return None

            msg = messages[0]
            msg_type = msg.get("type", "")
            text = None
            interactive_data = None

            if msg_type == "text":
                text = msg.get("text", {}).get("body", "")

            elif msg_type == "interactive":
                interactive = msg.get("interactive", {})
                interactive_type = interactive.get("type", "")

                if interactive_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    text = button_reply.get("id", "")
                    interactive_data = {
                        "type": "button_reply",
                        "id": button_reply.get("id", ""),
                        "title": button_reply.get("title", ""),
                    }

                elif interactive_type == "list_reply":
                    list_reply = interactive.get("list_reply", {})
                    text = list_reply.get("id", "")
                    interactive_data = {
                        "type": "list_reply",
                        "id": list_reply.get("id", ""),
                        "title": list_reply.get("title", ""),
                        "description": list_reply.get("description", ""),
                    }

            return WhatsAppMessage(
                from_number=msg.get("from", ""),
                message_id=msg.get("id", ""),
                message_type=msg_type,
                text=text,
                timestamp=msg.get("timestamp", ""),
                interactive_data=interactive_data,
            )
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing WhatsApp message: {e}")
            return None

    # ── Sending: Text ─────────────────────────────────────────────────

    async def send_text(self, to: str, text: str) -> bool:
        """Send a plain text message. Alias for send_message."""
        return await self.send_message(to, text)

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

    # ── Sending: Interactive Buttons ──────────────────────────────────

    async def send_reply_buttons(
        self, to: str, body_text: str, buttons: List[Dict[str, str]]
    ) -> bool:
        """Send an interactive reply-button message (max 3 buttons).

        Each button dict must have 'id' and 'title' keys.
        Title is truncated to 20 chars (WhatsApp limit).
        """
        if not self.is_configured:
            logger.warning("WhatsApp not configured — interactive message not sent")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        interactive_buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20],
                },
            }
            for btn in buttons[:3]
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": interactive_buttons},
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url, headers=headers, json=payload, timeout=30.0
                )
                if response.status_code == 200:
                    logger.info(f"Interactive buttons sent to {to}")
                    return True
                logger.error(
                    f"Failed to send interactive buttons: {response.status_code} — {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error sending interactive buttons: {e}")
            return False

    # ── Sending: Interactive List ─────────────────────────────────────

    async def send_list(
        self,
        to: str,
        body_text: str,
        button_label: str,
        sections: List[Dict[str, Any]],
    ) -> bool:
        """Send an interactive list message.

        sections format: [{"title": "...", "rows": [{"id": "...", "title": "...", "description": "..."}]}]
        """
        if not self.is_configured:
            logger.warning("WhatsApp not configured — list message not sent")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button": button_label[:20],
                    "sections": sections,
                },
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url, headers=headers, json=payload, timeout=30.0
                )
                if response.status_code == 200:
                    logger.info(f"List message sent to {to}")
                    return True
                logger.error(
                    f"Failed to send list message: {response.status_code} — {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error sending list message: {e}")
            return False

    # ── Sending: Template (stub for future CTA) ──────────────────────

    async def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en",
        components: Optional[List[Dict]] = None,
    ) -> bool:
        """Send a pre-approved template message.

        Ready for URL call-to-action buttons once the template is approved.
        """
        if not self.is_configured:
            logger.warning("WhatsApp not configured — template not sent")
            return False

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        template_payload: Dict[str, Any] = {
            "name": template_name,
            "language": {"code": language},
        }
        if components:
            template_payload["components"] = components

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template_payload,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url, headers=headers, json=payload, timeout=30.0
                )
                if response.status_code == 200:
                    logger.info(f"Template '{template_name}' sent to {to}")
                    return True
                logger.error(
                    f"Failed to send template: {response.status_code} — {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error sending template message: {e}")
            return False

    # ── Structured Response Renderer ──────────────────────────────────

    async def send_structured_response(self, to: str, bot_response) -> bool:
        """Convert a BotResponse into the correct Meta API payload and send.

        Routes to send_text, send_reply_buttons, or send_list based on
        the interactive field of the BotResponse.
        """
        interactive = bot_response.interactive

        if interactive is None:
            return await self.send_text(to, bot_response.message)

        resp_type = interactive.get("type", "")

        if resp_type == "buttons":
            buttons = interactive.get("buttons", [])
            if buttons:
                return await self.send_reply_buttons(
                    to, bot_response.message, buttons
                )
            return await self.send_text(to, bot_response.message)

        if resp_type == "list":
            sections = interactive.get("sections", [])
            button_label = interactive.get("button_label", "Options")
            if sections:
                return await self.send_list(
                    to, bot_response.message, button_label, sections
                )
            return await self.send_text(to, bot_response.message)

        # Unknown type — fall back to text
        return await self.send_text(to, bot_response.message)

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
