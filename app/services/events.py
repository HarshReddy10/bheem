"""Event Bus and Versioned Domain Events."""

import logging
import uuid
import httpx
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from app.company_config import company_config
from app.services.worker import background_worker

logger = logging.getLogger(__name__)

# ── Domain Event Schema ────────────────────────────────────────────────

class DomainEvent(BaseModel):
    """Standard versioned envelope for all domain events."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    event_version: str = "1.0"
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    tenant: str = "default"
    payload: Dict[str, Any]


# ── Event Bus ────────────────────────────────────────────────────────

class EventBus:
    """Central event bus for decoupling publishers and subscribers."""
    def __init__(self):
        # Maps event_type to list of subscriber callbacks
        self._subscribers: Dict[str, List[Callable[[DomainEvent], None]]] = {}
        # Subscribers listening to ALL events
        self._global_subscribers: List[Callable[[DomainEvent], None]] = []

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[DomainEvent], None]) -> None:
        """Subscribe to all events (useful for logging/webhooks)."""
        self._global_subscribers.append(handler)

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all relevant subscribers."""
        logger.info(f"Publishing event: {event.event_type} (ID: {event.event_id})")
        
        # Notify specific subscribers
        for handler in self._subscribers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Subscriber error for {event.event_type}: {e}", exc_info=True)
                
        # Notify global subscribers
        for handler in self._global_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Global subscriber error for {event.event_type}: {e}", exc_info=True)


# ── Subscribers ──────────────────────────────────────────────────────

def _post_to_webhook(url: str, event_data: dict) -> None:
    """Synchronous function to post to a webhook, usually run in a background worker."""
    try:
        # httpx Client for quick synchronous dispatch if running in a thread/process worker
        # But wait, background_worker expects an async function if we use asyncio!
        # Actually our AsyncioBackgroundWorker accepts async functions. 
        pass
    except Exception as e:
        logger.error(f"Failed to post event to webhook: {e}")

async def async_post_to_webhook(url: str, event_data: dict) -> None:
    """Async function to post to a webhook."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=event_data, timeout=10.0)
            response.raise_for_status()
            logger.debug(f"Successfully posted event to webhook: {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to post event to {url}: {e}")

def n8n_webhook_subscriber(event: DomainEvent) -> None:
    """Subscriber that forwards events to n8n."""
    # We must fetch the n8n webhook URL from config
    # Since config is dynamic, we can reach into company_config.raw_config
    n8n_config = company_config.raw_config.get("integrations", {}).get("n8n", {})
    webhook_url = n8n_config.get("webhook_url")
    
    if webhook_url:
        event_dict = event.model_dump()
        # Enqueue the async background task
        background_worker.enqueue(async_post_to_webhook, webhook_url, event_dict)
    else:
        # No webhook URL configured, drop the event silently
        pass


# Global singleton EventBus
event_bus = EventBus()

# Register standard subscribers
event_bus.subscribe_all(n8n_webhook_subscriber)
