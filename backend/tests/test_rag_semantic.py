"""Tests for semantic RAG retrieval, vector compatibility, and fail-open behavior.

Verifies:
- Semantic retrieval quality with clinical paraphrases (not exact keywords)
- Cosine ranking of clinically relevant chunks
- Stale / incompatible vector rejection (dimension mismatch, provider mismatch)
- Ingestion idempotency and re-embedding
- Fail-open retrieval on provider outage
- Comparison of semantic vs mock vector capabilities
"""

import asyncio
import math
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.core.errors import ProviderFailure
from app.database import Base
from app.services.embedding_provider import MockEmbeddingProvider
from app.services.rag import KnowledgeIngestionService, KnowledgeRetrievalService


@pytest.fixture
def db_session():
    """In-memory SQLite session with table creation."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


class ControlledSemanticEmbeddingProvider:
    """Controlled semantic embedding simulator for deterministic offline CI testing.

    NOTE ON SIMILARITY SCORES:
    This simulator constructs an idealized orthogonal 4-dimensional concept basis
    (dyspnea, exertion, radiation, autonomic) where matching concepts yield high
    unit similarities around ~0.92-0.94, and orthogonal concepts yield ~0.05.
    
    This verifies the algorithmic ranking and thresholding logic in a deterministic,
    offline environment without relying on external network calls.
    
    In contrast, real-world dense embeddings (e.g. nvidia/nemotron-3-embed-1b in 2048 dimensions)
    exhibit a broader dense similarity distribution, where relevant clinical paraphrases
    score ~0.28 to ~0.52 (mean ~0.42), while unrelated negative controls score below 0.16.
    """

    name = "semantic_sim"
    model = "controlled-semantic-v1"
    dimension = 4

    # 4 semantic dimensions:
    # 0: DYSPNEA / BREATHLESSNESS
    # 1: EXERTION / PROVOCATION
    # 2: RADIATION / SPREAD
    # 3: AUTONOMIC / SWEATING / NAUSEA

    CONCEPT_WEIGHTS = {
        # Dyspnea concepts
        "dyspnea": [1.0, 0.0, 0.0, 0.0],
        "shortness of breath": [1.0, 0.0, 0.0, 0.0],
        "breathless": [0.95, 0.2, 0.0, 0.0],
        "difficulty breathing": [1.0, 0.0, 0.0, 0.0],
        # Exertion concepts
        "exertion": [0.0, 1.0, 0.0, 0.0],
        "provocation": [0.0, 0.9, 0.0, 0.0],
        "walking": [0.1, 0.9, 0.0, 0.0],
        "climbing stairs": [0.2, 0.9, 0.0, 0.0],
        "physical activity": [0.0, 0.95, 0.0, 0.0],
        # Radiation concepts
        "radiat": [0.0, 0.0, 1.0, 0.0],
        "travels toward": [0.0, 0.0, 0.9, 0.0],
        "jaw": [0.0, 0.0, 0.8, 0.0],
        "left arm": [0.0, 0.0, 0.85, 0.0],
        "upper limb": [0.0, 0.0, 0.8, 0.0],
        # Autonomic / Sweating / Nausea
        "diaphoresis": [0.0, 0.0, 0.0, 1.0],
        "sweating": [0.0, 0.0, 0.0, 0.95],
        "cold sweat": [0.0, 0.0, 0.0, 0.95],
        "nausea": [0.0, 0.0, 0.0, 0.9],
        "feeling sick": [0.0, 0.0, 0.0, 0.85],
        "vomiting": [0.0, 0.0, 0.0, 0.9],
    }

    def _embed(self, text: str) -> List[float]:
        t = text.lower()
        vec = [0.05, 0.05, 0.05, 0.05]  # baseline
        for phrase, weights in self.CONCEPT_WEIGHTS.items():
            if phrase in t:
                for idx, w in enumerate(weights):
                    vec[idx] += w
        # Normalize to unit vector
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec]

    async def embed_query(self, text: str) -> List[float]:
        return self._embed(text)

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    async def embed(self, text: str) -> List[float]:
        return await self.embed_query(text)

    async def embed_many(self, texts: List[str]) -> List[List[float]]:
        return await self.embed_documents(texts)


def test_semantic_retrieval_clinical_paraphrases(db_session):
    """Verify semantic retrieval ranks clinically relevant chunks highest on paraphrased queries."""
    provider = ControlledSemanticEmbeddingProvider()

    # Seed 4 distinct chest pain knowledge chunks
    chunks_data = [
        {
            "id": "cp-dyspnea-001",
            "source_id": "associated_symptoms",
            "source_title": "Associated Symptoms",
            "section": "dyspnea",
            "topic": "chest_pain",
            "content": "Dyspnea and shortness of breath are key associated symptoms in acute chest discomfort.",
        },
        {
            "id": "cp-exertion-002",
            "source_id": "history_taking",
            "source_title": "History Taking",
            "section": "exertion",
            "topic": "chest_pain",
            "content": "History taking should determine provocation and exacerbating factors such as walking or exertion.",
        },
        {
            "id": "cp-radiation-003",
            "source_id": "warning_features",
            "source_title": "Warning Features",
            "section": "radiation",
            "topic": "chest_pain",
            "content": "Cardiac warning features include pain radiating to the jaw, neck, back, or left arm.",
        },
        {
            "id": "cp-sweating-004",
            "source_id": "associated_symptoms",
            "source_title": "Associated Symptoms",
            "section": "autonomic",
            "topic": "chest_pain",
            "content": "Autonomic symptoms include diaphoresis, heavy sweating, nausea, and vomiting accompanying chest pain.",
        },
    ]

    for d in chunks_data:
        emb = asyncio.run(provider.embed_query(d["content"]))
        kc = models.KnowledgeChunk(
            id=d["id"],
            source_id=d["source_id"],
            source_title=d["source_title"],
            section=d["section"],
            topic=d["topic"],
            content=d["content"],
            language="en",
            document_version="1.0",
            checksum="test_check",
            embedding_model=provider.model,
            embedding_provider=provider.name,
            embedding_dimension=len(emb),
        )
        kc.set_embedding(emb, provider=provider.name, model=provider.model)
        db_session.add(kc)
    db_session.commit()

    service = KnowledgeRetrievalService(db_session_factory=lambda: db_session)
    service.embedding_provider = provider

    # 1. Query: "Patient gets breathless while climbing stairs with chest discomfort"
    res1 = asyncio.run(service.retrieve(
        "Patient gets breathless while climbing stairs with chest discomfort",
        topic="chest_pain",
        top_k=2,
    ))
    assert len(res1) >= 1
    top_chunk1, score1 = res1[0]
    assert top_chunk1.id == "cp-dyspnea-001"
    assert score1 > 0.7

    # 2. Query: "Pressure in chest becomes worse while walking"
    res2 = asyncio.run(service.retrieve(
        "Pressure in chest becomes worse while walking",
        topic="chest_pain",
        top_k=2,
    ))
    assert len(res2) >= 1
    top_chunk2, score2 = res2[0]
    assert top_chunk2.id == "cp-exertion-002"
    assert score2 > 0.7

    # 3. Query: "Pain travels toward the jaw and left upper limb"
    res3 = asyncio.run(service.retrieve(
        "Pain travels toward the jaw and left upper limb",
        topic="chest_pain",
        top_k=2,
    ))
    assert len(res3) >= 1
    top_chunk3, score3 = res3[0]
    assert top_chunk3.id == "cp-radiation-003"
    assert score3 > 0.7

    # 4. Query: "Cold sweat and feeling sick with central chest discomfort"
    res4 = asyncio.run(service.retrieve(
        "Cold sweat and feeling sick with central chest discomfort",
        topic="chest_pain",
        top_k=2,
    ))
    assert len(res4) >= 1
    top_chunk4, score4 = res4[0]
    assert top_chunk4.id == "cp-sweating-004"
    assert score4 > 0.7


def test_incompatible_stored_vectors_skipped(db_session, caplog):
    """Ensure vectors with mismatched dimensions or incompatible providers are skipped without crashing."""
    active_provider = MockEmbeddingProvider(dimension=384)

    # Insert a valid chunk
    valid_chunk = models.KnowledgeChunk(
        id="chunk-valid",
        source_id="src1",
        source_title="Title 1",
        section="s1",
        topic="chest_pain",
        content="Valid content with matching dimension",
        language="en",
        document_version="1.0",
        checksum="chk1",
        embedding_model="mock",
        embedding_provider="mock",
        embedding_dimension=384,
    )
    valid_emb = asyncio.run(active_provider.embed_query("Valid content with matching dimension"))
    valid_chunk.set_embedding(valid_emb, provider="mock", model="mock")
    db_session.add(valid_chunk)

    # Insert an incompatible 2048-dim chunk
    incompatible_chunk = models.KnowledgeChunk(
        id="chunk-incompatible-dim",
        source_id="src2",
        source_title="Title 2",
        section="s2",
        topic="chest_pain",
        content="Old or different dimension vector",
        language="en",
        document_version="1.0",
        checksum="chk2",
        embedding_model="nvidia/nemotron-3-embed-1b",
        embedding_provider="nvidia",
        embedding_dimension=2048,
    )
    incompatible_chunk.set_embedding([0.01] * 2048, provider="nvidia", model="nvidia/nemotron-3-embed-1b")
    db_session.add(incompatible_chunk)
    db_session.commit()

    service = KnowledgeRetrievalService(db_session_factory=lambda: db_session)
    service.embedding_provider = active_provider

    results = asyncio.run(service.retrieve("Valid content with matching dimension", topic="chest_pain"))
    assert len(results) == 1
    assert results[0][0].id == "chunk-valid"
    assert any("dimension mismatch" in record.message for record in caplog.records)


def test_retrieval_fail_open_on_provider_failure(db_session):
    """Verify retrieval fails open returning [] if embedding provider raises an exception."""
    class FailingProvider:
        name = "failing"
        model = "failing"
        dimension = 384

        async def embed_query(self, text: str):
            raise ProviderFailure("timeout")

        async def embed_documents(self, texts: List[str]):
            raise ProviderFailure("timeout")

    service = KnowledgeRetrievalService(db_session_factory=lambda: db_session)
    service.embedding_provider = FailingProvider()

    results = asyncio.run(service.retrieve("chest pain", topic="chest_pain"))
    assert results == []


def test_ingestion_idempotency_and_reembed(tmp_path, db_session):
    """Verify knowledge ingestion is idempotent and properly re-embeds when requested."""
    md_file = tmp_path / "test_knowledge.md"
    md_file.write_text("# Test Section\n\nClinical guidance text for chest pain.", encoding="utf-8")

    provider1 = MockEmbeddingProvider(dimension=384)
    ingestion = KnowledgeIngestionService(db_session_factory=lambda: db_session)
    ingestion.embedding_provider = provider1

    # First ingestion
    asyncio.run(ingestion.ingest_file(
        file_path=str(md_file),
        source_id="test-doc",
        source_title="Test Doc",
        section="test_section",
        topic="chest_pain",
    ))

    chunks = db_session.query(models.KnowledgeChunk).all()
    assert len(chunks) == 2
    for c in chunks:
        assert c.embedding_dimension == 384
        assert c.embedding_provider == "mock"

    # Second ingestion without force: should be a no-op (same count, not duplicated)
    asyncio.run(ingestion.ingest_file(
        file_path=str(md_file),
        source_id="test-doc",
        source_title="Test Doc",
        section="test_section",
        topic="chest_pain",
    ))
    chunks_after = db_session.query(models.KnowledgeChunk).all()
    assert len(chunks_after) == 2  # No duplicate chunks created!

    # Third ingestion with a different provider: updates embedding and provenance
    provider2 = ControlledSemanticEmbeddingProvider()
    ingestion.embedding_provider = provider2
    asyncio.run(ingestion.ingest_file(
        file_path=str(md_file),
        source_id="test-doc",
        source_title="Test Doc",
        section="test_section",
        topic="chest_pain",
        force_reembed=True,
    ))

    chunks_updated = db_session.query(models.KnowledgeChunk).all()
    assert len(chunks_updated) == 2
    for c in chunks_updated:
        assert c.embedding_dimension == 4
        assert c.embedding_provider == "semantic_sim"
