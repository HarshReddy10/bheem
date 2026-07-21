"""Razorpay integration for the Closing Agent.

Uses central app.config.settings for credentials. Provides:
- Payment link creation
- Webhook signature verification
"""

import hashlib
import hmac
import httpx
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.logger import logger

RAZORPAY_API_URL = "https://api.razorpay.com/v1"


async def create_payment_link(
    amount: int,
    currency: str,
    receipt_id: str,
    description: str = "Course Enrolment",
) -> Optional[Dict[str, Any]]:
    """Create a Razorpay payment link.

    Args:
        amount: Amount in smallest currency unit (paise for INR).
        currency: Currency code (e.g. 'INR').
        receipt_id: Unique internal reference for reconciliation.
        description: Human-readable description shown on payment page.

    Returns:
        Razorpay response dict with 'id', 'short_url', etc., or None on failure.
    """
    if not settings.is_razorpay_configured:
        logger.error("Razorpay credentials not configured")
        return None

    auth = (settings.razorpay_key_id, settings.razorpay_key_secret)
    payload = {
        "amount": amount,
        "currency": currency,
        "reference_id": receipt_id,
        "description": description,
        "reminder_enable": True,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RAZORPAY_API_URL}/payment_links",
                auth=auth,
                json=payload,
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Created Razorpay payment link: {data.get('id')}")
            return data
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Razorpay API error: {e.response.status_code} — {e.response.text}"
        )
        return None
    except Exception as e:
        logger.error(f"Error creating Razorpay payment link: {e}")
        return None


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Razorpay webhook HMAC-SHA256 signature.

    Uses the raw request body (bytes) for verification — not parsed JSON.

    Args:
        payload: Raw request body bytes.
        signature: Value of the X-Razorpay-Signature header.

    Returns:
        True if signature is valid.
    """
    secret = settings.razorpay_webhook_secret
    if not secret:
        logger.warning("Razorpay webhook secret not configured")
        return False

    if not signature:
        logger.warning("No Razorpay signature provided")
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)
