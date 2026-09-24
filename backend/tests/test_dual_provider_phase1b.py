"""Current-API tests for independent patient-RAG index and search providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest
from sqlalchemy import select

from app import models
from app.core import config
from app.schemas.patient_rag import PatientRAGSearchRequest, PatientRAGSearchResponse
from app.services import patient_rag
from app.services.patient_rag import CanonicalChunk


@dataclass
class FakeEmbeddingProvider:
    name: str
    model: str
    version: str
    dimension: int
    calls: list[tuple[str, list[str]]] = field(default_factory=list)

    def vector(self) -> list[float]:
        return [1.0] + ([0.0] * (self.dimension - 1))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(("documents", list(texts)))
        return [self.vector() for _text in texts]

    async def embed_query(self, text: str) -> list[float]:
        self.calls.append(("query", [text]))
        return self.vector()


MOCK_PROVIDER = FakeEmbeddingProvider("mock", "mock", "0.1.0", 384)
NVIDIA_PROVIDER = FakeEmbeddingProvider(
    "nvidia", "nvidia/nemotron-3-embed-1b", "1.0.0", 2048
)


def _fresh_provider(name: str) -> FakeEmbeddingProvider:
    if name == "mock":
        return FakeEmbeddingProvider("mock", "mock", "0.1.0", 384)
    return FakeEmbeddingProvider(
        "nvidia", "nvidia/nemotron-3-embed-1b", "1.0.0", 2048
    )


def _patient_session(database, patient_id: str, session_id: str) -> None:
    database.add(models.Patient(id=patient_id, name=f"Patient {patient_id}"))
    database.commit()
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


def _canonical(patient_id: str, session_id: str) -> CanonicalChunk:
    return CanonicalChunk(
        patient_id=patient_id,
        session_id=session_id,
        source_type="INTERVIEW_ANSWER",
        source_record_id=f"{patient_id}-allergy",
        chunk_key="answer",
        text="Patient reported an aspirin allergy.",
        evidence_type="allergy",
        verification_status="PATIENT_REPORTED",
    )


def _representation(
    database,
    *,
    patient_id: str,
    session_id: str,
    source_record_id: str,
    provider: str = "nvidia",
    model: str = "nvidia/nemotron-3-embed-1b",
    version: str = "1.0.0",
    dimension: int = 2048,
    status: str = "indexed",
    text: str = "Patient reported an aspirin allergy.",
) -> models.PatientRAGChunk:
    row = models.PatientRAGChunk(
        patient_id=patient_id,
        session_id=session_id,
        source_type="INTERVIEW_ANSWER",
        source_record_id=source_record_id,
        chunk_key="answer",
        text=text,
        normalized_text=text.lower(),
        evidence_type="allergy",
        verification_status="PATIENT_REPORTED",
        provenance_json={},
        metadata_json={},
        clinician_verified=False,
        is_current=True,
        is_conflicted=False,
        embedding_provider=provider,
        embedding_model=model,
        embedding_version=version,
        embedding_dimension=dimension,
        embedding=([1.0] + ([0.0] * (dimension - 1))) if status == "indexed" else None,
        content_checksum=(source_record_id.encode().hex() + ("0" * 64))[:64],
        index_status=status,
    )
    database.add(row)
    database.commit()
    return row


def _search(
    database,
    session_id: str,
    provider: FakeEmbeddingProvider | None = None,
    query: str = "aspirin allergy",
) -> PatientRAGSearchResponse:
    return asyncio.run(
        patient_rag.search_patient(
            database,
            session_id,
            PatientRAGSearchRequest(query=query, top_k=20),
            provider,
        )
    )


def test_config_legacy_only(monkeypatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    monkeypatch.delenv("RAG_INDEXING_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RAG_ACTIVE_EMBEDDING_PROVIDER", raising=False)
    assert config.configured_indexing_provider() == "mock"
    assert config.configured_search_provider() == "mock"


def test_config_indexing_override(monkeypatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("RAG_INDEXING_EMBEDDING_PROVIDER", "nvidia")
    monkeypatch.delenv("RAG_ACTIVE_EMBEDDING_PROVIDER", raising=False)
    assert config.configured_indexing_provider() == "nvidia"
    assert config.configured_search_provider() == "mock"


def test_config_search_override(monkeypatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    monkeypatch.delenv("RAG_INDEXING_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("RAG_ACTIVE_EMBEDDING_PROVIDER", "nvidia")
    assert config.configured_indexing_provider() == "mock"
    assert config.configured_search_provider() == "nvidia"


def test_config_both_explicit(monkeypatch) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("RAG_INDEXING_EMBEDDING_PROVIDER", "nvidia")
    monkeypatch.setenv("RAG_ACTIVE_EMBEDDING_PROVIDER", "mock")
    assert config.configured_indexing_provider() == "nvidia"
    assert config.configured_search_provider() == "mock"


def test_indexing_provider_can_differ_from_search_provider(
    database, monkeypatch
) -> None:
    patient_id = "phase1b-provider-selection"
    session_id = "phase1b-provider-selection-session"
    _patient_session(database, patient_id, session_id)
    chunk = _canonical(patient_id, session_id)
    monkeypatch.setattr(patient_rag, "build_patient_chunks", lambda _db, _id: [chunk])
    providers = {"mock": _fresh_provider("mock"), "nvidia": _fresh_provider("nvidia")}
    monkeypatch.setattr(patient_rag, "configured_provider", providers.__getitem__)
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("RAG_INDEXING_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("RAG_ACTIVE_EMBEDDING_PROVIDER", "nvidia")

    asyncio.run(patient_rag.reindex_patient(database, patient_id))
    rows = list(
        database.scalars(
            select(models.PatientRAGChunk).where(
                models.PatientRAGChunk.patient_id == patient_id
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].embedding_provider == "mock"
    empty_response = _search(database, session_id)
    assert empty_response.embedding_provider == "nvidia"
    assert empty_response.evidence == []

    asyncio.run(patient_rag.reindex_patient(database, patient_id, providers["nvidia"]))
    response = _search(database, session_id)
    assert [item.source_record_id for item in response.evidence] == [
        chunk.source_record_id
    ]
    assert response.embedding_provider == "nvidia"


@pytest.mark.parametrize(
    ("wrong_field", "wrong_value"),
    [
        ("provider", "mock"),
        ("model", "other-embedding-model"),
        ("version", "old-version"),
        ("dimension", 384),
        ("status", "pending"),
    ],
    ids=["provider", "model", "version", "dimension", "index-status"],
)
def test_active_representation_identity_isolation(
    database, wrong_field: str, wrong_value: str | int
) -> None:
    patient_id = f"phase1b-{wrong_field}"
    session_id = f"phase1b-{wrong_field}-session"
    _patient_session(database, patient_id, session_id)
    active = _representation(
        database,
        patient_id=patient_id,
        session_id=session_id,
        source_record_id=f"{wrong_field}-active",
    )
    wrong = {
        "provider": "nvidia",
        "model": "nvidia/nemotron-3-embed-1b",
        "version": "1.0.0",
        "dimension": 2048,
        "status": "indexed",
    }
    wrong[wrong_field] = wrong_value
    _representation(
        database,
        patient_id=patient_id,
        session_id=session_id,
        source_record_id=f"{wrong_field}-wrong",
        **wrong,
    )

    response = _search(database, session_id, _fresh_provider("nvidia"))

    assert [item.chunk_id for item in response.evidence] == [active.id]
    assert response.evidence[0].source_record_id == f"{wrong_field}-active"


def test_lexical_candidates_use_complete_active_scope(database) -> None:
    patient_id = "phase1b-lexical-scope"
    session_id = "phase1b-lexical-scope-session"
    _patient_session(database, patient_id, session_id)
    active = _representation(
        database,
        patient_id=patient_id,
        session_id=session_id,
        source_record_id="lexical-active",
    )
    variants = [
        {"provider": "mock", "model": "mock", "version": "0.1.0", "dimension": 384},
        {"model": "wrong-model"},
        {"version": "wrong-version"},
        {"dimension": 384},
        {"status": "failed"},
    ]
    for index, values in enumerate(variants):
        _representation(
            database,
            patient_id=patient_id,
            session_id=session_id,
            source_record_id=f"lexical-wrong-{index}",
            **values,
        )

    response = _search(database, session_id, _fresh_provider("nvidia"))

    assert [item.chunk_id for item in response.evidence] == [active.id]


def test_vector_candidates_receive_complete_active_scope(database, monkeypatch) -> None:
    patient_id = "phase1b-vector-scope"
    session_id = "phase1b-vector-scope-session"
    _patient_session(database, patient_id, session_id)
    active = _representation(
        database,
        patient_id=patient_id,
        session_id=session_id,
        source_record_id="vector-active",
    )
    captured_conditions = []

    def capture_statement(conditions, _query_vector, limit):
        captured_conditions.extend(conditions)
        return select(models.PatientRAGChunk).where(*conditions).limit(limit)

    monkeypatch.setattr(patient_rag, "postgres_vector_statement", capture_statement)
    monkeypatch.setattr(database.bind.dialect, "name", "postgresql")

    response = _search(database, session_id, _fresh_provider("nvidia"))

    rendered = " ".join(
        str(condition.compile(compile_kwargs={"literal_binds": True}))
        for condition in captured_conditions
    )
    assert f"rag_patient_chunks.patient_id = '{patient_id}'" in rendered
    assert "rag_patient_chunks.embedding_provider = 'nvidia'" in rendered
    assert "rag_patient_chunks.embedding_model = 'nvidia/nemotron-3-embed-1b'" in rendered
    assert "rag_patient_chunks.embedding_version = '1.0.0'" in rendered
    assert "rag_patient_chunks.embedding_dimension = 2048" in rendered
    assert "rag_patient_chunks.index_status = 'indexed'" in rendered
    assert [item.chunk_id for item in response.evidence] == [active.id]


def test_cross_patient_isolation(database) -> None:
    patient_a = "phase1b-patient-a"
    patient_b = "phase1b-patient-b"
    session_a = "phase1b-session-a"
    session_b = "phase1b-session-b"
    _patient_session(database, patient_a, session_a)
    _patient_session(database, patient_b, session_b)
    row_a = _representation(
        database,
        patient_id=patient_a,
        session_id=session_a,
        source_record_id="patient-a-allergy",
    )
    row_b = _representation(
        database,
        patient_id=patient_b,
        session_id=session_b,
        source_record_id="patient-b-allergy",
    )

    response_a = _search(database, session_a, _fresh_provider("nvidia"))
    response_b = _search(database, session_b, _fresh_provider("nvidia"))

    assert [item.chunk_id for item in response_a.evidence] == [row_a.id]
    assert [item.chunk_id for item in response_b.evidence] == [row_b.id]


def test_response_provider_metadata_and_scoring(database) -> None:
    patient_id = "phase1b-response"
    session_id = "phase1b-response-session"
    _patient_session(database, patient_id, session_id)
    row = _representation(
        database,
        patient_id=patient_id,
        session_id=session_id,
        source_record_id="response-allergy",
    )
    provider = _fresh_provider("nvidia")

    response = _search(database, session_id, provider)

    assert response.embedding_provider == provider.name
    assert response.embedding_model == provider.model
    assert response.fallback_used is False
    assert [item.chunk_id for item in response.evidence] == [row.id]
    # 0.50 vector + 0.30 keyword + 0.12 intent + 0.10 patient-reported
    # + 0.08 current-record boost.
    assert response.evidence[0].similarity == pytest.approx(1.0)
    assert response.evidence[0].score == pytest.approx(1.10)
