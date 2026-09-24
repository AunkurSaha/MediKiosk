import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "")
APP_ENV = os.getenv("APP_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5175,http://127.0.0.1:5175").split(",")


def demo_enabled():
    return os.getenv("DEMO_MODE", "false").lower() == "true" and APP_ENV != "production"


SPEECH_PROVIDER = os.getenv("SPEECH_PROVIDER", "mock")
ABDM_ENV = os.getenv("ABDM_ENV", "mock")
ABDM_CLIENT_ID = os.getenv("ABDM_CLIENT_ID", "")
ABDM_CLIENT_SECRET = os.getenv("ABDM_CLIENT_SECRET", "")
HIS_ENDPOINT_URL = os.getenv("HIS_ENDPOINT_URL", "")
MAX_RAG_FOLLOWUPS_PER_INTERVIEW = int(os.getenv("MAX_RAG_FOLLOWUPS_PER_INTERVIEW", "2"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "mock")
RAG_INDEXING_EMBEDDING_PROVIDER = os.getenv("RAG_INDEXING_EMBEDDING_PROVIDER")
RAG_ACTIVE_EMBEDDING_PROVIDER = os.getenv("RAG_ACTIVE_EMBEDDING_PROVIDER")
RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b")
RAG_EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "10.0"))
RAG_EMBEDDING_BATCH_SIZE = int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "16"))
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.25"))
RAG_GENERATION_PROVIDER = os.getenv("RAG_GENERATION_PROVIDER", "template")
RAG_GENERATION_MODEL = os.getenv("RAG_GENERATION_MODEL", "meta/llama-3.2-11b-vision-instruct")
RAG_GENERATION_TIMEOUT_SECONDS = float(os.getenv("RAG_GENERATION_TIMEOUT_SECONDS", "20.0"))
RAG_GENERATION_TEMPERATURE = float(os.getenv("RAG_GENERATION_TEMPERATURE", "0.1"))
RAG_GENERATION_MAX_TOKENS = int(os.getenv("RAG_GENERATION_MAX_TOKENS", "100"))
PACKET_EXPIRY_MINUTES = int(os.getenv("PACKET_EXPIRY_MINUTES", "1440"))
HANDOFF_TOKEN_EXPIRY_MINUTES = int(os.getenv("HANDOFF_TOKEN_EXPIRY_MINUTES", "60"))


def configured_indexing_provider() -> str:
    """Resolve the refresh provider independently from the search provider."""
    return (
        os.getenv("RAG_INDEXING_EMBEDDING_PROVIDER")
        or os.getenv("RAG_EMBEDDING_PROVIDER")
        or "mock"
    ).strip().lower()


def configured_search_provider() -> str:
    """Resolve the active query provider without changing indexing selection."""
    return (
        os.getenv("RAG_ACTIVE_EMBEDDING_PROVIDER")
        or os.getenv("RAG_EMBEDDING_PROVIDER")
        or "mock"
    ).strip().lower()
