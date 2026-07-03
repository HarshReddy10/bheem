"""Chat orchestrator — the brain of the chatbot.

Ties together:
- User management (lookup / create / name capture)
- Conversation management (active session, timeout)
- RAG retrieval (knowledge base context)
- LLM generation (system prompt + history + context)
- Message persistence (every exchange is logged)
"""

from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.crud import (
    add_message,
    get_or_create_conversation,
    get_or_create_user,
    get_recent_history,
    update_user_name,
)
from app.services.ai_service import LLMProvider, get_llm_provider
from app.services.rag import rag_service
from app.utils.logger import logger

# ── System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """You are a helpful, professional, and friendly AI customer support assistant \
for a Placement & Training Services company.

CRITICAL RULES:
1. ONLY answer questions using the provided context from the company's knowledge base.
2. If the information is NOT in the context, politely say: \
"I don't have that specific information in our records. \
I'd recommend contacting our team directly for the most accurate details."
3. NEVER make up or hallucinate information that is not in the context.
4. Be concise, clear, and helpful in your responses.
5. Use a warm, professional tone.
6. If the user greets you, greet them back warmly.

{name_instruction}

KNOWLEDGE BASE CONTEXT:
{context}

If the context above is empty, it means no relevant information was found. \
In that case, let the user know you don't have specific information about \
their query but offer to help with general questions about training programs, \
placements, fees, or contact information."""


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
            return (
                "Welcome to our Placement & Training Services! 👋\n\n"
                "I'm your AI assistant, here to help you with information "
                "about our training programs, placement services, and more.\n\n"
                "Before we begin, may I know your name?"
            )

        # User replied — treat it as their name
        name = user_message.strip().title()

        if len(name) <= 50 and len(name.split()) <= 4 and "?" not in name:
            await update_user_name(session, user, name)
            return (
                f"Nice to meet you, {name}! 😊\n\n"
                "How can I help you today? I can assist you with:\n"
                "• Training programs & courses\n"
                "• Placement process & opportunities\n"
                "• Fees & payment information\n"
                "• General inquiries\n\n"
                "Just ask me anything!"
            )

        # Doesn't look like a name — ask again gently
        return (
            "I'd love to address you by name! "
            "Could you please share just your name?"
        )

    # ── Normal Chat (with RAG) ────────────────────────────────────────

    async def _handle_chat(
        self,
        session: AsyncSession,
        user,
        conversation_id: int,
        user_message: str,
    ) -> str:
        """Run RAG retrieval + LLM generation for a normal chat turn."""
        # Conversation history
        history = await get_recent_history(
            session, conversation_id, limit=settings.max_conversation_history
        )

        # RAG context
        context = rag_service.build_context(user_message)

        # System prompt
        name_instruction = (
            f"The user's name is {user.name}. "
            "Address them by name occasionally to keep the conversation personal."
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            name_instruction=name_instruction,
            context=context or "(No relevant documents found in the knowledge base)",
        )

        # LLM generation
        response = await self._llm.generate(
            messages=history,
            system_prompt=system_prompt,
        )

        return response


# Singleton instance
chat_service = ChatService()
