"""Stable API endpoints for automation and orchestration (n8n)."""

from fastapi import APIRouter, Depends, BackgroundTasks
from typing import Dict, Any

from app.database.connection import get_session
from app.services.knowledge import knowledge_service

router = APIRouter(prefix="/v1", tags=["Automation"])

# ── Queries (State & Status) ──────────────────────────────────────────

@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}

@router.get("/leads")
async def list_leads(session = Depends(get_session)) -> Any:
    """List all leads. Relies on internal CRUD logic."""
    from app.database.crud import get_all_users
    users = await get_all_users(session)
    return users

@router.get("/leads/{phone_number}/profile")
async def get_lead_profile(phone_number: str, session = Depends(get_session)) -> Dict[str, Any]:
    """Get a specific lead profile by phone number."""
    from app.database.crud import get_user_by_phone
    from app.services.lead_profile import load_profile
    
    user = await get_user_by_phone(session, phone_number)
    if not user:
        return {"error": "Lead not found"}
        
    profile = load_profile(user)
    return {
        "phone_number": user.phone_number,
        "name": user.name,
        "profile": profile.to_dict(),
        "is_complete": profile.is_complete
    }

@router.get("/knowledge/status")
async def knowledge_status() -> Dict[str, Any]:
    """Return metadata on the current knowledge repository."""
    from app.services.rag import rag_service
    return {
        "document_count": rag_service.document_count,
        "is_initialized": rag_service.is_initialized
    }


# ── Commands (Actions) ────────────────────────────────────────────────

@router.post("/knowledge/ingest")
async def ingest_knowledge(source_type: str, url: str, background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Trigger background ingestion of a website or resource."""
    # We use FastAPI's BackgroundTasks for simple async dispatch without blocking
    background_tasks.add_task(knowledge_service.trigger_ingestion, source_type, url)
    return {"message": f"Ingestion triggered for {url}. Completion event will be fired."}

@router.post("/knowledge/rebuild")
async def rebuild_knowledge(background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Trigger background rebuild of the RAG index."""
    background_tasks.add_task(knowledge_service.rebuild_index)
    return {"message": "Index rebuild triggered. Completion event will be fired."}
