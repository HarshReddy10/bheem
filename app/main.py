"""FastAPI application — entry point with lifespan events."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.webhooks import router as webhook_router
from app.config import settings
from app.database.connection import close_db, init_db
from app.services.chat import chat_service
from app.services.rag import rag_service
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown lifecycle events."""
    # ── Startup ───────────────────────────────────────────────────────
    logger.info(f"Starting {settings.app_name}...")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"LLM Provider: {settings.llm_provider}")

    # Production security check
    if settings.app_env.lower() == "production":
        if not settings.whatsapp_app_secret or settings.whatsapp_app_secret == "your_app_secret":
            logger.error("CRITICAL CONFIGURATION ERROR: WHATSAPP_APP_SECRET is not configured or is a placeholder in production!")
            raise ValueError("WHATSAPP_APP_SECRET must be set to a secure, non-default value in production.")

    # Database
    await init_db()

    # RAG
    rag_service.initialize()
    if rag_service.is_initialized and rag_service.document_count == 0:
        logger.info("Auto-ingesting documents from knowledge base...")
        rag_service.ingest_documents()

    # Chat
    chat_service.initialize()

    logger.info(f"{settings.app_name} is ready! 🚀")
    if not settings.is_whatsapp_configured:
        logger.warning(
            "WhatsApp credentials not configured — "
            "use /api/test-chat for local testing"
        )

    yield

    # ── Shutdown ──────────────────────────────────────────────────────
    logger.info("Shutting down...")
    await close_db()
    logger.info("Goodbye!")


# ── Application ───────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description=(
        "WhatsApp AI Customer Support Chatbot "
        "for Placement & Training Services"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(webhook_router)


@app.get("/")
async def root():
    """Root endpoint — quick status and navigation links."""
    return {
        "name": settings.app_name,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "test_chat": "/api/test-chat",
    }
