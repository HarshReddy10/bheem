"""Session management for the Closing Agent.

Uses the ClosingSession ORM model for persistent state tracking instead
of encoding state into system messages.  This ensures that RAG questions
never erase the selected course or reset the closing journey.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.closing_agent.state_machine import State
from app.models.database import ClosingSession
from app.utils.logger import logger


async def get_or_create_session(
    db: AsyncSession, conversation_id: int
) -> ClosingSession:
    """Return the existing closing session or create one in GREETING state."""
    result = await db.execute(
        select(ClosingSession).where(
            ClosingSession.conversation_id == conversation_id
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        session = ClosingSession(
            conversation_id=conversation_id,
            state=State.GREETING.value,
        )
        db.add(session)
        await db.flush()
        logger.info(
            f"Created closing session for conversation {conversation_id}"
        )

    return session


async def update_session(
    db: AsyncSession,
    closing_session: ClosingSession,
    *,
    state: Optional[State] = None,
    course_id: Optional[str] = ...,  # sentinel: ... means "don't change"
    order_id: Optional[int] = ...,   # sentinel: ... means "don't change"
) -> ClosingSession:
    """Update closing session fields.

    Uses sentinel values (...) to distinguish between 'set to None' and
    'don't change'.  Pass ``course_id=None`` to clear the course, or
    omit it to leave it unchanged.
    """
    if state is not None:
        old_state = closing_session.state
        closing_session.state = state.value
        if old_state != state.value:
            logger.info(
                f"Session {closing_session.conversation_id}: "
                f"{old_state} → {state.value}"
            )

    if course_id is not ...:
        closing_session.selected_course_id = course_id

    if order_id is not ...:
        closing_session.active_order_id = order_id

    closing_session.updated_at = datetime.utcnow()
    await db.flush()
    return closing_session
