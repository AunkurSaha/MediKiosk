"""Focused regression tests for the audited dual-provider RAG blockers."""

from __future__ import annotations

import asyncio
import importlib.util
import math
from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint, select

from app import models
from app.schemas.patient_rag import PatientRAGSearchRequest
from app.services import patient_rag
from app.services.patient_rag import CanonicalChunk


class InspectingProvider:
    name = "nvidia"
    model = "fake-nvidia"
    version = "test-v1"
    dimension = 4

    def __init__(self, database, output: list[float] | None = None):
        self.database = database
        self.output = [0.25] * self.dimension if output is None else output
        self.patient_id: str | None = None
        self.chunk: CanonicalChunk | None = None

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        assert self.patient_id is not None
        assert self.chunk is not None
        row = self.database.scalar(
            select(models.PatientRAGChunk).where(
                models.PatientRAGChunk.patient_id == self.patient_id,
                models.PatientRAGChunk.embedding_provider == self.name,
                models.PatientRAGChunk.embedding_model == self.model,
                models.PatientRAGChunk.embedding_version == self.version,
            )
        )
        assert row is not None
        assert row.embedding_dimension == self.dimension
        assert row.content_checksum == self.chunk.checksum
        assert row.index_status == "pending"
        return [self.output for _text in texts]

    async def embed_query(self, _text: str) -> list[float]:
        return [0.25] * self.dimension


def _patient(database, patient_id: str) -> None:
    database.add(models.Patient(id=patient_id, name=f"Patient {patient_id}"))
    database.commit()


def _chunk(patient_id: str) -> CanonicalChunk:
    return CanonicalChunk(
        patient_id=patient_id,
        session_id=None,
        source_type="INTERVIEW_ANSWER",
        source_record_id=f"{patient_id}-answer",
        chunk_key="answer",
        text="Patient reported an aspirin allergy.",
        evidence_type="allergy",
        verification_status="UNVERIFIED",
    )


def test_migration_imports_and_model_constraint_matches() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "53d64d0dbe27_dual_provider_rag.py"
    )
    spec = importlib.util.spec_from_file_location("dual_provider_rag_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "53d64d0dbe27"
    assert migration.down_revision == "7a3d9e1c5b20"

    constraint = next(
        item
        for item in models.PatientRAGChunk.__table__.constraints
        if isinstance(item, UniqueConstraint)
        and item.name == "uq_rag_patient_chunk_source_representation"
    )
    assert tuple(column.name for column in constraint.columns) == (
        "source_type",
        "source_record_id",
        "chunk_key",
        "embedding_provider",
        "embedding_model",
        "embedding_version",
    )


def test_legacy_reindex_persists_dimension_before_embedding(database, monkeypatch) -> None:
    patient_id = "legacy-before-embed"
    _patient(database, patient_id)
    chunk = _chunk(patient_id)
    monkeypatch.setattr(patient_rag, "build_patient_chunks", lambda _db, _id: [chunk])
    provider = InspectingProvider(database)
    provider.patient_id = patient_id
    provider.chunk = chunk

    asyncio.run(patient_rag.reindex_patient(database, patient_id, provider))

    row = database.scalar(
        select(models.PatientRAGChunk).where(
            models.PatientRAGChunk.patient_id == patient_id
        )
    )
    assert row is not None
    assert row.embedding_dimension == provider.dimension
    assert row.index_status == "indexed"


@pytest.mark.parametrize(
    "vector",
    [[], [0.25] * 3, [math.nan] * 4, [math.inf] * 4],
    ids=["empty", "wrong-dimension", "nan", "inf"],
)
def test_legacy_reindex_rejects_invalid_vectors(
    database, monkeypatch, vector: list[float]
) -> None:
    patient_id = f"legacy-invalid-{len(vector)}-{str(vector[:1])}"
    _patient(database, patient_id)
    chunk = _chunk(patient_id)
    monkeypatch.setattr(patient_rag, "build_patient_chunks", lambda _db, _id: [chunk])
    provider = InspectingProvider(database, output=vector)
    provider.patient_id = patient_id
    provider.chunk = chunk

    asyncio.run(patient_rag.reindex_patient(database, patient_id, provider))

    row = database.scalar(
        select(models.PatientRAGChunk).where(
            models.PatientRAGChunk.patient_id == patient_id
        )
    )
    assert row is not None
    assert row.embedding is None
    assert row.index_status == "failed"
    assert row.embedding_dimension == provider.dimension
    assert row.index_error


def test_search_lexical_scope_excludes_wrong_dimension(database, monkeypatch) -> None:
    patient_id = "search-dimension"
    session_id = "search-dimension-session"
    _patient(database, patient_id)
    database.add(
        models.Session(
            id=session_id,
            patient_id=patient_id,
            hospital_token="TEST",
            language="en",
            status="intake",
        )
    )
    database.commit()
    database.add(
        models.PatientRAGChunk(
            patient_id=patient_id,
            session_id=session_id,
            source_type="INTERVIEW_ANSWER",
            source_record_id="wrong-dimension-answer",
            chunk_key="answer",
            text="Patient reported an aspirin allergy.",
            normalized_text="aspirin allergy",
            evidence_type="allergy",
            verification_status="UNVERIFIED",
            provenance_json={},
            metadata_json={},
            clinician_verified=False,
            is_current=True,
            is_conflicted=False,
            embedding_provider="nvidia",
            embedding_model="fake-nvidia",
            embedding_version="test-v1",
            embedding_dimension=3,
            embedding=[0.25] * 3,
            content_checksum="0" * 64,
            index_status="indexed",
        )
    )
    database.commit()

    async def no_reindex(*_args, **_kwargs):
        return None

    monkeypatch.setattr(patient_rag, "reindex_patient", no_reindex)
    provider = InspectingProvider(database)
    response = asyncio.run(
        patient_rag.search_patient(
            database,
            session_id,
            PatientRAGSearchRequest(query="aspirin allergy"),
            provider,
        )
    )
    assert response.evidence == []


def test_vector_statement_retains_dimension_filter() -> None:
    statement = patient_rag.postgres_vector_statement(
        [models.PatientRAGChunk.patient_id == "patient"], [0.25] * 4, 5
    )
    assert "embedding_dimension" in str(statement)
