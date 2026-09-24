"""Current-API tests for patient RAG representation lifecycle behavior."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field

from sqlalchemy import select

from app import models
from app.core.errors import ProviderFailure
from app.services import patient_rag
from app.services.patient_rag import CanonicalChunk


@dataclass
class FakeEmbeddingProvider:
    name: str
    model: str
    version: str
    dimension: int
    vector: list[float] | None = None
    error: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        vector = self.vector if self.vector is not None else [0.25] * self.dimension
        return [list(vector) for _text in texts]

    async def embed_query(self, _text: str) -> list[float]:
        if self.error is not None:
            raise self.error
        return list(self.vector or [0.25] * self.dimension)


def _provider(
    name: str,
    *,
    vector: list[float] | None = None,
    error: Exception | None = None,
) -> FakeEmbeddingProvider:
    if name == "mock":
        return FakeEmbeddingProvider("mock", "mock", "0.1.0", 384, vector, error)
    return FakeEmbeddingProvider(
        "nvidia",
        "nvidia/nemotron-3-embed-1b",
        "1.0.0",
        2048,
        vector,
        error,
    )


def _patient(database, patient_id: str) -> None:
    database.add(models.Patient(id=patient_id, name=f"Patient {patient_id}"))
    database.commit()


def _chunk(
    patient_id: str, text: str = "Patient reported an aspirin allergy."
) -> CanonicalChunk:
    return CanonicalChunk(
        patient_id=patient_id,
        session_id=None,
        source_type="INTERVIEW_ANSWER",
        source_record_id=f"{patient_id}-answer",
        chunk_key="answer",
        text=text,
        evidence_type="allergy",
        verification_status="PATIENT_REPORTED",
    )


def _canonical(monkeypatch, chunks: list[CanonicalChunk]) -> None:
    monkeypatch.setattr(
        patient_rag,
        "build_patient_chunks",
        lambda _db, patient_id: [
            chunk for chunk in chunks if chunk.patient_id == patient_id
        ],
    )


def _rows(database, patient_id: str) -> list[models.PatientRAGChunk]:
    return list(
        database.scalars(
            select(models.PatientRAGChunk)
            .where(models.PatientRAGChunk.patient_id == patient_id)
            .order_by(models.PatientRAGChunk.embedding_provider)
        )
    )


def _row(database, patient_id: str, provider_name: str) -> models.PatientRAGChunk:
    return database.scalar(
        select(models.PatientRAGChunk).where(
            models.PatientRAGChunk.patient_id == patient_id,
            models.PatientRAGChunk.embedding_provider == provider_name,
        )
    )


def test_mock_indexed_twice_one_representation(database, monkeypatch) -> None:
    patient_id = "patient-rag-mock-twice"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])
    provider = _provider("mock")

    asyncio.run(patient_rag.reindex_patient(database, patient_id, provider))
    first = _row(database, patient_id, "mock")
    assert first is not None
    first_id = first.id
    asyncio.run(patient_rag.reindex_patient(database, patient_id, provider))

    rows = _rows(database, patient_id)
    assert len(rows) == 1
    assert rows[0].id == first_id
    assert rows[0].index_status == "indexed"
    assert rows[0].embedding_dimension == 384
    assert provider.calls == [["Patient reported an aspirin allergy."]]


def test_mock_and_fake_nvidia_two_representations(database, monkeypatch) -> None:
    patient_id = "patient-rag-dual"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])

    asyncio.run(patient_rag.reindex_patient(database, patient_id, _provider("mock")))
    asyncio.run(patient_rag.reindex_patient(database, patient_id, _provider("nvidia")))

    rows = _rows(database, patient_id)
    assert len(rows) == 2
    assert {row.embedding_provider for row in rows} == {"mock", "nvidia"}
    assert {row.embedding_dimension for row in rows} == {384, 2048}
    assert all(row.index_status == "indexed" for row in rows)


def test_fake_nvidia_indexed_twice_still_two_total(database, monkeypatch) -> None:
    patient_id = "patient-rag-nvidia-twice"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])
    mock = _provider("mock")
    nvidia = _provider("nvidia")

    asyncio.run(patient_rag.reindex_patient(database, patient_id, mock))
    asyncio.run(patient_rag.reindex_patient(database, patient_id, nvidia))
    nvidia_id = _row(database, patient_id, "nvidia").id
    asyncio.run(patient_rag.reindex_patient(database, patient_id, nvidia))

    rows = _rows(database, patient_id)
    assert len(rows) == 2
    assert _row(database, patient_id, "nvidia").id == nvidia_id
    assert len(nvidia.calls) == 1


def test_mock_reindex_preserves_nvidia_row(database, monkeypatch) -> None:
    patient_id = "patient-rag-preserve-nvidia"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id)]
    _canonical(monkeypatch, chunks)
    mock = _provider("mock")
    nvidia = _provider("nvidia")
    asyncio.run(patient_rag.reindex_patient(database, patient_id, mock))
    asyncio.run(patient_rag.reindex_patient(database, patient_id, nvidia))
    nvidia_before = _row(database, patient_id, "nvidia")
    nvidia_snapshot = (
        nvidia_before.id,
        nvidia_before.content_checksum,
        list(nvidia_before.embedding),
        nvidia_before.last_indexed_at,
    )

    chunks[:] = [_chunk(patient_id, "Patient reported a penicillin allergy.")]
    asyncio.run(patient_rag.reindex_patient(database, patient_id, mock))

    nvidia_after = _row(database, patient_id, "nvidia")
    assert (
        nvidia_after.id,
        nvidia_after.content_checksum,
        list(nvidia_after.embedding),
        nvidia_after.last_indexed_at,
    ) == nvidia_snapshot
    assert _row(database, patient_id, "mock").content_checksum == chunks[0].checksum


def test_nvidia_failure_produces_failed_representation_while_mock_remains_indexed(
    database, monkeypatch
) -> None:
    patient_id = "patient-rag-nvidia-failure"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])
    asyncio.run(patient_rag.reindex_patient(database, patient_id, _provider("mock")))
    failing = _provider("nvidia", error=ProviderFailure("unavailable"))

    asyncio.run(patient_rag.reindex_patient(database, patient_id, failing))

    mock_row = _row(database, patient_id, "mock")
    nvidia_row = _row(database, patient_id, "nvidia")
    assert mock_row.index_status == "indexed"
    assert mock_row.embedding is not None
    assert nvidia_row.index_status == "failed"
    assert nvidia_row.embedding is None
    assert nvidia_row.embedding_dimension == 2048
    assert nvidia_row.index_error == "unavailable"


def test_retry_reuses_failed_nvidia_row(database, monkeypatch) -> None:
    patient_id = "patient-rag-nvidia-retry"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])
    failing = _provider("nvidia", error=ProviderFailure("unavailable"))
    asyncio.run(patient_rag.reindex_patient(database, patient_id, failing))
    failed_id = _row(database, patient_id, "nvidia").id

    asyncio.run(patient_rag.reindex_patient(database, patient_id, _provider("nvidia")))

    rows = _rows(database, patient_id)
    assert len(rows) == 1
    assert rows[0].id == failed_id
    assert rows[0].index_status == "indexed"
    assert rows[0].embedding is not None
    assert rows[0].index_error is None


def test_wrong_dimension_rejected(database, monkeypatch) -> None:
    patient_id = "patient-rag-wrong-dimension"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])
    provider = _provider("nvidia", vector=[0.25] * 300)

    asyncio.run(patient_rag.reindex_patient(database, patient_id, provider))

    row = _row(database, patient_id, "nvidia")
    assert row.index_status == "failed"
    assert row.embedding is None
    assert row.embedding_dimension == 2048
    assert row.index_error == "dimension_mismatch"


def test_nan_rejected(database, monkeypatch) -> None:
    patient_id = "patient-rag-nan"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])

    asyncio.run(
        patient_rag.reindex_patient(
            database, patient_id, _provider("mock", vector=[math.nan] * 384)
        )
    )

    row = _row(database, patient_id, "mock")
    assert row.index_status == "failed"
    assert row.embedding is None
    assert row.index_error == "invalid_result"


def test_inf_rejected(database, monkeypatch) -> None:
    patient_id = "patient-rag-inf"
    _patient(database, patient_id)
    _canonical(monkeypatch, [_chunk(patient_id)])

    asyncio.run(
        patient_rag.reindex_patient(
            database, patient_id, _provider("mock", vector=[math.inf] * 384)
        )
    )

    row = _row(database, patient_id, "mock")
    assert row.index_status == "failed"
    assert row.embedding is None
    assert row.index_error == "invalid_result"
