import pytest
from app.config import settings
from app.company_config import company_config
from app.database.connection import init_db, engine
from app.models.database import Base, ClosingSession, WebhookEvent, Order
from app.services.rag import rag_service
from app.services.chat import chat_service
from app.services.message_processor import message_processor

@pytest.fixture(autouse=True)
async def setup_test_services():
    """Autouse fixture to clean/initialize database and services for every test."""
    # Force mock provider for tests to keep them hermetic
    settings.llm_provider = "mock"

    # Initialize company config if not already done
    if not company_config.is_initialized:
        company_config.initialize()

    # Drop and recreate tables to ensure absolute clean state for every test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    if not rag_service.is_initialized:
        rag_service.initialize()
    chat_service.initialize()
    message_processor.initialize()
