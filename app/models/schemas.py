"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── User ──────────────────────────────────────────────────────────────────


class UserBase(BaseModel):
    phone_number: str
    name: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Message ───────────────────────────────────────────────────────────────


class MessageBase(BaseModel):
    role: str
    content: str


class MessageResponse(MessageBase):
    id: int
    conversation_id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Conversation ──────────────────────────────────────────────────────────


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    started_at: datetime
    last_message_at: datetime
    is_active: bool
    messages: List[MessageResponse] = []

    model_config = {"from_attributes": True}


# ── Test Chat ─────────────────────────────────────────────────────────────


class TestChatRequest(BaseModel):
    """Request body for testing chat without WhatsApp integration."""

    phone_number: str = Field(
        ..., description="Simulated WhatsApp phone number", examples=["919876543210"]
    )
    message: str = Field(
        ..., description="User message text", examples=["Tell me about training programs"]
    )


class TestChatResponse(BaseModel):
    """Response body for test chat endpoint."""

    phone_number: str
    user_name: Optional[str]
    user_message: str
    bot_response: str
    conversation_id: int
    timestamp: datetime


# ── WhatsApp ──────────────────────────────────────────────────────────────


class WhatsAppMessage(BaseModel):
    """Parsed WhatsApp incoming message from webhook payload."""

    from_number: str
    message_id: str
    message_type: str
    text: Optional[str] = None
    timestamp: str


# ── Admin ─────────────────────────────────────────────────────────────────


class StatsResponse(BaseModel):
    """Database statistics."""

    total_users: int
    total_conversations: int
    total_messages: int
