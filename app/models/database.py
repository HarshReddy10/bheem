"""SQLAlchemy ORM models for the application database."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy declarative base class."""

    pass


class User(Base):
    """A user identified by their WhatsApp phone number."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    lead_profile = Column(Text, nullable=True)  # JSON-serialized lead profile
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, phone={self.phone_number}, name={self.name})>"


class Conversation(Base):
    """A conversation session with a user.

    Conversations automatically expire after a configurable timeout,
    after which a new conversation is created.
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id={self.user_id})>"


class Message(Base):
    """A single message within a conversation.

    Roles: 'user' (incoming), 'assistant' (bot response), 'system' (internal).
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role})>"


class Order(Base):
    """An order created during the Closing Agent checkout flow.

    Lifecycle: created → payment_link_sent → paid | failed
    """

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    course_id = Column(String(100), nullable=True)
    course_name = Column(String(255), nullable=True)
    amount = Column(Integer, nullable=True)           # in paise
    currency = Column(String(10), default="INR")
    internal_order_id = Column(String(100), unique=True, nullable=True, index=True)
    # Keep old column name for migration compatibility
    payment_link_id = Column(String(255), nullable=True, index=True)
    razorpay_payment_link_id = Column(String(255), nullable=True, index=True)
    razorpay_payment_url = Column(String(1024), nullable=True)
    razorpay_payment_id = Column(String(255), nullable=True)
    status = Column(String(50), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    conversation = relationship("Conversation")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, internal={self.internal_order_id}, status={self.status})>"


class ClosingSession(Base):
    """Persisted closing-agent state for a conversation.

    Tracks the customer's position in the closing journey, the selected
    course, and the active order — ensuring RAG questions don't reset
    the purchase flow.
    """

    __tablename__ = "closing_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), unique=True, nullable=False)
    state = Column(String(50), default="GREETING", nullable=False)
    selected_course_id = Column(String(100), nullable=True)
    active_order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversation = relationship("Conversation")
    active_order = relationship("Order", foreign_keys=[active_order_id])

    def __repr__(self) -> str:
        return f"<ClosingSession(conv={self.conversation_id}, state={self.state})>"


class WebhookEvent(Base):
    """Record of an external webhook delivery for idempotency.

    Prevents duplicate processing of the same Razorpay (or other provider)
    webhook event.
    """

    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)            # e.g. "razorpay"
    external_event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=True)          # e.g. "payment_link.paid"
    payload_json = Column(Text, nullable=True)               # raw JSON for audit
    status = Column(String(50), default="received")          # received / processed / failed
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<WebhookEvent(provider={self.provider}, ext_id={self.external_event_id}, status={self.status})>"
