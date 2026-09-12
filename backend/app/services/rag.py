"""RAG (Retrieval-Augmented Generation) service."""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app import models
from app.core.config import RAG_MIN_SIMILARITY
from app.core.errors import ProviderFailure, ProviderUnavailable
from app.database import SessionLocal
from app.services.embedding_provider import EmbeddingProvider
from app.services.embedding_provider import configured_provider as get_embedding_provider

logger = logging.getLogger(__name__)


@contextmanager
def _session_scope(factory_or_session):
    if isinstance(factory_or_session, Session):
        yield factory_or_session
    elif callable(factory_or_session):
        obj = factory_or_session()
        if isinstance(obj, Session) and factory_or_session is SessionLocal:
            try:
                yield obj
            finally:
                obj.close()
        else:
            yield obj
    else:
        yield factory_or_session


class KnowledgeIngestionService:
    """Service for ingesting knowledge base files into the vector store."""

    def __init__(self, db_session_factory=SessionLocal):
        self.db_session_factory = db_session_factory
        self.embedding_provider: EmbeddingProvider = get_embedding_provider()

    def _compute_checksum(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _chunk_markdown(
        self, content: str, source_id: str, source_title: str, section: str
    ) -> List[dict]:
        """Simple markdown-aware chunking.

        Splits by headings (#, ##, etc.) and then by paragraphs if needed.
        For demo purposes, we'll just split by double newline and limit chunk size.
        """
        lines = content.split("\n")
        chunks = []
        current_chunk = []
        current_length = 0
        target_length = 500  # characters per chunk

        for line in lines:
            line = line.strip()
            if not line:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                continue
            current_chunk.append(line)
            current_length += len(line) + 1  # +1 for newline
            if current_length >= target_length:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_length = 0

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        # Convert to chunk dicts with metadata
        result = []
        for i, chunk_content in enumerate(chunks):
            chunk_id = f"{source_id}-{i:03d}"
            result.append(
                {
                    "id": chunk_id,
                    "content": chunk_content,
                    "metadata": {
                        "source_id": source_id,
                        "source_title": source_title,
                        "section": section,
                        "chunk_index": i,
                    },
                }
            )
        return result

    async def ingest_file(
        self,
        file_path: str,
        source_id: str,
        source_title: str,
        section: str,
        topic: str,
        specialty: Optional[str] = None,
        language: str = "en",
        document_version: str = "1.0-demo",
        source_reference: Optional[str] = None,
        force_reembed: bool = False,
    ) -> None:
        """Ingest a single markdown file into the knowledge base.

        Idempotent: updates existing chunks by deterministic ID/content rather than duplicating.
        Re-embeds if content changed, force_reembed is set, or provider/model changed.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        checksum = self._compute_checksum(content)
        chunks = self._chunk_markdown(content, source_id, source_title, section)

        provider_name = self.embedding_provider.name
        model_name = getattr(self.embedding_provider, "model", provider_name)
        expected_dim = getattr(self.embedding_provider, "dimension", None)

        with _session_scope(self.db_session_factory) as db:
            to_embed_entries = []
            for chunk in chunks:
                existing = (
                    db.query(models.KnowledgeChunk)
                    .filter(
                        (models.KnowledgeChunk.id == chunk["id"])
                        | (
                            (models.KnowledgeChunk.source_id == source_id)
                            & (models.KnowledgeChunk.section == section)
                            & (models.KnowledgeChunk.content == chunk["content"])
                        )
                    )
                    .first()
                )

                needs_embed = (
                    existing is None
                    or force_reembed
                    or existing.checksum != checksum
                    or existing.embedding_provider != provider_name
                    or existing.embedding_model != model_name
                    or (expected_dim is not None and existing.embedding_dimension != expected_dim)
                )

                if needs_embed:
                    to_embed_entries.append((chunk, existing))

            # Batch embed all chunks that need fresh embeddings
            embeddings_map = {}
            if to_embed_entries:
                texts = [entry[0]["content"] for entry in to_embed_entries]
                embeddings = await self.embedding_provider.embed_documents(texts)
                for (chunk, _), emb in zip(to_embed_entries, embeddings):
                    embeddings_map[chunk["id"]] = emb

            for chunk in chunks:
                matching_entry = next((e for c, e in to_embed_entries if c["id"] == chunk["id"]), None)
                if chunk["id"] in embeddings_map:
                    emb = embeddings_map[chunk["id"]]
                    existing = matching_entry
                    if existing is None:
                        existing = (
                            db.query(models.KnowledgeChunk)
                            .filter(models.KnowledgeChunk.id == chunk["id"])
                            .first()
                        )
                    if existing:
                        existing.content = chunk["content"]
                        existing.checksum = checksum
                        existing.topic = topic
                        existing.specialty = specialty
                        existing.language = language
                        existing.document_version = document_version
                        existing.source_reference = source_reference
                        existing.set_embedding(emb, provider=provider_name, model=model_name)
                        db.add(existing)
                    else:
                        kc = models.KnowledgeChunk(
                            id=chunk["id"],
                            source_id=source_id,
                            source_title=source_title,
                            section=section,
                            content=chunk["content"],
                            topic=topic,
                            specialty=specialty,
                            language=language,
                            document_version=document_version,
                            source_reference=source_reference,
                            checksum=checksum,
                        )
                        kc.set_embedding(emb, provider=provider_name, model=model_name)
                        db.add(kc)
            db.commit()

    async def reembed_all(self, topic: Optional[str] = None) -> int:
        """Re-embed all knowledge chunks in the database using the active provider."""
        provider_name = self.embedding_provider.name
        model_name = getattr(self.embedding_provider, "model", provider_name)

        with _session_scope(self.db_session_factory) as db:
            query = db.query(models.KnowledgeChunk)
            if topic:
                query = query.filter(models.KnowledgeChunk.topic == topic)
            chunks = query.all()
            if not chunks:
                return 0

            texts = [c.content for c in chunks]
            embeddings = await self.embedding_provider.embed_documents(texts)
            for chunk, emb in zip(chunks, embeddings):
                chunk.set_embedding(emb, provider=provider_name, model=model_name)
                db.add(chunk)
            db.commit()
            return len(chunks)


class KnowledgeRetrievalService:
    """Service for retrieving relevant knowledge chunks."""

    def __init__(self, db_session_factory=SessionLocal):
        self.db_session_factory = db_session_factory
        self.embedding_provider: EmbeddingProvider = get_embedding_provider()

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math

        if len(a) != len(b) or len(a) == 0:
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    async def retrieve(
        self,
        query_text: str,
        topic: Optional[str] = None,
        language: str = "en",
        top_k: int = 4,
        min_similarity: Optional[float] = None,
    ) -> List[Tuple[models.KnowledgeChunk, float]]:
        """Retrieve top-k relevant chunks for a query.

        Returns a list of (chunk, similarity_score) tuples, sorted by similarity descending.
        Rejects incompatible stored vectors (dimension mismatch or conflicting provider).
        Fails open on provider unavailable/failure.
        """
        effective_min_sim = min_similarity if min_similarity is not None else RAG_MIN_SIMILARITY
        try:
            query_embedding = await self.embedding_provider.embed_query(query_text)
        except (ProviderUnavailable, ProviderFailure) as exc:
            logger.warning("RAG embedding retrieval failed open: %s", exc)
            return []

        query_dim = len(query_embedding)
        if query_dim == 0:
            logger.warning("Empty query embedding received; aborting retrieval")
            return []

        active_provider_name = self.embedding_provider.name

        with _session_scope(self.db_session_factory) as db:
            query = db.query(models.KnowledgeChunk).filter(
                models.KnowledgeChunk.language == language
            )
            if topic:
                query = query.filter(models.KnowledgeChunk.topic == topic)

            chunks = query.all()
            scored_chunks = []

            for chunk in chunks:
                # 1. Dimension compatibility check
                if chunk.embedding_dimension is not None and chunk.embedding_dimension != query_dim:
                    logger.warning(
                        "Skipping chunk %s due to dimension mismatch (stored=%d, query=%d)",
                        chunk.id,
                        chunk.embedding_dimension,
                        query_dim,
                    )
                    continue

                # 2. Provider compatibility check (when not in mock test mode)
                if chunk.embedding_provider is not None and active_provider_name != "mock":
                    if chunk.embedding_provider != active_provider_name:
                        logger.warning(
                            "Skipping chunk %s due to provider mismatch (stored=%s, active=%s)",
                            chunk.id,
                            chunk.embedding_provider,
                            active_provider_name,
                        )
                        continue

                # 3. Vector length verification from deserialized data
                try:
                    chunk_embedding = chunk.get_embedding()
                except Exception as err:
                    logger.warning("Skipping chunk %s: failed to deserialize embedding (%s)", chunk.id, err)
                    continue

                if len(chunk_embedding) != query_dim:
                    logger.warning(
                        "Skipping chunk %s due to actual vector length mismatch (%d vs %d)",
                        chunk.id,
                        len(chunk_embedding),
                        query_dim,
                    )
                    continue

                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                if similarity >= effective_min_sim:
                    scored_chunks.append((chunk, similarity))

            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            return scored_chunks[:top_k]




class RAGGenerationService:
    """Service for generating grounded suggestions using an LLM."""

    def __init__(self):
        # We'll reuse the existing normalization provider abstraction for generation?
        # Actually, generation is different. We'll use the same provider pattern but for generation.
        # For now, we'll use a mock generator that returns a templated response.
        # In a real implementation, we would plug into NVIDIA or Sarvam generation.
        pass

    def suggest_questions(
        self,
        structured_facts: dict,
        retrieved_chunks: List[Tuple[models.KnowledgeChunk, float]],
    ) -> List[dict]:
        """Generate grounded follow-up question suggestions.

        Args:
            structured_facts: The normalized patient facts (e.g., from normalization service).
            retrieved_chunks: List of (chunk, similarity) from retrieval.

        Returns:
            List of suggestion dicts, each with:
                - question: str
                - reason: str
                - source_chunk_ids: List[str]
                - origin: "rag"
        """
        if not retrieved_chunks:
            return []

        # For demo, we'll generate a simple question based on the chunks.
        # In a real implementation, we would prompt an LLM with the facts and chunks.
        # We'll use a template-based approach for now to avoid LLM calls in the demo.

        suggestions: List[dict] = []
        seen_candidate_ids = set()

        for chunk, score in retrieved_chunks:
            content = chunk.content.lower()

            # 1. Shortness of breath / dyspnea (associated symptoms, history taking)
            if any(term in content for term in ["dyspnea", "shortness of breath", "breath"]):
                if "dyspnea" not in seen_candidate_ids:
                    seen_candidate_ids.add("dyspnea")
                    suggestions.append({
                        "candidate_id": "dyspnea",
                        "question": "Are you experiencing any shortness of breath or difficulty breathing?",
                        "reason": "Shortness of breath is an important associated symptom to evaluate in chest pain.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.associated_details",
                        "storage_field": "hpi.associated_details",
                        "concept": "DYSPNEA",
                        "target_concepts": ["DYSPNEA"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 2. Exertional provocation / worsening
            if any(term in content for term in ["exertion", "provocation", "walking"]):
                if "exertion" not in seen_candidate_ids:
                    seen_candidate_ids.add("exertion")
                    suggestions.append({
                        "candidate_id": "exertion",
                        "question": "Does the pain worsen with exertion, walking, or physical activity?",
                        "reason": "Exertional worsening helps differentiate cardiac ischemic pain from other etiologies.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.exacerbating",
                        "storage_field": "hpi.associated_details",
                        "concept": "EXERTION",
                        "target_concepts": ["EXERTION", "EXERTIONAL_WORSENING"],
                        "equivalent_fields": ["hpi.exacerbating", "hpi.provocation"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 3. Diaphoresis / sweating
            if any(term in content for term in ["diaphoresis", "sweating", "sweat"]):
                if "sweating" not in seen_candidate_ids:
                    seen_candidate_ids.add("sweating")
                    suggestions.append({
                        "candidate_id": "sweating",
                        "question": "Have you experienced heavy sweating or cold sweats along with the chest pain?",
                        "reason": "Sweating (diaphoresis) is an important autonomic sign in acute chest pain assessment.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.associated_details",
                        "storage_field": "hpi.associated_details",
                        "concept": "SWEATING",
                        "target_concepts": ["SWEATING", "DIAPHORESIS"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 4. Nausea / vomiting
            if any(term in content for term in ["nausea", "vomiting"]):
                if "nausea" not in seen_candidate_ids:
                    seen_candidate_ids.add("nausea")
                    suggestions.append({
                        "candidate_id": "nausea",
                        "question": "Have you had any nausea or vomiting accompanying the chest discomfort?",
                        "reason": "Nausea is a recognized associated autonomic symptom in cardiac chest pain presentations.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.associated_details",
                        "storage_field": "hpi.associated_details",
                        "concept": "NAUSEA",
                        "target_concepts": ["NAUSEA", "VOMITING"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 5. Dizziness / palpitations
            if any(term in content for term in ["dizziness", "lightheadedness", "palpitations", "syncope"]):
                if "dizziness" not in seen_candidate_ids:
                    seen_candidate_ids.add("dizziness")
                    suggestions.append({
                        "candidate_id": "dizziness",
                        "question": "Have you felt dizzy, lightheaded, or noticed a racing heartbeat?",
                        "reason": "Dizziness and palpitations help assess hemodynamic impact or arrhythmias.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.associated_details",
                        "storage_field": "hpi.associated_details",
                        "concept": "DIZZINESS",
                        "target_concepts": ["DIZZINESS", "SYNCOPE", "PALPITATIONS"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 6. Cough or fever (associated_symptoms-002: Less Common but Important)
            if any(term in content for term in ["cough", "fever", "abdominal"]):
                if "cough_fever" not in seen_candidate_ids:
                    seen_candidate_ids.add("cough_fever")
                    suggestions.append({
                        "candidate_id": "cough_fever",
                        "question": "Have you had a cough, fever, or abdominal pain alongside the chest discomfort?",
                        "reason": "Cough and fever help evaluate non-cardiac pulmonary or infectious causes.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.associated_details",
                        "storage_field": "hpi.associated_details",
                        "concept": "COUGH_FEVER",
                        "target_concepts": ["COUGH", "FEVER"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 7. Radiation
            if "radiat" in content:
                if "pain_radiation" not in seen_candidate_ids:
                    seen_candidate_ids.add("pain_radiation")
                    suggestions.append({
                        "candidate_id": "pain_radiation",
                        "question": "Does the pain radiate to your jaw, neck, back, or left arm?",
                        "reason": "Radiation pattern is an important diagnostic indicator in chest pain.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.radiation",
                        "storage_field": "hpi.associated_details",
                        "concept": "RADIATION",
                        "target_concepts": ["RADIATION"],
                        "equivalent_fields": ["hpi.radiation", "hpi.radiation_site"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

            # 8. Character / quality
            if any(term in content for term in ["character", "squeezing", "pressure", "burning", "sharp"]):
                if "pain_character" not in seen_candidate_ids:
                    seen_candidate_ids.add("pain_character")
                    suggestions.append({
                        "candidate_id": "pain_character",
                        "question": "Can you describe the pain in more detail?",
                        "reason": "Understanding the quality and pattern of chest discomfort.",
                        "source_chunk_ids": [chunk.id],
                        "origin": "rag",
                        "target_field": "hpi.character",
                        "storage_field": "hpi.associated_details",
                        "concept": "PRESSURE_LIKE_PAIN",
                        "target_concepts": ["PRESSURE_LIKE_PAIN", "SHARP_PAIN", "BURNING_PAIN"],
                        "equivalent_fields": ["hpi.character"],
                        "similarity_score": score,
                        "source_title": chunk.source_title,
                        "source_section": chunk.section,
                    })

        return suggestions


def get_ingestion_service() -> KnowledgeIngestionService:
    return KnowledgeIngestionService()


def get_retrieval_service() -> KnowledgeRetrievalService:
    return KnowledgeRetrievalService()


def get_generation_service() -> RAGGenerationService:
    return RAGGenerationService()