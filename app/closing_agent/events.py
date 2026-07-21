"""Lead outcome tagging for the Closing Agent."""

from typing import Any, Dict, Optional

from app.closing_agent.state_machine import State
from app.services.events import DomainEvent, event_bus
from app.utils.logger import logger
from app.services.worker import background_worker
from pydantic_settings import BaseSettings
import httpx
from datetime import datetime

class N8nSettings(BaseSettings):
    n8n_lead_webhook_url: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

n8n_settings = N8nSettings()

async def notify_n8n(payload: dict) -> None:
    """Send an HTTP POST request to the n8n webhook URL."""
    if not n8n_settings.n8n_lead_webhook_url:
        logger.debug("N8N_LEAD_WEBHOOK_URL not configured, skipping n8n notification")
        return
        
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                n8n_settings.n8n_lead_webhook_url, 
                json=payload, 
                timeout=5.0
            )
            response.raise_for_status()
            logger.info("Successfully notified n8n of lead outcome")
    except Exception as e:
        logger.warning(f"Failed to notify n8n of lead outcome: {e}")

def determine_lead_outcome(current_state: State, previous_state: Optional[State] = None) -> str:
    """Deterministically tag the lead outcome based on terminal state."""
    
    if current_state == State.ORDER_COMPLETE or current_state == State.PAYMENT_SUCCESS:
        return "purchased"
    
    if current_state == State.CANCELLED or current_state == State.PAYMENT_FAILED:
        if previous_state in (State.CREATE_PAYMENT, State.WAITING_FOR_PAYMENT, State.PAYMENT_FAILED):
            return "abandoned_at_payment"
        elif previous_state == State.CONFIRM_PURCHASE:
            return "abandoned_at_checkout"
        elif previous_state in (State.PRODUCT_SELECTION, State.PRODUCT_DETAILS):
            return "abandoned_at_product_selection"
        else:
            return "abandoned_early"
            
    # Default catch-all
    return "unknown_outcome"

def emit_lead_outcome_event(
    phone_number: str, 
    current_state: State, 
    previous_state: Optional[State] = None,
    context_data: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[int] = None
) -> None:
    """Emit a single event with the lead outcome.
    
    Note: For a full MVP, we might later add a broader event taxonomy here
    (e.g., OrderStarted, PaymentCreated, ProductViewed) but for now we only
    emit the final LeadOutcome event.
    """
    outcome = determine_lead_outcome(current_state, previous_state)
    
    payload = {
        "phone_number": phone_number,
        "outcome": outcome,
        "final_state": current_state.value,
        "previous_state": previous_state.value if previous_state else None,
        "context": context_data or {}
    }
    
    event = DomainEvent(
        event_type="ClosingAgentLeadOutcome",
        payload=payload
    )
    
    event_bus.publish(event)
    logger.info(f"Emitted lead outcome '{outcome}' for {phone_number}")

    # Send payload to n8n
    n8n_payload = {
        "conversation_id": conversation_id,
        "phone_number": phone_number,
        "outcome": outcome,
        "product_id": context_data.get("product_id") if context_data else None,
        "timestamp": datetime.utcnow().isoformat()
    }
    background_worker.enqueue(notify_n8n, n8n_payload)
