"""Canonical message processing service.

Single entry point for all inbound messages — WhatsApp webhook and
/api/test-chat.  Replaces the dual chat_service + closing_agent
conversation handler.

Intent-routing priority (5 tiers):
  1. Interactive button/list action ID (deterministic)
  2. Current persisted closing state (context-aware)
  3. Deterministic keyword rules
  4. Course name and alias matching
  5. LLM-assisted classification (only if still ambiguous)
"""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.closing_agent.catalog import (
    Course,
    get_course_by_id,
    get_courses,
    match_course,
)
from app.closing_agent.payments import create_payment_link
from app.closing_agent.response import (
    BotResponse,
    after_payment_buttons,
    after_rag_buttons,
    course_list,
    course_selected_buttons,
    greeting_buttons,
)
from app.closing_agent.session import get_or_create_session, update_session
from app.closing_agent.state_machine import State
from app.company_config import company_config
from app.config import settings
from app.database.crud import (
    add_message,
    get_or_create_conversation,
    get_or_create_user,
    get_recent_history,
    update_user_name,
)
from app.models.database import Order
from app.services.ai_service import LLMProvider, get_llm_provider
from app.services.rag import rag_service
from app.utils.logger import logger


# ── Keyword patterns ───────────────────────────────────────────────────

_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|greetings|start|good\s*(morning|afternoon|evening))[\s!.]*$",
    re.IGNORECASE,
)

_CONFIRMATION_PATTERNS = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|proceed|confirm|buy|enroll|enrol|i\s*want\s*to\s*(buy|enroll|enrol|pay)|let'?s\s*do\s*it).*$",
    re.IGNORECASE,
)

_REJECTION_PATTERNS = re.compile(
    r"^(no|nope|not\s*now|later|cancel|maybe\s*later|nah|no\s*thanks)[\s!.]*$",
    re.IGNORECASE,
)

# Interactive button IDs that are deterministically routed
_ACTION_IDS = {
    "view_courses", "other_courses",
    "ask_question",
    "talk_to_advisor",
    "proceed_to_payment",
    "not_now",
    "view_receipt",
    "contact_support",
}


