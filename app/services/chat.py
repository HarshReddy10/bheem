"""Chat orchestrator — the brain of the chatbot.

Ties together:
- User management (lookup / create / name capture)
- Conversation management (active session, timeout)
- RAG retrieval (knowledge base context)
- LLM generation (system prompt + history + context)
- Message persistence (every exchange is logged)
- Lead intelligence (passive profile extraction)

All company-specific content (prompts, messages, branding) is loaded
from the company configuration layer — no business logic is hardcoded.
"""

from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.company_config import company_config
from app.config import settings
from app.database.crud import (
    add_message,
    get_or_create_conversation,
    get_or_create_user,
    get_recent_history,
    update_user_name,
)
from app.services.ai_service import LLMProvider, get_llm_provider
from app.services.lead_profile import (
    build_profile_prompt_section,
    load_profile,
    save_profile,
)
from app.services.rag import rag_service
from app.utils.logger import logger


class ChatService:
    """Orchestrates the end-to-end chat flow."""

    def __init__(self) -> None:
        self._llm: Optional[LLMProvider] = None

    def initialize(self) -> None:
        """Initialize with the configured LLM provider."""
        self._llm = get_llm_provider()
        logger.info("Chat service initialized")

    # ── Public Entry Point ────────────────────────────────────────────

    async def handle_message(
        self,
        session: AsyncSession,
        phone_number: str,
        user_message: str,
    ) -> Dict:
        """Process an incoming user message and return the bot's response.

        Returns a dict with: phone_number, user_name, user_message,
        bot_response, conversation_id.
        """
        if self._llm is None:
            self.initialize()

        # 1. Resolve user
        user = await get_or_create_user(session, phone_number)
        logger.info(
            f"Processing message from {phone_number} (user_id={user.id})"
        )

        # 2. Resolve conversation
        conversation = await get_or_create_conversation(session, user.id)

        # 3. Persist the incoming message
        await add_message(session, conversation.id, "user", user_message)

        # 4. Route: name capture vs. normal chat
        if user.name is None:
            response_text = await self._handle_name_flow(
                session, user, conversation.id, user_message
            )
        else:
            response_text = await self._handle_chat(
                session, user, conversation.id, user_message
            )

        # 5. Persist the bot response
        await add_message(session, conversation.id, "assistant", response_text)

        logger.info(f"Response to {phone_number}: {response_text[:100]}...")

        # 6. Dispatch background lead extraction
        from app.services.worker import background_worker
        from app.services.ai_service import MockProvider
        
        if not isinstance(self._llm, MockProvider):
            background_worker.enqueue(
                run_background_extraction, 
                user.id, 
                conversation.id, 
                self._llm
            )

        return {
            "phone_number": phone_number,
            "user_name": user.name,
            "user_message": user_message,
            "bot_response": response_text,
            "conversation_id": conversation.id,
        }

    # ── Name Capture Flow ─────────────────────────────────────────────

    async def _handle_name_flow(
        self,
        session: AsyncSession,
        user,
        conversation_id: int,
        user_message: str,
    ) -> str:
        """If we don't know the user's name, ask for it; then capture it."""
        history = await get_recent_history(session, conversation_id, limit=5)

        # Did we already ask?
        already_asked = any(
            any(
                phrase in msg.get("content", "").lower()
                for phrase in (
                    "may i know your name",
                    "what is your name",
                    "could you tell me your name",
                )
            )
            for msg in history
            if msg["role"] == "assistant"
        )

        if not already_asked:
            # First message — greet & ask
            return company_config.render_name_capture_message("welcome")

        # User replied — treat it as their name
        name = user_message.strip().title()

        if len(name) <= 50 and len(name.split()) <= 4 and "?" not in name:
            await update_user_name(session, user, name)
            return company_config.render_name_capture_message(
                "confirmation", name=name
            )

        # Doesn't look like a name — ask again gently
        return company_config.render_name_capture_message("retry")

    # ── Normal Chat (with RAG) ────────────────────────────────────────

    async def _handle_chat(
        self,
        session: AsyncSession,
        user,
        conversation_id: int,
        user_message: str,
    ) -> str:
        """Run RAG retrieval + LLM generation for a normal chat turn."""
        # Conversation history (includes the current message which was already persisted)
        history = await get_recent_history(
            session, conversation_id, limit=settings.max_conversation_history
        )

        search_query = user_message

        from app.services.ai_service import MockProvider
        prior_messages = history[:-1] if len(history) > 1 else []

        if prior_messages and not isinstance(self._llm, MockProvider):
            history_text = "\n".join(
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in prior_messages
            )
            rewrite_system_prompt = (
                "You are an AI assistant that rewrites user questions to be standalone "
                "queries for a RAG search database based on the conversation history."
            )
            rewrite_prompt = company_config.render_query_rewrite_prompt(
                history_text=history_text,
                user_message=user_message,
            )
            try:
                rewritten = await self._llm.generate(
                    messages=[{"role": "user", "content": rewrite_prompt}],
                    system_prompt=rewrite_system_prompt,
                    temperature=0.1,
                    max_tokens=100,
                )
                rewritten_clean = rewritten.strip().strip('"').strip("'")
                if rewritten_clean:
                    logger.info(f"RAG query rewritten: '{user_message}' -> '{rewritten_clean}'")
                    search_query = rewritten_clean
            except Exception as e:
                logger.error(f"Failed to rewrite query: {e}. Falling back to raw message.")

        profile = load_profile(user)

        # ── RAG context using rewritten query ─────────────────────────
        context = rag_service.build_context(search_query)

        # ── System prompt (assembled from config templates) ───────────
        name_instruction = (
            f"The user's name is {user.name}. "
            "Address them by name occasionally to keep the conversation personal."
        )
        lead_profile_section = build_profile_prompt_section(
            profile, user_name=user.name
        )
        system_prompt = company_config.render_system_prompt(
            name_instruction=name_instruction,
            lead_profile_section=lead_profile_section,
            context=context or "(No relevant documents found in the knowledge base)",
        )

        # LLM generation (using original history)
        response = await self._llm.generate(
            messages=history,
            system_prompt=system_prompt,
        )

        return response


# ── Background Intelligence ──────────────────────────────────────────

async def run_background_extraction(user_id: int, conversation_id: int, llm: LLMProvider):
    """Run lead extraction in the background using the latest context."""
    from app.database.connection import async_session_factory
    from app.database.crud import get_recent_history
    from app.lead_intelligence.extractor import extract_lead_info
    from app.lead_intelligence.merger import merge_extracted_fields
    from sqlalchemy import select
    from app.models.database import User

    async with async_session_factory() as session:
        # Load user directly to avoid circular import of get_user_by_id
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return

        profile = load_profile(user)
        missing = profile.missing_fields
        if not missing:
            return

        history = await get_recent_history(session, conversation_id, limit=6)
        history_text = "\n".join(
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in history
        )

        extracted = await extract_lead_info(llm, history_text, missing, conversation_id)
        if extracted:
            profile._data = merge_extracted_fields(profile._data, extracted)
            await save_profile(session, user, profile)
            
            # Emit Domain Events
            from app.services.events import event_bus, DomainEvent
            
            payload = {
                "phone_number": user.phone_number,
                "name": user.name,
                "profile": profile.to_dict()
            }
            
            event_bus.publish(DomainEvent(
                event_type="LeadUpdated",
                payload=payload
            ))
            
            if profile.is_complete:
                event_bus.publish(DomainEvent(
                    event_type="LeadQualified",
                    payload=payload
                ))


# Singleton instance
chat_service = ChatService()
