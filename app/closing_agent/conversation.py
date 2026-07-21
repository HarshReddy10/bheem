"""Conversation utilities for the Closing Agent.

The main message handling has moved to app.services.message_processor.
This module retains the RAG fallback utility used by the message processor.
"""

from app.services.rag import rag_service
from app.services.ai_service import get_llm_provider
from app.utils.logger import logger


async def rag_fallback(user_message: str, course_context: str = "") -> str:
    """Answer a question using the RAG pipeline.

    Args:
        user_message: The user's question.
        course_context: Optional course name to include in the query.

    Returns:
        The LLM-generated answer based on RAG context.
    """
    llm = get_llm_provider()
    search_query = f"{course_context}: {user_message}" if course_context else user_message
    context = rag_service.build_context(search_query)

    system_prompt = (
        "You are a helpful assistant for our educational platform. "
        "A user asked a question while exploring courses. "
        "Answer their question briefly using the provided knowledge base context. "
        "Only share information from the context — never invent details. "
        "Do not ask follow-up questions because the bot will automatically "
        "re-prompt them with their options.\n\n"
        f"Knowledge Base Context:\n{context if context else '(No relevant context found)'}"
    )

    return await llm.generate(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=300,
    )
