"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Application
    app_name: str = "Bheem WhatsApp Chatbot"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/bheem.db"

    # WhatsApp Cloud API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = "bheem_verify_token_2024"
    whatsapp_app_secret: str = ""

    # LLM Provider
    llm_provider: str = "gemini"  # Options: mock, antigravity, gemini
    antigravity_api_key: str = ""
    antigravity_api_url: str = "https://api.antigravity.example.com/v1"
    antigravity_model: str = "antigravity-default"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # RAG Settings
    knowledge_base_dir: str = "./knowledge_base"
    chroma_persist_dir: str = "./data/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"
    rag_top_k: int = 5
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50

    # Conversation
    max_conversation_history: int = 20
    conversation_timeout_hours: int = 24

    # Logging
    log_level: str = "INFO"
    log_file: str = "./data/logs/bheem.log"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def is_whatsapp_configured(self) -> bool:
        """Check if WhatsApp credentials are set."""
        return bool(self.whatsapp_phone_number_id and self.whatsapp_access_token)

    @property
    def is_antigravity_configured(self) -> bool:
        """Check if Antigravity credentials are set."""
        return bool(self.antigravity_api_key)

    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini credentials are set."""
        return bool(self.gemini_api_key)



# Global settings singleton
settings = Settings()
