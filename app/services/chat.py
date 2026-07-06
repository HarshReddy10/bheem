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


QUERY_REWRITE_PROMPT = """Given the conversation history and the latest user message, rewrite the user message into a standalone, context-complete search query that can be used to search a knowledge base.
Do NOT answer the question. Just output the rewritten search query.
If the latest message is a standalone query already and doesn't refer to prior history, output it exactly as-is.

CONVERSATION HISTORY:
{history_text}

LATEST USER MESSAGE:
{user_message}

STANDALONE SEARCH QUERY:"""


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
        # Conversation history (includes the current message which was already persisted)
        history = await get_recent_history(
            session, conversation_id, limit=settings.max_conversation_history
        )

        search_query = user_message

        # Only attempt to rewrite if there is prior history (history has > 1 messages)
        # and we are not using the MockProvider
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
            rewrite_prompt = QUERY_REWRITE_PROMPT.format(
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

        # RAG context using rewritten query
        context = rag_service.build_context(search_query)

        # System prompt
        name_instruction = (
            f"The user's name is {user.name}. "
            "Address them by name occasionally to keep the conversation personal."
        )
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            name_instruction=name_instruction,
            context=context or "(No relevant documents found in the knowledge base)",
        )

        # LLM generation (using original history)
        response = await self._llm.generate(
            messages=history,
            system_prompt=system_prompt,
        )

        return response


# Singleton instance
chat_service = ChatService()