class MessageProcessor:
    """Unified message processing service."""

    def __init__(self) -> None:
        self._llm: Optional[LLMProvider] = None

    def initialize(self) -> None:
        self._llm = get_llm_provider()
        logger.info("Message processor initialized")

    # ── Public Entry Point ────────────────────────────────────────────

    async def process_message(
        self,
        db: AsyncSession,
        phone_number: str,
        user_message: str,
        interactive_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process an inbound message and return the bot's response.

        Returns a dict with: phone_number, user_name, user_message,
        bot_response, conversation_id, state, interactive.
        """
        if self._llm is None:
            self.initialize()

        # 1. Resolve user
        user = await get_or_create_user(db, phone_number)

        # 2. Resolve conversation
        conversation = await get_or_create_conversation(db, user.id)

        # 3. Load/create closing session
        closing = await get_or_create_session(db, conversation.id)

        # 4. Persist inbound message
        display_text = user_message
        if interactive_data:
            display_text = interactive_data.get("title", user_message)
        await add_message(db, conversation.id, "user", display_text)

        # 5. Handle name capture first (if user has no name yet)
        if user.name is None:
            response = await self._handle_name_flow(
                db, user, conversation.id, user_message
            )
        else:
            # 6. Route through closing agent
            response = await self._route_message(
                db, user, conversation, closing,
                user_message, interactive_data,
            )

        # 7. Persist assistant response
        await add_message(db, conversation.id, "assistant", response.message)
        await db.commit()

        return {
            "phone_number": phone_number,
            "user_name": user.name,
            "user_message": user_message,
            "bot_response": response.message,
            "conversation_id": conversation.id,
            "state": response.state,
            "interactive": response.interactive,
        }

    # ── Name Capture ─────────────────────────────────────────────────

    async def _handle_name_flow(
        self, db, user, conversation_id: int, user_message: str
    ) -> BotResponse:
        """Handle name capture before entering the closing journey."""
        history = await get_recent_history(db, conversation_id, limit=5)
        already_asked = any(
            any(
                phrase in msg.get("content", "").lower()
                for phrase in ("may i know your name", "what is your name",
                               "could you tell me your name")
            )
            for msg in history
            if msg["role"] == "assistant"
        )

        if not already_asked:
            return BotResponse(
                message=company_config.render_name_capture_message("welcome"),
                state=State.GREETING.value,
            )

        name = user_message.strip().title()
        if len(name) <= 50 and len(name.split()) <= 4 and "?" not in name:
            await update_user_name(db, user, name)
            msg = company_config.render_name_capture_message(
                "confirmation", name=name
            )
            return BotResponse(
                message=msg,
                state=State.GREETING.value,
                interactive=greeting_buttons(),
            )

        return BotResponse(
            message=company_config.render_name_capture_message("retry"),
            state=State.GREETING.value,
        )

    # ── Intent Router (5-tier priority) ──────────────────────────────

    async def _route_message(
        self,
        db: AsyncSession,
        user,
        conversation,
        closing,
        user_message: str,
        interactive_data: Optional[Dict[str, Any]],
    ) -> BotResponse:
        """Classify intent and route to the appropriate handler."""
        current_state = State(closing.state)
        text = user_message.strip()

        # ── Tier 1: Interactive action ID ─────────────────────────────
        if interactive_data and interactive_data.get("id"):
            action_id = interactive_data["id"]
            return await self._handle_action_id(
                db, user, conversation, closing, current_state, action_id
            )

        # For non-interactive messages, also check if the text matches
        # a known action ID (e.g. from test-chat simulating a button press)
        if text in _ACTION_IDS:
            return await self._handle_action_id(
                db, user, conversation, closing, current_state, text
            )

        # ── Tier 2: State-aware routing ───────────────────────────────
        if current_state == State.AWAITING_PURCHASE_CONFIRMATION:
            if _CONFIRMATION_PATTERNS.match(text):
                return await self._handle_purchase_confirmation(
                    db, user, conversation, closing
                )
            if _REJECTION_PATTERNS.match(text):
                return await self._handle_rejection(db, closing)

        if current_state == State.PAYMENT_PENDING:
            if _CONFIRMATION_PATTERNS.match(text):
                # Idempotent: re-send existing payment link
                return await self._handle_purchase_confirmation(
                    db, user, conversation, closing
                )

        # ── Tier 3: Deterministic keywords ────────────────────────────
        if _GREETING_PATTERNS.match(text):
            return await self._handle_greeting(db, closing)

        if _CONFIRMATION_PATTERNS.match(text) and closing.selected_course_id:
            return await self._handle_purchase_confirmation(
                db, user, conversation, closing
            )

        # ── Tier 4: Course name/alias matching ────────────────────────
        course = match_course(text)
        if course:
            return await self._handle_course_selection(
                db, closing, course
            )

        # ── Tier 5: LLM classification / RAG fallback ────────────────
        # For any other message, treat as a course question → RAG
        return await self._handle_course_question(
            db, user, conversation, closing, text
        )

    # ── Action ID Handler ────────────────────────────────────────────

    async def _handle_action_id(
        self, db, user, conversation, closing, current_state, action_id: str
    ) -> BotResponse:
        """Route deterministically by interactive button/list ID."""

        if action_id == "view_courses" or action_id == "other_courses":
            courses = get_courses()
            if not courses:
                return BotResponse(
                    message="Sorry, no courses are available right now.",
                    state=closing.state,
                )
            await update_session(db, closing, state=State.DISCOVERING_COURSE)
            if len(courses) <= 3:
                buttons = [{"id": c.id, "title": c.name[:20]} for c in courses]
                return BotResponse(
                    message="Here are our available courses. Select one to learn more:",
                    state=State.DISCOVERING_COURSE.value,
                    interactive={"type": "buttons", "buttons": buttons},
                )
            return BotResponse(
                message="Here are our available courses. Select one to learn more:",
                state=State.DISCOVERING_COURSE.value,
                interactive=course_list(courses),
            )

        if action_id == "ask_question":
            await update_session(db, closing, state=State.ANSWERING_QUESTIONS)
            course_hint = ""
            if closing.selected_course_id:
                c = get_course_by_id(closing.selected_course_id)
                if c:
                    course_hint = f" about {c.name}"
            return BotResponse(
                message=f"Sure! What would you like to know{course_hint}? "
                        "I can help with syllabus, fees, duration, placements, "
                        "eligibility, and more.",
                state=State.ANSWERING_QUESTIONS.value,
            )

        if action_id == "talk_to_advisor":
            return BotResponse(
                message=company_config.escalation_message,
                state=closing.state,
            )

        if action_id == "proceed_to_payment":
            return await self._handle_purchase_confirmation(
                db, user, conversation, closing
            )

        if action_id == "not_now":
            return await self._handle_rejection(db, closing)

        if action_id == "view_receipt":
            return await self._handle_view_receipt(db, closing)

        if action_id == "contact_support":
            return BotResponse(
                message=f"You can reach our team at:\n"
                        f"📧 {company_config.company_contact_email}\n"
                        f"📞 {company_config.company_contact_phone}\n\n"
                        f"Or visit {company_config.company_website}",
                state=closing.state,
            )

        # Check if action_id is a course ID (from list selection)
        course = get_course_by_id(action_id)
        if course:
            return await self._handle_course_selection(db, closing, course)

        # Unknown action — fallback
        return BotResponse(
            message="I didn't quite catch that. How can I help you?",
            state=closing.state,
            interactive=greeting_buttons(),
        )

    # ── Greeting ─────────────────────────────────────────────────────

    async def _handle_greeting(self, db, closing) -> BotResponse:
        await update_session(
            db, closing, state=State.GREETING,
            course_id=None, order_id=None,
        )
        name = ""
        try:
            from app.models.database import Conversation, User
            result = await db.execute(
                select(User).join(Conversation).where(
                    Conversation.id == closing.conversation_id
                )
            )
            u = result.scalar_one_or_none()
            if u and u.name:
                name = u.name
        except Exception:
            pass

        greeting_name = f", {name}" if name else ""
        return BotResponse(
            message=f"Hello{greeting_name}! {company_config.welcome_emoji}\n\n"
                    f"Welcome to {company_config.company_name}. "
                    f"I'm here to help you find the right {company_config.offering_term}.\n\n"
                    "How would you like to get started?",
            state=State.GREETING.value,
            interactive=greeting_buttons(),
        )

    # ── Course Selection ─────────────────────────────────────────────

    async def _handle_course_selection(
        self, db, closing, course: Course
    ) -> BotResponse:
        await update_session(
            db, closing,
            state=State.AWAITING_PURCHASE_CONFIRMATION,
            course_id=course.id,
        )
        return BotResponse(
            message=f"{course.to_summary()}\n\n"
                    "Would you like to proceed with enrolment?",
            state=State.AWAITING_PURCHASE_CONFIRMATION.value,
            interactive=course_selected_buttons(),
        )

    # ── Course Question (RAG) ────────────────────────────────────────

    async def _handle_course_question(
        self, db, user, conversation, closing, text: str
    ) -> BotResponse:
        # Include selected course in RAG query for better retrieval
        search_query = text
        selected_course = None
        if closing.selected_course_id:
            selected_course = get_course_by_id(closing.selected_course_id)
            if selected_course:
                search_query = f"{selected_course.name}: {text}"

        # RAG retrieval
        context = rag_service.build_context(search_query)

        # Build system prompt
        system_prompt = (
            f"You are {company_config.bot_persona} for {company_config.company_name}. "
            "Answer the user's question using the knowledge base context below. "
            "Be helpful and conversational. Only share information from the context. "
            "If the answer isn't in the context, say so honestly.\n\n"
        )
        if user.name:
            system_prompt += f"The user's name is {user.name}. Address them by name occasionally.\n\n"
        system_prompt += f"KNOWLEDGE BASE CONTEXT:\n{context or '(No relevant documents found)'}"

        # Get conversation history
        history = await get_recent_history(
            db, conversation.id, limit=settings.max_conversation_history
        )

        # LLM generation
        answer = await self._llm.generate(
            messages=history,
            system_prompt=system_prompt,
        )

        # Update state
        await update_session(db, closing, state=State.ANSWERING_QUESTIONS)

        # Append purchase continuation if course is selected and not in
        # payment/paid state
        current_state = State(closing.state)
        if (
            selected_course
            and current_state not in (State.PAYMENT_PENDING, State.PAID)
        ):
            answer += (
                f"\n\nWould you like to proceed with enrolment in "
                f"{selected_course.name}?"
            )
            return BotResponse(
                message=answer,
                state=State.ANSWERING_QUESTIONS.value,
                interactive=after_rag_buttons(),
            )

        return BotResponse(
            message=answer,
            state=State.ANSWERING_QUESTIONS.value,
            interactive=greeting_buttons() if not closing.selected_course_id else None,
        )

    # ── Purchase Confirmation (idempotent) ───────────────────────────

    async def _handle_purchase_confirmation(
        self, db, user, conversation, closing
    ) -> BotResponse:
        """Create an order and payment link, or reuse existing one."""

        # Check for selected course
        if not closing.selected_course_id:
            courses = get_courses()
            if len(courses) <= 3:
                buttons = [{"id": c.id, "title": c.name[:20]} for c in courses]
                return BotResponse(
                    message="I'd be happy to help you enrol! Which course are you interested in?",
                    state=State.DISCOVERING_COURSE.value,
                    interactive={"type": "buttons", "buttons": buttons},
                )
            return BotResponse(
                message="I'd be happy to help you enrol! Which course are you interested in?",
                state=State.DISCOVERING_COURSE.value,
                interactive=course_list(courses),
            )

        course = get_course_by_id(closing.selected_course_id)
        if not course:
            return BotResponse(
                message="Sorry, that course is no longer available.",
                state=closing.state,
            )

        # ── Duplicate order prevention ────────────────────────────────
        if closing.active_order_id:
            existing_order = await db.get(Order, closing.active_order_id)
            if existing_order and existing_order.status in ("created", "payment_link_sent"):
                # Reuse existing payment link
                if existing_order.razorpay_payment_url:
                    await update_session(
                        db, closing, state=State.PAYMENT_PENDING
                    )
                    return BotResponse(
                        message=f"Your payment link for *{course.name}* "
                                f"({course.price_display}) is ready:\n\n"
                                f"{existing_order.razorpay_payment_url}\n\n"
                                "Please complete the payment to confirm your enrolment.",
                        state=State.PAYMENT_PENDING.value,
                    )
                # Order exists but no payment link yet — continue to create one
                order = existing_order
            elif existing_order and existing_order.status == "paid":
                return BotResponse(
                    message=f"You've already paid for *{course.name}*! "
                            f"Your order ID is {existing_order.internal_order_id}.",
                    state=State.PAID.value,
                    interactive=after_payment_buttons(),
                )
            else:
                order = None
        else:
            order = None

        # ── Create new order ─────────────────────────────────────────
        if order is None:
            internal_order_id = f"ORD-{uuid.uuid4().hex[:12].upper()}"
            order = Order(
                user_id=user.id,
                conversation_id=conversation.id,
                course_id=course.id,
                course_name=course.name,
                amount=course.price,
                currency=course.currency,
                internal_order_id=internal_order_id,
                status="created",
            )
            db.add(order)
            await db.flush()  # get order.id

            await update_session(
                db, closing, state=State.PAYMENT_PENDING, order_id=order.id
            )

        # ── Create Razorpay payment link ─────────────────────────────
        payment_data = await create_payment_link(
            amount=course.price,
            currency=course.currency,
            receipt_id=order.internal_order_id,
            description=f"Enrolment: {course.name}",
        )

        if payment_data and payment_data.get("short_url"):
            order.razorpay_payment_link_id = payment_data["id"]
            order.razorpay_payment_url = payment_data["short_url"]
            order.status = "payment_link_sent"
            await db.flush()

            await update_session(db, closing, state=State.PAYMENT_PENDING)

            return BotResponse(
                message=f"Great! Here's your payment link for *{course.name}* "
                        f"({course.price_display}):\n\n"
                        f"{payment_data['short_url']}\n\n"
                        "Please complete the payment to confirm your enrolment.",
                state=State.PAYMENT_PENDING.value,
            )
        else:
            return BotResponse(
                message="I'm sorry, I couldn't generate a payment link right now. "
                        "Please try again in a moment or contact our team.",
                state=closing.state,
            )

    # ── Rejection ────────────────────────────────────────────────────

    async def _handle_rejection(self, db, closing) -> BotResponse:
        # Keep the selected course but go back to questions
        await update_session(db, closing, state=State.ANSWERING_QUESTIONS)
        return BotResponse(
            message="No problem! Take your time. I'm here whenever you're ready.\n\n"
                    "Feel free to ask any questions about our courses.",
            state=State.ANSWERING_QUESTIONS.value,
            interactive=greeting_buttons(),
        )

    # ── View Receipt ─────────────────────────────────────────────────

    async def _handle_view_receipt(self, db, closing) -> BotResponse:
        if not closing.active_order_id:
            return BotResponse(
                message="I don't have a receipt to show right now.",
                state=closing.state,
            )
        order = await db.get(Order, closing.active_order_id)
        if not order or order.status != "paid":
            return BotResponse(
                message="Your order hasn't been completed yet.",
                state=closing.state,
            )
        amount_display = f"₹{order.amount / 100:,.0f}" if order.amount else "N/A"
        return BotResponse(
            message=f"🧾 *Payment Receipt*\n\n"
                    f"Course: {order.course_name}\n"
                    f"Amount: {amount_display}\n"
                    f"Order ID: {order.internal_order_id}\n"
                    f"Payment ID: {order.razorpay_payment_id or 'N/A'}\n"
                    f"Paid at: {order.paid_at.strftime('%d %b %Y, %H:%M') if order.paid_at else 'N/A'}\n\n"
                    "Thank you for your enrolment!",
            state=State.PAID.value,
        )


# Singleton
message_processor = MessageProcessor()
