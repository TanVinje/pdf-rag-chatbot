import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./chroma_db")
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.15"))
    TOP_K: int = int(os.getenv("TOP_K", "6"))
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Admin secret for /ingest endpoint (set a strong random string)
    ADMIN_SECRET: str = os.getenv("ADMIN_SECRET", "nexzoneo-admin-2026")

    USE_LOCAL_EMBEDDINGS: bool = os.getenv("USE_LOCAL_EMBEDDINGS", "true").lower() in ("true", "1", "yes")

    @property
    def use_openai_embeddings(self) -> bool:
        """Use OpenAI embeddings only if explicitly enabled (local is default)."""
        if self.USE_LOCAL_EMBEDDINGS:
            return False
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY.strip())


settings = Settings()
