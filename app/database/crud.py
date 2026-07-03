"""CRUD operations for Users, Conversations, and Messages."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.database import Conversation, Message, User
from app.utils.logger import logger


# ── User Operations ───────────────────────────────────────────────────────


async def get_user_by_phone(
    session: AsyncSession, phone_number: str
) -> Optional[User]:
    """Look up a user by their WhatsApp phone number."""
    result = await session.execute(
        select(User).where(User.phone_number == phone_number)
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, phone_number: str, name: Optional[str] = None
) -> User:
    """Create a new user record."""
    user = User(phone_number=phone_number, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info(f"Created user: {phone_number}")
    return user


async def update_user_name(
    session: AsyncSession, user: User, name: str
) -> User:
    """Set or update a user's display name."""
    user.name = name
    user.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(user)
    logger.info(f"Updated user name: {user.phone_number} -> {name}")
    return user


async def get_or_create_user(
    session: AsyncSession, phone_number: str
) -> User:
    """Return an existing user or create a new one."""
    user = await get_user_by_phone(session, phone_number)
    if user is None:
        user = await create_user(session, phone_number)
    return user


async def get_all_users(session: AsyncSession) -> List[User]:
    """Return all users, newest first."""
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    return list(result.scalars().all())


# ── Conversation Operations ──────────────────────────────────────────────


async def get_active_conversation(
    session: AsyncSession, user_id: int
) -> Optional[Conversation]:
    """Return the user's most recent active conversation, if not timed out."""
    timeout = datetime.utcnow() - timedelta(
        hours=settings.conversation_timeout_hours
    )
    result = await session.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.is_active == True,  # noqa: E712
            Conversation.last_message_at >= timeout,
        )
        .order_by(Conversation.last_message_at.desc())
    )
    return result.scalar_one_or_none()


async def create_conversation(
    session: AsyncSession, user_id: int
) -> Conversation:
    """Start a new conversation for a user."""
    conversation = Conversation(user_id=user_id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    logger.info(f"Created conversation {conversation.id} for user {user_id}")
    return conversation


async def get_or_create_conversation(
    session: AsyncSession, user_id: int
) -> Conversation:
    """Return an active conversation or start a new one."""
    conversation = await get_active_conversation(session, user_id)
    if conversation is None:
        conversation = await create_conversation(session, user_id)
    return conversation


async def get_conversation_with_messages(
    session: AsyncSession, conversation_id: int
) -> Optional[Conversation]:
    """Load a conversation together with all of its messages."""
    result = await session.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


# ── Message Operations ────────────────────────────────────────────────────


async def add_message(
    session: AsyncSession,
    conversation_id: int,
    role: str,
    content: str,
) -> Message:
    """Append a message to a conversation and update its timestamp."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    session.add(message)

    # Touch conversation timestamp
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        conversation.last_message_at = datetime.utcnow()

    await session.commit()
    await session.refresh(message)
    return message


async def get_conversation_history(
    session: AsyncSession,
    conversation_id: int,
    limit: Optional[int] = None,
) -> List[Message]:
    """Return messages for a conversation, ordered chronologically."""
    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
    )
    if limit:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_recent_history(
    session: AsyncSession,
    conversation_id: int,
    limit: int = 20,
) -> List[Dict[str, str]]:
    """Return recent messages formatted for LLM context window.

    Returns a list of ``{"role": ..., "content": ...}`` dicts, truncated
    to the most recent *limit* messages.
    """
    messages = await get_conversation_history(session, conversation_id)
    recent = messages[-limit:] if len(messages) > limit else messages
    return [{"role": msg.role, "content": msg.content} for msg in recent]


# ── Stats ─────────────────────────────────────────────────────────────────


async def get_stats(session: AsyncSession) -> Dict[str, int]:
    """Return aggregate counts for admin dashboard."""
    users = await session.execute(select(func.count(User.id)))
    conversations = await session.execute(select(func.count(Conversation.id)))
    messages = await session.execute(select(func.count(Message.id)))
    return {
        "total_users": users.scalar() or 0,
        "total_conversations": conversations.scalar() or 0,
        "total_messages": messages.scalar() or 0,
    }
