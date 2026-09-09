import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://localhost/medikiosk")
APP_ENV = os.getenv("APP_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5175,http://127.0.0.1:5175").split(",")


def demo_enabled():
    return os.getenv("DEMO_MODE", "false").lower() == "true" and APP_ENV != "production"


SPEECH_PROVIDER = os.getenv("SPEECH_PROVIDER", "mock")
