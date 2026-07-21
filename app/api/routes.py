"""API routes — health check, admin dashboard, and test-chat endpoint.

The /api/test-chat endpoint lets you interact with the chatbot without
needing WhatsApp credentials, making local development much easier.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.crud import (
    get_all_users,
    get_conversation_with_messages,
    get_stats,
    get_user_by_phone,
)
from app.services.lead_profile import load_profile
from app.models.schemas import (
    ConversationResponse,
    StatsResponse,
    TestChatRequest,
    TestChatResponse,
    UserResponse,
)
from app.services.message_processor import message_processor
from app.services.rag import rag_service
from app.utils.logger import logger

router = APIRouter(prefix="/api", tags=["API"])


# ── Health ────────────────────────────────────────────────────────────────


@router.get("/health")
async def health_check():
    """Application health check with RAG status."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "rag_initialized": rag_service.is_initialized,
        "documents_loaded": rag_service.document_count,
    }


# ── Test Chat (no WhatsApp needed) ────────────────────────────────────────


@router.post("/test-chat", response_model=TestChatResponse)
async def test_chat(
    request: TestChatRequest,
    session: AsyncSession = Depends(get_session),
):
    """Chat with the bot using a simulated phone number.

    This endpoint exercises the full pipeline (user management,
    closing agent, RAG, LLM) without requiring WhatsApp credentials.

    Optionally pass an ``interactive`` field to simulate a button press:
    ``{"type": "button_reply", "id": "proceed_to_payment", "title": "Proceed to Payment"}``
    """
    logger.info(f"Test chat from {request.phone_number}: {request.message}")

    result = await message_processor.process_message(
        db=session,
        phone_number=request.phone_number,
        user_message=request.message,
        interactive_data=request.interactive,
    )

    return TestChatResponse(
        phone_number=result["phone_number"],
        user_name=result["user_name"],
        user_message=result["user_message"],
        bot_response=result["bot_response"],
        conversation_id=result["conversation_id"],
        timestamp=datetime.utcnow(),
        state=result.get("state"),
        interactive=result.get("interactive"),
    )


# ── Admin: Users ──────────────────────────────────────────────────────────


@router.get("/admin/users", response_model=List[UserResponse])
async def list_users(session: AsyncSession = Depends(get_session)):
    """List all registered users (newest first)."""
    users = await get_all_users(session)
    return users


# ── Admin: Conversations ──────────────────────────────────────────────────


@router.get(
    "/admin/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Retrieve a conversation and all its messages."""
    conversation = await get_conversation_with_messages(
        session, conversation_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


# ── Admin: Stats ──────────────────────────────────────────────────────────


@router.get("/admin/stats", response_model=StatsResponse)
async def get_statistics(session: AsyncSession = Depends(get_session)):
    """Aggregate database statistics."""
    stats = await get_stats(session)
    return StatsResponse(**stats)


# ── Admin: Lead Profile ───────────────────────────────────────────────────


@router.get("/admin/users/{phone_number}/lead-profile")
async def get_lead_profile(
    phone_number: str,
    session: AsyncSession = Depends(get_session),
):
    """View the collected lead profile for a specific user."""
    from app.company_config import company_config

    user = await get_user_by_phone(session, phone_number)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    profile = load_profile(user)
    return {
        "phone_number": user.phone_number,
        "user_name": user.name,
        "lead_profile": profile.to_dict(),
        "is_complete": profile.is_complete,
        "missing_fields": list(profile.missing_fields.keys()),
        "configured_fields": company_config.lead_fields,
    }


# ── Admin: Document Ingestion ─────────────────────────────────────────────


@router.post("/admin/ingest")
async def ingest_documents():
    """Trigger document ingestion from the knowledge base directory."""
    if not rag_service.is_initialized:
        raise HTTPException(
            status_code=500, detail="RAG service not initialized"
        )

    count = rag_service.ingest_documents()
    return {
        "status": "success",
        "chunks_ingested": count,
        "total_documents": rag_service.document_count,
    }
