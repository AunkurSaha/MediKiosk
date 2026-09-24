"""Safe single-patient embedding backfill and CLI tests."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, select

from app import models
from app.core.config import configured_indexing_provider, configured_search_provider
from app.core.errors import ProviderFailure
from app.scripts import reindex_rag
from app.services import patient_rag
from app.services.patient_rag import CanonicalChunk, backfill_patient_embeddings
from app.services.patient_rag_coverage import get_patient_embedding_coverage


@dataclass
class FakeProvider:
    name: str = "nvidia"
    model: str = "fake-nvidia"
    version: str = "test-v1"
    dimension: int = 4
    outputs: list[list[list[float]]] = field(default_factory=list)
    error: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        if self.outputs:
            return self.outputs.pop(0)
        return [[0.25] * self.dimension for _ in texts]


MOCK_IDENTITY = ("mock", "mock", "0.1.0", 3)


def _patient(database, patient_id: str) -> None:
    database.add(models.Patient(id=patient_id, name=f"Patient {patient_id}"))
    database.commit()


def _chunk(patient_id: str, key: str, text: str | None = None) -> CanonicalChunk:
    return CanonicalChunk(
        patient_id=patient_id,
        session_id=None,
        source_type="INTERVIEW_ANSWER",
        source_record_id=f"{patient_id}-{key}",
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


def _row(
    database,
    chunk: CanonicalChunk,
    identity: tuple[str, str, str, int],
    *,
    status: str = "indexed",
    checksum: str | None = None,
    embedding: list[float] | None = None,
) -> models.PatientRAGChunk:
    name, model, version, dimension = identity
    row = models.PatientRAGChunk(
        patient_id=chunk.patient_id,
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
        embedding_provider=name,
        embedding_model=model,
        embedding_version=version,
        embedding_dimension=dimension,
        embedding=(
            [0.5] * dimension
            if embedding is None and status == "indexed"
            else embedding
        ),
        content_checksum=checksum or chunk.checksum,
        index_status=status,
    )
    database.add(row)
    database.commit()
    return row


def _identity(provider: FakeProvider) -> tuple[str, str, str, int]:
    return provider.name, provider.model, provider.version, provider.dimension


def _rows(database, patient_id: str, provider: str | None = None):
    statement = select(models.PatientRAGChunk).where(
        models.PatientRAGChunk.patient_id == patient_id
    )
    if provider:
        statement = statement.where(
            models.PatientRAGChunk.embedding_provider == provider
        )
    return list(database.scalars(statement.order_by(models.PatientRAGChunk.id)))


def test_success_idempotency_mock_preservation_and_coverage(
    database, monkeypatch
):
    patient_id = "backfill-success"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b", "c")]
    _canonical(monkeypatch, chunks)
    for chunk in chunks:
        _row(database, chunk, MOCK_IDENTITY)
    provider = FakeProvider()
    indexed = _row(database, chunks[0], _identity(provider))
    failed = _row(database, chunks[1], _identity(provider), status="failed")
    failed_id = failed.id
    mock_before = [
        (row.id, row.content_checksum, row.index_status, list(row.embedding))
        for row in _rows(database, patient_id, "mock")
    ]

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    assert provider.calls == [[chunks[1].text, chunks[2].text]]
    assert result.already_indexed == 1
    assert result.retried_failed == 1
    assert result.created_missing == 1
    assert result.embedded_count == 2
    assert result.coverage_after == 100.0
    assert result.ready_after is True
    nvidia_rows = _rows(database, patient_id, "nvidia")
    assert len(nvidia_rows) == 3
    assert database.get(models.PatientRAGChunk, failed_id).index_status == "indexed"
    assert indexed.index_status == "indexed"
    assert mock_before == [
        (row.id, row.content_checksum, row.index_status, list(row.embedding))
        for row in _rows(database, patient_id, "mock")
    ]
    coverage = get_patient_embedding_coverage(database, patient_id, provider)
    assert coverage.indexed_count == 3
    assert coverage.ready_for_search is True

    second = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    assert provider.calls == [[chunks[1].text, chunks[2].text]]
    assert second.would_embed == 0
    assert second.embedded_count == 0
    assert len(_rows(database, patient_id, "nvidia")) == 3
    assert second.coverage_after == 100.0
    assert configured_indexing_provider() == "mock"
    assert configured_search_provider() == "mock"


def test_stale_representation_is_refreshed_in_place(database, monkeypatch):
    patient_id = "backfill-stale"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a", "current text")
    _canonical(monkeypatch, [chunk])
    provider = FakeProvider()
    stale = _row(
        database,
        chunk,
        _identity(provider),
        checksum="0" * 64,
    )
    stale_id = stale.id
    mock = _row(database, chunk, MOCK_IDENTITY)
    mock_snapshot = (mock.content_checksum, list(mock.embedding))

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    refreshed = database.get(models.PatientRAGChunk, stale_id)
    assert result.refreshed_stale == 1
    assert refreshed.content_checksum == chunk.checksum
    assert refreshed.index_status == "indexed"
    assert len(_rows(database, patient_id, "nvidia")) == 1
    assert (mock.content_checksum, list(mock.embedding)) == mock_snapshot


def test_provider_failure_then_retry_reuses_rows(database, monkeypatch):
    patient_id = "backfill-retry"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b")]
    _canonical(monkeypatch, chunks)
    for chunk in chunks:
        _row(database, chunk, MOCK_IDENTITY)
    failing = FakeProvider(error=ProviderFailure("network_error"))

    failed_result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, failing)
    )

    first_ids = {row.id for row in _rows(database, patient_id, "nvidia")}
    assert failed_result.failed_count == 2
    assert all(row.index_status == "failed" for row in _rows(database, patient_id, "nvidia"))
    assert all(row.embedding is None for row in _rows(database, patient_id, "nvidia"))
    assert failed_result.ready_after is False
    assert all(row.index_status == "indexed" for row in _rows(database, patient_id, "mock"))

    succeeding = FakeProvider()
    retry_result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, succeeding)
    )

    assert retry_result.retried_failed == 2
    assert retry_result.embedded_count == 2
    assert {row.id for row in _rows(database, patient_id, "nvidia")} == first_ids
    assert retry_result.ready_after is True


@pytest.mark.parametrize(
    "invalid_vector",
    [
        [0.1, 0.2],
        [0.1, float("nan"), 0.3, 0.4],
        [0.1, float("inf"), 0.3, 0.4],
        [],
    ],
    ids=("wrong-dimension", "nan", "inf", "empty"),
)
def test_invalid_vector_never_becomes_indexed(
    database, monkeypatch, invalid_vector
):
    patient_id = f"backfill-invalid-{len(invalid_vector)}-{repr(invalid_vector)}"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    mock = _row(database, chunk, MOCK_IDENTITY)
    provider = FakeProvider(outputs=[[invalid_vector]])

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    target = _rows(database, patient_id, "nvidia")[0]
    assert result.embedded_count == 0
    assert result.failed_count == 1
    assert target.index_status == "failed"
    assert target.embedding is None
    assert mock.index_status == "indexed"


def test_bounded_batching(database, monkeypatch):
    patient_id = "backfill-batches"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, str(index)) for index in range(5)]
    _canonical(monkeypatch, chunks)
    provider = FakeProvider()

    result = asyncio.run(
        backfill_patient_embeddings(
            database, patient_id, provider, batch_size=2
        )
    )

    assert [len(call) for call in provider.calls] == [2, 2, 1]
    assert result.estimated_batches == 3
    assert result.embedded_count == 5


def test_new_row_metadata_exists_before_embedding_call(database, monkeypatch):
    patient_id = "backfill-metadata-first"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])

    class InspectingProvider(FakeProvider):
        async def embed_documents(self, texts: list[str]) -> list[list[float]]:
            target = _rows(database, patient_id, "nvidia")[0]
            assert target.embedding_model == self.model
            assert target.embedding_version == self.version
            assert target.embedding_dimension == self.dimension
            assert target.content_checksum == chunk.checksum
            assert target.index_status == "pending"
            assert target.embedding is None
            return await super().embed_documents(texts)

    provider = InspectingProvider()

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    assert result.embedded_count == 1


def test_wrong_result_count_marks_only_batch_failed(database, monkeypatch):
    patient_id = "backfill-count-mismatch"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b")]
    _canonical(monkeypatch, chunks)
    provider = FakeProvider(outputs=[[[0.1] * 4]])

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    assert result.failed_count == 2
    assert all(row.index_status == "failed" for row in _rows(database, patient_id, "nvidia"))
    assert all(row.embedding is None for row in _rows(database, patient_id, "nvidia"))


def test_one_invalid_vector_does_not_discard_valid_peer(database, monkeypatch):
    patient_id = "backfill-partial"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b")]
    _canonical(monkeypatch, chunks)
    provider = FakeProvider(outputs=[[[0.2] * 4, [float("nan")] * 4]])

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_id, provider)
    )

    statuses = sorted(row.index_status for row in _rows(database, patient_id, "nvidia"))
    assert statuses == ["failed", "indexed"]
    assert result.embedded_count == 1
    assert result.failed_count == 1


def test_dry_run_is_read_only_and_makes_no_provider_calls(database, monkeypatch):
    patient_id = "backfill-dry-run"
    _patient(database, patient_id)
    chunks = [_chunk(patient_id, key) for key in ("a", "b", "c", "d", "e")]
    _canonical(monkeypatch, chunks)
    provider = FakeProvider()
    indexed = _row(database, chunks[0], _identity(provider))
    failed = _row(database, chunks[1], _identity(provider), status="failed")
    pending = _row(database, chunks[2], _identity(provider), status="pending")
    stale = _row(database, chunks[3], _identity(provider), checksum="f" * 64)
    before_count = database.scalar(select(func.count(models.PatientRAGChunk.id)))
    before = {
        row.id: (row.index_status, row.content_checksum, row.embedding)
        for row in (indexed, failed, pending, stale)
    }

    result = asyncio.run(
        backfill_patient_embeddings(
            database, patient_id, provider, dry_run=True, batch_size=2
        )
    )

    assert result.already_indexed == 1
    assert result.failed_before_count == 1
    assert result.pending_count == 1
    assert result.stale_count == 1
    assert result.missing_count == 1
    assert result.would_embed == 4
    assert result.estimated_batches == 2
    assert provider.calls == []
    assert database.scalar(select(func.count(models.PatientRAGChunk.id))) == before_count
    database.expire_all()
    assert before == {
        row.id: (row.index_status, row.content_checksum, row.embedding)
        for row in (indexed, failed, pending, stale)
    }


def test_patient_isolation(database, monkeypatch):
    patient_a = "backfill-isolation-a"
    patient_b = "backfill-isolation-b"
    _patient(database, patient_a)
    _patient(database, patient_b)
    chunk_a = _chunk(patient_a, "a")
    chunk_b = _chunk(patient_b, "b")
    _canonical(monkeypatch, [chunk_a, chunk_b])
    provider = FakeProvider()
    row_b = _row(database, chunk_b, _identity(provider), status="failed")
    snapshot_b = (row_b.id, row_b.index_status, row_b.content_checksum)

    result = asyncio.run(
        backfill_patient_embeddings(database, patient_a, provider)
    )

    database.refresh(row_b)
    assert result.created_missing == 1
    assert (row_b.id, row_b.index_status, row_b.content_checksum) == snapshot_b


def test_cli_requires_patient_for_nvidia():
    args = reindex_rag.arguments(["--provider", "nvidia", "--session", "session-id"])
    with pytest.raises(SystemExit, match="requires --patient-id"):
        asyncio.run(reindex_rag.run(args))


def test_cli_nvidia_bulk_is_disabled():
    args = reindex_rag.arguments(
        ["--provider", "nvidia", "--all", "--confirm-all", "--confirm-bulk"]
    )
    with pytest.raises(SystemExit, match="bulk mode is disabled"):
        asyncio.run(reindex_rag.run(args))


def test_cli_dry_run_uses_fake_provider(
    database, monkeypatch, capsys
):
    patient_id = "backfill-cli"
    _patient(database, patient_id)
    chunk = _chunk(patient_id, "a")
    _canonical(monkeypatch, [chunk])
    provider = FakeProvider()
    monkeypatch.setattr(reindex_rag, "configured_provider", lambda _name: provider)
    monkeypatch.setattr(reindex_rag, "SessionLocal", lambda: nullcontext(database))
    args = reindex_rag.arguments(
        ["--provider", "nvidia", "--patient-id", patient_id, "--dry-run"]
    )

    assert asyncio.run(reindex_rag.run(args)) == 0

    output = capsys.readouterr().out
    assert "Provider: nvidia" in output
    assert "Patient: backfill-cli" in output
    assert "Would embed: 1" in output
    assert "Ready after: false" in output
    assert provider.calls == []
    assert _rows(database, patient_id, "nvidia") == []
