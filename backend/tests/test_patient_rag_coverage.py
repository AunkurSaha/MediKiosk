"""Coverage/readiness tests for dual-provider patient RAG representations."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import models
from app.services import patient_rag, patient_rag_coverage
from app.services.patient_rag import CanonicalChunk


@dataclass(frozen=True)
class FakeProvider:
    name: str
    model: str
    version: str
    dimension: int


MOCK = FakeProvider("mock", "mock", "0.1.0", 3)
NVIDIA = FakeProvider("nvidia", "fake-nvidia", "test-v1", 4)


def _patient(database, patient_id: str) -> None:
    database.add(models.Patient(id=patient_id, name=f"Patient {patient_id}"))
    database.commit()


def _chunk(
    patient_id: str,
    key: str,
    text: str | None = None,
    source_record_id: str | None = None,
) -> CanonicalChunk:
    return CanonicalChunk(
        patient_id=patient_id,
        session_id=None,
        source_type="INTERVIEW_ANSWER",
        source_record_id=source_record_id or f"{patient_id}-{key}",
        chunk_key="answer",
        text=text or f"Canonical {key}",
        evidence_type="interview",
        verification_status="UNVERIFIED",
    )


def _canonical(monkeypatch, chunks: list[CanonicalChunk]) -> None:
    monkeypatch.setattr(
        patient_rag,
        "build_patient_chunks",
        lambda _db, patient_id: [
            chunk for chunk in chunks if chunk.patient_id == patient_id
        ],
    )


def _representation(
    database,
    chunk: CanonicalChunk,
    provider: FakeProvider,
    *,
    status: str = "indexed",
    checksum: str | None = None,
    embedding: list[float] | None = None,
    patient_id: str | None = None,
    model: str | None = None,
    version: str | None = None,
) -> models.PatientRAGChunk:
    row = models.PatientRAGChunk(
        patient_id=patient_id or chunk.patient_id,
        source_type=chunk.source_type,
        source_record_id=chunk.source_record_id,
        chunk_key=chunk.chunk_key,
        text=chunk.text,
        evidence_type=chunk.evidence_type,
        verification_status=chunk.verification_status,
        provenance_json={},
        metadata_json={},
        clinician_verified=False,
        is_current=True,
        is_conflicted=False,
        embedding_provider=provider.name,
        embedding_model=model or provider.model,
        embedding_version=version or provider.version,
        embedding_dimension=provider.dimension,
        embedding=(
            [0.25] * provider.dimension
            if embedding is None and status == "indexed"
            else embedding
        ),
        content_checksum=checksum or chunk.checksum,
        index_status=status,
    )
    database.add(row)
    database.commit()
    return row


def test_empty_patient_has_zero_coverage(database, monkeypatch):
    patient_id = "coverage-empty"
    _patient(database, patient_id)
    _canonical(monkeypatch, [])

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, MOCK
    )

    assert result.canonical_chunk_count == 0
    assert result.coverage_percent == 0.0
    assert result.ready_for_search is False


def test_full_mock_coverage_is_ready(database, monkeypatch):
    patient_id = "coverage-mock"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b", "c")]
    _canonical(monkeypatch, chunks)
    for chunk in chunks:
        _representation(database, chunk, MOCK)

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, MOCK
    )

    assert result.canonical_chunk_count == 3
    assert result.indexed_count == 3
    assert result.coverage_percent == 100.0
    assert result.ready_for_search is True


def test_mixed_nvidia_coverage(database, monkeypatch):
    patient_id = "coverage-mixed"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b", "c")]
    _canonical(monkeypatch, chunks)
    _representation(database, chunks[0], NVIDIA)
    _representation(database, chunks[1], NVIDIA, status="failed")

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, NVIDIA
    )

    assert result.canonical_chunk_count == 3
    assert result.indexed_count == 1
    assert result.failed_count == 1
    assert result.missing_count == 1
    assert result.ready_for_search is False


def test_pending_representation_is_not_ready(database, monkeypatch):
    patient_id = "coverage-pending"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    _representation(database, chunk, NVIDIA, status="pending")

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, NVIDIA
    )

    assert result.pending_count == 1
    assert result.ready_for_search is False


def test_stale_checksum_is_not_indexed(database, monkeypatch):
    patient_id = "coverage-stale"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    _representation(database, chunk, NVIDIA, checksum="0" * 64)

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, NVIDIA
    )

    assert result.stale_count == 1
    assert result.indexed_count == 0
    assert result.ready_for_search is False


def test_dual_representations_count_as_one_canonical_chunk(database, monkeypatch):
    patient_id = "coverage-dual"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    _representation(database, chunk, MOCK)
    _representation(database, chunk, NVIDIA)

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, NVIDIA
    )

    assert result.canonical_chunk_count == 1
    assert result.indexed_count == 1
    assert result.ready_for_search is True


@pytest.mark.parametrize(
    ("model", "version"),
    [("wrong-model", NVIDIA.version), (NVIDIA.model, "wrong-version")],
)
def test_wrong_model_or_version_is_missing(
    database, monkeypatch, model: str, version: str
):
    patient_id = f"coverage-wrong-{model}-{version}"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    _representation(database, chunk, NVIDIA, model=model, version=version)

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, NVIDIA
    )

    assert result.missing_count == 1
    assert result.indexed_count == 0
    assert result.ready_for_search is False


def test_cross_patient_rows_do_not_affect_coverage(database, monkeypatch):
    patient_a = "coverage-patient-a"
    patient_b = "coverage-patient-b"
    _patient(database, patient_a)
    _patient(database, patient_b)
    chunk_a = _chunk(patient_a, "shared")
    chunk_b = _chunk(patient_b, "shared", source_record_id=chunk_a.source_record_id)
    # Give both patients the same canonical logical identity to prove that the
    # SQL patient predicate, rather than merely the key map, provides isolation.
    _canonical(monkeypatch, [chunk_a, chunk_b])
    _representation(database, chunk_b, NVIDIA)

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_a, NVIDIA
    )

    assert result.canonical_chunk_count == 1
    assert result.missing_count == 1
    assert result.indexed_count == 0
    assert result.ready_for_search is False


def test_orphaned_representation_does_not_affect_coverage(database, monkeypatch):
    patient_id = "coverage-orphan"
    _patient(database, patient_id)
    current = _chunk(patient_id, "current")
    orphan = _chunk(patient_id, "orphan")
    _canonical(monkeypatch, [current])
    _representation(database, current, MOCK)
    _representation(database, orphan, MOCK, status="failed")

    result = patient_rag_coverage.get_patient_embedding_coverage(
        database, patient_id, MOCK
    )

    assert result.canonical_chunk_count == 1
    assert result.indexed_count == 1
    assert result.failed_count == 0
    assert result.ready_for_search is True
