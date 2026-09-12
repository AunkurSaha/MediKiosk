import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

os.environ["APP_ENV"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite://")
# Normal CI must never inherit live credentials/provider selection from the local .env.
os.environ["CLINICAL_NORMALIZATION_PROVIDER"] = "mock"
os.environ["CLINICAL_NORMALIZATION_TIMEOUT_SECONDS"] = "0.5"
os.environ["NVIDIA_API_KEY"] = ""
os.environ["SPEECH_PROVIDER"] = "mock"
os.environ["OCR_PROVIDER"] = "mock"
os.environ["TRANSLATION_PROVIDER"] = "mock"
os.environ["RAG_EMBEDDING_PROVIDER"] = "mock"
os.environ["RAG_EMBEDDING_TIMEOUT_SECONDS"] = "0.5"

from app import models  # noqa: E402
from app.api.deps import DEMO_DOCTOR_ID  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def pg_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        yield None
        return
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database.endswith("_test"):
        raise RuntimeError("PostgreSQL tests require a separate database ending in _test.")
    from alembic.config import Config

    from alembic import command

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def database(pg_engine):
    if pg_engine is not None:
        engine = pg_engine
    else:
        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            from app.api.deps import DEMO_TRIAGE_ID
            from app.core import security

            db.add(
                models.User(
                    id=DEMO_DOCTOR_ID,
                    name="Synthetic Doctor",
                    email="doctor@tests.invalid",
                    phone_number="+919876500001",
                    hashed_password=security.hash_password("Doctor@123"),
                    role="doctor",
                    is_active=True,
                )
            )
            db.add(
                models.User(
                    id=DEMO_TRIAGE_ID,
                    name="Synthetic Triage Staff",
                    email="triage@tests.invalid",
                    phone_number="+919876500002",
                    hashed_password=security.hash_password("Triage@123"),
                    role="triage",
                    is_active=True,
                )
            )
            db.commit()
            yield db
        transaction.rollback()
    if pg_engine is None:
        engine.dispose()


@pytest.fixture
def client(database):
    def override():
        try:
            yield database
        except Exception:
            database.rollback()
            raise

    app.dependency_overrides[get_db] = override
    with TestClient(app, raise_server_exceptions=False) as instance:
        yield instance
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def isolated_document_storage(tmp_path, monkeypatch):
    from app.api.v1 import documents
    from app.services import document_service
    from app.services import storage as storage_module
    from app.services.storage import StorageService

    storage = StorageService(tmp_path / "uploads")
    monkeypatch.setattr(document_service, "default_storage", storage)
    monkeypatch.setattr(documents, "default_storage", storage)
    monkeypatch.setattr(storage_module, "default_storage", storage)
    return storage
