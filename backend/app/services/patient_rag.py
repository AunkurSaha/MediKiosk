"""Persistent, patient-scoped retrieval over canonical MediKiosk evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from sqlalchemy import bindparam, cast, delete, select
from sqlalchemy.orm import Session

from app import models
from app.core.config import (
    RAG_EMBEDDING_BATCH_SIZE,
    configured_indexing_provider,
    configured_search_provider,
)
from app.core.errors import ProviderFailure, ProviderUnavailable, WorkflowError
from app.schemas.patient_rag import (
    PatientRAGEvidence,
    PatientRAGIndexStatus,
    PatientRAGSearchRequest,
    PatientRAGSearchResponse,
)
from app.services.embedding_provider import (
    EmbeddingProvider,
    configured_provider,
    provider_identity,
    validate_embedding_vector,
)

NO_EVIDENCE = "No supporting patient evidence was found."
ALLOWED_SOURCE_TYPES = {
    "INTERVIEW_ANSWER",
    "CLINICAL_EVIDENCE",
    "MEDICAL_FACT",
    "PRESCRIPTION",
    "LAB_RESULT",
    "DISCHARGE_DOCUMENT",
    "TIMELINE_EVENT",
    "CLINICAL_SUMMARY",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "about",
    "any",
    "are",
    "does",
    "evidence",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "patient",
    "recorded",
    "relevant",
    "show",
    "the",
    "this",
    "what",
}


@dataclass
class CanonicalChunk:
    patient_id: str
    session_id: str | None
    source_type: str
    source_record_id: str
    chunk_key: str
    text: str
    evidence_type: str
    verification_status: str
    document_id: str | None = None
    page_number: int | None = None
    normalized_text: str | None = None
    provenance: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    event_at: datetime | None = None
    clinician_verified: bool = False
    is_current: bool = True
    is_conflicted: bool = False

    @property
    def checksum(self) -> str:
        payload = {
            "text": self.text,
            "normalized_text": self.normalized_text,
            "verification_status": self.verification_status,
            "provenance": self.provenance,
            "metadata": self.metadata,
            "current": self.is_current,
            "conflicted": self.is_conflicted,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class PatientEmbeddingBackfillResult:
    patient_id: str
    provider_name: str
    provider_model: str
    provider_version: str
    provider_dimension: int
    dry_run: bool
    canonical_chunk_count: int
    already_indexed: int
    retried_failed: int
    refreshed_stale: int
    created_missing: int
    pending_count: int
    failed_before_count: int
    missing_count: int
    stale_count: int
    would_embed: int
    embedded_count: int
    failed_count: int
    skipped_count: int
    estimated_batches: int
    coverage_before: float
    coverage_after: float
    ready_before: bool
    ready_after: bool


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value.lower()) if token not in _STOP}


def _value_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return value
        return _value_text(parsed)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_value_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_value_text(item) for item in value)
    return str(value)


def _document_source(document_type: str) -> str:
    if document_type == "prescription":
        return "PRESCRIPTION"
    if document_type == "lab_report":
        return "LAB_RESULT"
    return "DISCHARGE_DOCUMENT"


def _verification(value: str | None) -> str:
    return (value or "unverified").upper()


def _meaningful_paragraphs(raw_text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", raw_text) if part.strip()]
    if not paragraphs and raw_text.strip():
        paragraphs = [raw_text.strip()]
    return paragraphs


def build_patient_chunks(db: Session, patient_id: str) -> list[CanonicalChunk]:
    """Project canonical records into clinically meaningful, source-linked chunks."""
    sessions = list(
        db.scalars(
            select(models.Session)
            .where(models.Session.patient_id == patient_id)
            .order_by(models.Session.created_at, models.Session.id)
        )
    )
    session_ids = [row.id for row in sessions]
    if not session_ids:
        return []
    latest_session_id = sessions[-1].id

    chunks: list[CanonicalChunk] = []
    conflicted_ids = set(
        db.scalars(
            select(models.ClinicalEvidenceConflict.evidence_a_id).where(
                models.ClinicalEvidenceConflict.evidence_a_id.in_(
                    select(models.ClinicalEvidence.id).where(
                        models.ClinicalEvidence.patient_id == patient_id
                    )
                )
            )
        )
    ) | set(
        db.scalars(
            select(models.ClinicalEvidenceConflict.evidence_b_id).where(
                models.ClinicalEvidenceConflict.evidence_b_id.in_(
                    select(models.ClinicalEvidence.id).where(
                        models.ClinicalEvidence.patient_id == patient_id
                    )
                )
            )
        )
    )

    answers = db.scalars(
        select(models.InterviewAnswer).where(models.InterviewAnswer.session_id.in_(session_ids))
    )
    for row in answers:
        raw = row.raw_value or _value_text(row.value_json)
        if not raw.strip():
            continue
        chunks.append(
            CanonicalChunk(
                patient_id=patient_id,
                session_id=row.session_id,
                source_type="INTERVIEW_ANSWER",
                source_record_id=row.id,
                chunk_key="answer",
                text=f"{row.field.replace('_', ' ').title()}: {raw}\nSource: Patient interview.",
                evidence_type="interview",
                verification_status=_verification(row.verification_status),
                provenance={"question_id": row.question_id, "input_source": row.source},
                metadata={"field": row.field, "language": row.language},
                event_at=row.updated_at or row.created_at,
                clinician_verified=row.verification_status == "clinician_verified",
                is_current=row.session_id == latest_session_id,
            )
        )

    evidence_rows = db.scalars(
        select(models.ClinicalEvidence).where(models.ClinicalEvidence.patient_id == patient_id)
    )
    for row in evidence_rows:
        value = row.normalized_text or row.original_text or _value_text(row.value_json)
        if not value.strip():
            continue
        metadata = dict(row.metadata_json or {})
        evidence_type = (
            "medication"
            if row.concept_code == "MEDICATION_MENTION"
            else "allergy"
            if row.concept_code and "ALLERG" in row.concept_code.upper()
            else "clinical_evidence"
        )
        chunks.append(
            CanonicalChunk(
                patient_id=patient_id,
                session_id=row.session_id,
                source_type="CLINICAL_EVIDENCE",
                source_record_id=row.id,
                chunk_key=row.stable_key,
                text=(
                    f"Clinical evidence: {value}\nVerification: "
                    f"{row.verification_status.replace('_', ' ')}."
                ),
                normalized_text=row.normalized_text,
                evidence_type=evidence_type,
                verification_status=_verification(row.verification_status),
                document_id=metadata.get("document_id"),
                page_number=metadata.get("page_number"),
                provenance={
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "stable_key": row.stable_key,
                },
                metadata={"concept_code": row.concept_code, **metadata},
                event_at=row.verified_at or row.updated_at or row.created_at,
                clinician_verified=row.verification_status == "CLINICIAN_VERIFIED",
                is_current=row.session_id == latest_session_id,
                is_conflicted=row.id in conflicted_ids,
            )
        )

    document_rows = db.execute(
        select(models.DocumentExtraction, models.Document)
        .join(models.Document, models.Document.id == models.DocumentExtraction.document_id)
        .where(models.Document.session_id.in_(session_ids))
    )
    extraction_documents: dict[str, models.Document] = {}
    for extraction, document in document_rows:
        extraction_documents[extraction.id] = document
        for index, paragraph in enumerate(_meaningful_paragraphs(extraction.raw_text or "")):
            chunks.append(
                CanonicalChunk(
                    patient_id=patient_id,
                    session_id=extraction.session_id,
                    source_type=_document_source(document.document_type),
                    source_record_id=extraction.id,
                    chunk_key=f"paragraph:{index}",
                    text=paragraph,
                    evidence_type="document",
                    verification_status=_verification(extraction.verification_status),
                    document_id=document.id,
                    provenance={
                        "extractor": extraction.extractor,
                        "extractor_version": extraction.extractor_version,
                        "ocr_confidence": extraction.confidence,
                    },
                    metadata={
                        "filename": document.original_filename,
                        "document_type": document.document_type,
                    },
                    event_at=document.document_date or extraction.created_at,
                    clinician_verified=extraction.verification_status == "verified",
                    is_current=extraction.session_id == latest_session_id,
                )
            )

    medications = db.scalars(
        select(models.MedicationFact).where(models.MedicationFact.session_id.in_(session_ids))
    )
    for row in medications:
        document = extraction_documents.get(row.document_extraction_id)
        parts = [f"Medication: {row.name}"]
        if row.dosage or row.unit:
            parts.append(f"Strength: {' '.join(x for x in (row.dosage, row.unit) if x)}")
        if row.frequency:
            parts.append(f"Frequency: {row.frequency}")
        if row.duration:
            parts.append(f"Duration: {row.duration}")
        parts.append(f"Verification: {row.verification_status}")
        chunks.append(
            CanonicalChunk(
                patient_id=patient_id,
                session_id=row.session_id,
                source_type="MEDICAL_FACT",
                source_record_id=row.id,
                chunk_key="medication",
                text="\n".join(parts),
                normalized_text=row.name,
                evidence_type="medication",
                verification_status=_verification(row.verification_status),
                document_id=document.id if document else None,
                provenance={
                    "document_extraction_id": row.document_extraction_id,
                    "source_text": row.source_text,
                    "source_location": row.source_location,
                },
                metadata={
                    "label": row.name,
                    "dose": " ".join(x for x in (row.dosage, row.unit) if x) or None,
                    "frequency": row.frequency,
                    "duration": row.duration,
                    "filename": document.original_filename if document else None,
                },
                event_at=row.start_date or row.updated_at or row.created_at,
                clinician_verified=row.verification_status == "verified",
                is_current=row.session_id == latest_session_id and row.end_date is None,
            )
        )

    labs = db.scalars(select(models.LabFact).where(models.LabFact.session_id.in_(session_ids)))
    for row in labs:
        document = extraction_documents.get(row.document_extraction_id)
        value = " ".join(item for item in (row.value, row.unit) if item)
        chunks.append(
            CanonicalChunk(
                patient_id=patient_id,
                session_id=row.session_id,
                source_type="LAB_RESULT",
                source_record_id=row.id,
                chunk_key="observation",
                text=(
                    f"Test: {row.test_name}\nValue: {value}\n"
                    f"Reference range: {row.reference_range or 'unknown'}\n"
                    f"Verification: {row.verification_status}"
                ),
                normalized_text=row.test_name,
                evidence_type="lab",
                verification_status=_verification(row.verification_status),
                document_id=document.id if document else None,
                provenance={"source_text": row.source_text, "source_location": row.source_location},
                metadata={
                    "label": row.test_name,
                    "value": value,
                    "reference_range": row.reference_range,
                    "flag": row.flag,
                    "filename": document.original_filename if document else None,
                },
                event_at=row.observation_timestamp or row.updated_at or row.created_at,
                clinician_verified=row.verification_status == "verified",
                is_current=row.session_id == latest_session_id,
            )
        )

    summaries = db.scalars(
        select(models.ClinicalSummary).where(models.ClinicalSummary.session_id.in_(session_ids))
    )
    for row in summaries:
        summary_text = row.confirmed_text or row.reviewed_text or row.generated_text
        if not summary_text:
            continue
        confirmed = bool(row.confirmed_text)
        chunks.append(
            CanonicalChunk(
                patient_id=patient_id,
                session_id=row.session_id,
                source_type="CLINICAL_SUMMARY",
                source_record_id=row.id,
                chunk_key=f"version:{row.version}",
                text=summary_text,
                evidence_type="summary",
                verification_status="CLINICIAN_VERIFIED" if confirmed else "UNVERIFIED",
                provenance={"summary_version": row.version, "status": row.status},
                event_at=row.confirmed_at or row.reviewed_at or row.generated_at or row.created_at,
                clinician_verified=confirmed,
                is_current=row.session_id == latest_session_id,
            )
        )
    return chunks


def _stable_id(
    chunk: CanonicalChunk,
    provider_name: str,
    provider_model: str,
    provider_version: str,
) -> str:
    return str(
        uuid.uuid5(
            uuid.UUID("aa86bba4-45fd-4cf1-902f-4e3081485ab5"),
            (
                f"{chunk.source_type}:{chunk.source_record_id}:{chunk.chunk_key}:"
                f"{provider_name}:{provider_model}:{provider_version}"
            ),
        )
    )


def _sync_representation_metadata(
    row: models.PatientRAGChunk,
    chunk: CanonicalChunk,
    *,
    provider_name: str,
    provider_model: str,
    provider_version: str,
    provider_dimension: int,
    now: datetime,
) -> None:
    row.patient_id = chunk.patient_id
    row.session_id = chunk.session_id
    row.source_type = chunk.source_type
    row.source_record_id = chunk.source_record_id
    row.chunk_key = chunk.chunk_key
    row.document_id = chunk.document_id
    row.page_number = chunk.page_number
    row.text = chunk.text
    row.normalized_text = chunk.normalized_text
    row.evidence_type = chunk.evidence_type
    row.verification_status = chunk.verification_status
    row.provenance_json = chunk.provenance
    row.metadata_json = chunk.metadata
    row.event_at = chunk.event_at
    row.clinician_verified = chunk.clinician_verified
    row.is_current = chunk.is_current
    row.is_conflicted = chunk.is_conflicted
    row.embedding_provider = provider_name
    row.embedding_model = provider_model
    row.embedding_version = provider_version
    row.embedding_dimension = provider_dimension
    row.content_checksum = chunk.checksum
    row.embedding = None
    row.index_status = "pending"
    row.index_error = None
    row.updated_at = now


def _safe_index_error(exc: Exception) -> str:
    if isinstance(exc, ProviderFailure):
        reason = str(exc.reason)
        if reason.replace("_", "").replace("-", "").isalnum() and len(reason) <= 80:
            return reason
        return "provider_failure"
    if isinstance(exc, ProviderUnavailable):
        return "provider_unavailable"
    if isinstance(exc, ValueError):
        return "invalid_provider_result"
    return "provider_error"


async def backfill_patient_embeddings(
    db: Session,
    patient_id: str,
    provider: EmbeddingProvider,
    *,
    dry_run: bool = False,
    batch_size: int | None = None,
) -> PatientEmbeddingBackfillResult:
    """Safely create or refresh one provider's rows for one patient."""
    from app.services.patient_rag_coverage import get_patient_embedding_coverage

    provider_name, provider_model, provider_version, provider_dimension = (
        provider_identity(provider)
    )
    effective_batch_size = (
        RAG_EMBEDDING_BATCH_SIZE if batch_size is None else batch_size
    )
    if (
        not isinstance(effective_batch_size, int)
        or isinstance(effective_batch_size, bool)
        or effective_batch_size <= 0
    ):
        raise ValueError("batch_size must be a positive integer")

    with db.no_autoflush:
        canonical_by_key = {
            (chunk.source_type, chunk.source_record_id, chunk.chunk_key): chunk
            for chunk in build_patient_chunks(db, patient_id)
        }
        coverage_before = get_patient_embedding_coverage(db, patient_id, provider)
        rows = list(
            db.scalars(
                select(models.PatientRAGChunk).where(
                    models.PatientRAGChunk.patient_id == patient_id,
                    models.PatientRAGChunk.embedding_provider == provider_name,
                    models.PatientRAGChunk.embedding_model == provider_model,
                    models.PatientRAGChunk.embedding_version == provider_version,
                )
            )
        )

    row_by_key = {
        (row.source_type, row.source_record_id, row.chunk_key): row for row in rows
    }
    work: list[tuple[CanonicalChunk, models.PatientRAGChunk | None, str]] = []
    already_indexed = 0
    failed_before_count = 0
    pending_count = 0
    missing_count = 0
    stale_count = 0

    for key, chunk in canonical_by_key.items():
        row = row_by_key.get(key)
        valid_indexed = False
        if (
            row is not None
            and row.embedding_dimension == provider_dimension
            and row.content_checksum == chunk.checksum
            and row.index_status == "indexed"
        ):
            try:
                validate_embedding_vector(row.embedding, provider_dimension)
                valid_indexed = True
            except (ProviderFailure, TypeError, ValueError):
                valid_indexed = False
        if valid_indexed:
            already_indexed += 1
            continue
        if row is None:
            category = "missing"
            missing_count += 1
        elif (
            row.embedding_dimension != provider_dimension
            or row.content_checksum != chunk.checksum
        ):
            category = "stale"
            stale_count += 1
        elif row.index_status == "pending":
            category = "pending"
            pending_count += 1
        else:
            category = "failed"
            failed_before_count += 1
        work.append((chunk, row, category))

    would_embed = len(work)
    estimated_batches = (
        (would_embed + effective_batch_size - 1) // effective_batch_size
        if would_embed
        else 0
    )
    if dry_run:
        return PatientEmbeddingBackfillResult(
            patient_id=patient_id,
            provider_name=provider_name,
            provider_model=provider_model,
            provider_version=provider_version,
            provider_dimension=provider_dimension,
            dry_run=True,
            canonical_chunk_count=len(canonical_by_key),
            already_indexed=already_indexed,
            retried_failed=0,
            refreshed_stale=0,
            created_missing=0,
            pending_count=pending_count,
            failed_before_count=failed_before_count,
            missing_count=missing_count,
            stale_count=stale_count,
            would_embed=would_embed,
            embedded_count=0,
            failed_count=0,
            skipped_count=already_indexed,
            estimated_batches=estimated_batches,
            coverage_before=coverage_before.coverage_percent,
            coverage_after=coverage_before.coverage_percent,
            ready_before=coverage_before.ready_for_search,
            ready_after=coverage_before.ready_for_search,
        )

    now = datetime.now(timezone.utc)
    prepared: list[tuple[CanonicalChunk, models.PatientRAGChunk, str]] = []
    for chunk, row, category in work:
        if row is None:
            row = models.PatientRAGChunk(
                id=_stable_id(chunk, provider_name, provider_model, provider_version)
            )
            db.add(row)
        _sync_representation_metadata(
            row,
            chunk,
            provider_name=provider_name,
            provider_model=provider_model,
            provider_version=provider_version,
            provider_dimension=provider_dimension,
            now=now,
        )
        prepared.append((chunk, row, category))

    # Identity, checksum, dimension and pending status are persisted in the unit
    # of work before any external provider call is attempted.
    db.flush()
    embedded_count = 0
    failed_count = 0
    for offset in range(0, len(prepared), effective_batch_size):
        batch = prepared[offset : offset + effective_batch_size]
        try:
            vectors = await provider.embed_documents([chunk.text for chunk, _row, _kind in batch])
        except Exception as exc:  # Provider adapters may wrap transport errors differently.
            reason = _safe_index_error(exc)
            for _chunk, row, _kind in batch:
                row.embedding = None
                row.index_status = "failed"
                row.index_error = reason
                row.last_indexed_at = now
                failed_count += 1
            continue

        if len(vectors) != len(batch):
            for _chunk, row, _kind in batch:
                row.embedding = None
                row.index_status = "failed"
                row.index_error = "result_count_mismatch"
                row.last_indexed_at = now
                failed_count += 1
            continue

        for (_chunk, row, _kind), vector in zip(batch, vectors, strict=True):
            try:
                cleaned = validate_embedding_vector(vector, provider_dimension)
            except (ProviderFailure, TypeError, ValueError) as exc:
                row.embedding = None
                row.index_status = "failed"
                row.index_error = _safe_index_error(exc)
                row.last_indexed_at = now
                failed_count += 1
                continue
            row.embedding = cleaned
            row.index_status = "indexed"
            row.index_error = None
            row.last_indexed_at = now
            embedded_count += 1

    db.commit()
    coverage_after = get_patient_embedding_coverage(db, patient_id, provider)
    return PatientEmbeddingBackfillResult(
        patient_id=patient_id,
        provider_name=provider_name,
        provider_model=provider_model,
        provider_version=provider_version,
        provider_dimension=provider_dimension,
        dry_run=False,
        canonical_chunk_count=len(canonical_by_key),
        already_indexed=already_indexed,
        retried_failed=failed_before_count,
        refreshed_stale=stale_count,
        created_missing=missing_count,
        pending_count=pending_count,
        failed_before_count=failed_before_count,
        missing_count=missing_count,
        stale_count=stale_count,
        would_embed=would_embed,
        embedded_count=embedded_count,
        failed_count=failed_count,
        skipped_count=already_indexed,
        estimated_batches=estimated_batches,
        coverage_before=coverage_before.coverage_percent,
        coverage_after=coverage_after.coverage_percent,
        ready_before=coverage_before.ready_for_search,
        ready_after=coverage_after.ready_for_search,
    )


async def reindex_patient(
    db: Session, patient_id: str, provider: EmbeddingProvider | None = None
) -> PatientRAGIndexStatus:
    provider = provider or configured_provider(configured_indexing_provider())
    canonical = build_patient_chunks(db, patient_id)
    provider_name, provider_model, provider_version, provider_dimension = (
        provider_identity(provider)
    )
    now = datetime.now(timezone.utc)
    active_keys: set[tuple[str, str, str]] = set()
    pending: list[tuple[CanonicalChunk, models.PatientRAGChunk]] = []

    for chunk in canonical:
        key = (chunk.source_type, chunk.source_record_id, chunk.chunk_key)
        active_keys.add(key)
        row = db.scalar(
            select(models.PatientRAGChunk).where(
                models.PatientRAGChunk.source_type == chunk.source_type,
                models.PatientRAGChunk.source_record_id == chunk.source_record_id,
                models.PatientRAGChunk.chunk_key == chunk.chunk_key,
                models.PatientRAGChunk.embedding_provider == provider_name,
                models.PatientRAGChunk.embedding_model == provider_model,
                models.PatientRAGChunk.embedding_version == provider_version,
            )
        )
        if row is None:
            row = models.PatientRAGChunk(
                id=_stable_id(
                    chunk, provider_name, provider_model, provider_version
                ),
                source_type=chunk.source_type,
                source_record_id=chunk.source_record_id,
                chunk_key=chunk.chunk_key,
                patient_id=chunk.patient_id,
                embedding_provider=provider_name,
                embedding_model=provider_model,
                embedding_version=provider_version,
            )
            db.add(row)
        changed = (
            row.content_checksum != chunk.checksum
            or row.embedding is None
            or row.embedding_dimension != provider_dimension
        )
        row.session_id = chunk.session_id
        row.document_id = chunk.document_id
        row.page_number = chunk.page_number
        row.text = chunk.text
        row.normalized_text = chunk.normalized_text
        row.evidence_type = chunk.evidence_type
        row.verification_status = chunk.verification_status
        row.provenance_json = chunk.provenance
        row.metadata_json = chunk.metadata
        row.event_at = chunk.event_at
        row.clinician_verified = chunk.clinician_verified
        row.is_current = chunk.is_current
        row.is_conflicted = chunk.is_conflicted
        row.embedding_provider = provider_name
        row.embedding_model = provider_model
        row.embedding_version = provider_version
        row.embedding_dimension = provider_dimension
        row.content_checksum = chunk.checksum
        row.updated_at = now
        if changed:
            row.embedding = None
            row.index_status = "pending"
            row.index_error = None
            pending.append((chunk, row))

    stale = list(
        db.scalars(
            select(models.PatientRAGChunk).where(
                models.PatientRAGChunk.patient_id == patient_id,
                models.PatientRAGChunk.embedding_provider == provider_name,
                models.PatientRAGChunk.embedding_model == provider_model,
                models.PatientRAGChunk.embedding_version == provider_version,
            )
        )
    )
    for row in stale:
        if (row.source_type, row.source_record_id, row.chunk_key) not in active_keys:
            db.delete(row)
    db.flush()

    if pending:
        try:
            vectors = await provider.embed_documents([chunk.text for chunk, _row in pending])
            if len(vectors) != len(pending):
                raise ProviderFailure("invalid_result")
            for (_chunk, row), vector in zip(pending, vectors, strict=True):
                row.embedding = validate_embedding_vector(vector, provider_dimension)
                row.embedding_provider = provider_name
                row.embedding_model = provider_model
                row.embedding_version = provider_version
                row.embedding_dimension = provider_dimension
                row.index_status = "indexed"
                row.index_error = None
                row.last_indexed_at = now
        except (ProviderFailure, ProviderUnavailable, TypeError, ValueError) as exc:
            for _chunk, row in pending:
                row.embedding = None
                row.index_status = "failed"
                row.index_error = _safe_index_error(exc)
                row.last_indexed_at = now
    db.commit()
    return index_status(db, patient_id)


def index_status(
    db: Session, patient_id: str, session_id: str | None = None
) -> PatientRAGIndexStatus:
    conditions = [models.PatientRAGChunk.patient_id == patient_id]
    if session_id:
        conditions.append(models.PatientRAGChunk.session_id == session_id)
    rows = list(db.scalars(select(models.PatientRAGChunk).where(*conditions)))
    return PatientRAGIndexStatus(
        patient_id=patient_id,
        session_id=session_id,
        canonical_records=len(build_patient_chunks(db, patient_id)),
        chunks_total=len(rows),
        chunks_embedded=sum(row.index_status == "indexed" for row in rows),
        chunks_failed=sum(row.index_status == "failed" for row in rows),
        embedding_provider=next((row.embedding_provider for row in rows if row.embedding_provider), None),
        embedding_model=next((row.embedding_model for row in rows if row.embedding_model), None),
        last_indexed_at=max(
            (row.last_indexed_at for row in rows if row.last_indexed_at), default=None
        ),
        failures=sorted({row.index_error for row in rows if row.index_error}),
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right, strict=True)) / denominator if denominator else 0.0


def classify_query(query: str) -> str:
    tokens = _tokens(query)
    if tokens & {"allergy", "allergies", "allergic"}:
        return "ALLERGY"
    if tokens & {"conflict", "conflicting", "discrepancy", "discrepancies"}:
        return "CONFLICT"
    if tokens & {"lab", "labs", "hba1c", "glucose", "test", "tests"}:
        return "LAB"
    medication_terms = {"medication", "medications", "medicine", "medicines", "metformin"}
    document_terms = {"document", "documents", "prescription", "uploaded"}
    if tokens & medication_terms and tokens & document_terms:
        return "DOCUMENT_MEDICATION"
    if tokens & medication_terms:
        return "MEDICATION_HISTORY" if tokens & {"history", "historical"} else "MEDICATION"
    if tokens & document_terms:
        return "DOCUMENT"
    if tokens & {"complaint", "chief"}:
        return "CHIEF_COMPLAINT"
    if tokens & {"timeline", "recent", "latest"}:
        return "TIMELINE"
    return "GENERAL_PATIENT_SEARCH"


def _intent_match(intent: str, row: models.PatientRAGChunk) -> float:
    if intent == "DOCUMENT_MEDICATION":
        return (
            1.0
            if row.document_id and row.evidence_type in {"document", "medication"}
            else 0.0
        )
    if intent.startswith("MEDICATION"):
        return 1.0 if row.evidence_type == "medication" else 0.0
    if intent == "ALLERGY":
        return 1.0 if row.evidence_type == "allergy" else 0.0
    if intent == "LAB":
        return 1.0 if row.evidence_type == "lab" else 0.0
    if intent == "DOCUMENT":
        return 1.0 if row.document_id or row.evidence_type == "document" else 0.0
    if intent == "CONFLICT":
        return 1.0 if row.is_conflicted else 0.0
    if intent == "CHIEF_COMPLAINT":
        field = str(row.metadata_json.get("field") or "")
        return 1.0 if field == "chief_complaint" or field.startswith("chief_complaint.") else 0.0
    return 0.25


def _verification_boost(row: models.PatientRAGChunk, intent: str) -> float:
    status = row.verification_status.upper()
    boost = 0.0
    if status == "CLINICIAN_VERIFIED":
        boost += 0.2
    elif status == "PATIENT_CONFIRMED":
        boost += 0.18
    elif status == "PATIENT_REPORTED":
        boost += 0.1
    if row.is_current and intent != "MEDICATION_HISTORY":
        boost += 0.08
    if row.is_conflicted and intent == "CONFLICT":
        boost += 0.12
    return boost


def _answer(intent: str, evidence: list[PatientRAGEvidence]) -> str:
    if not evidence:
        return NO_EVIDENCE
    if intent == "ALLERGY" and not any(item.metadata.get("evidence_type") == "allergy" for item in evidence):
        return NO_EVIDENCE
    if intent == "CONFLICT":
        if not any(item.is_conflicted for item in evidence):
            return NO_EVIDENCE
        return "Potentially conflicting patient records were found and require clinical review."
    if intent.startswith("MEDICATION"):
        medication = next((item for item in evidence if item.metadata.get("label")), evidence[0])
        label = medication.metadata.get("label") or medication.text.splitlines()[0].replace(
            "Medication: ", ""
        )
        dose = medication.metadata.get("dose")
        frequency = medication.metadata.get("frequency")
        display = " ".join(item for item in (label, dose, frequency) if item)
        confirmed = next(
            (
                item
                for item in evidence
                if item.verification_status in {"PATIENT_CONFIRMED", "CLINICIAN_VERIFIED"}
                and (label.lower() in item.text.lower())
            ),
            None,
        )
        if confirmed:
            status = (
                "clinician-verified"
                if confirmed.verification_status == "CLINICIAN_VERIFIED"
                else "patient-confirmed"
            )
            return f"{display} is recorded as {status} medication evidence."
        return (
            f"{display} was found in an uploaded document and remains unverified; "
            "current use is not confirmed."
        )
    if intent == "CHIEF_COMPLAINT":
        return evidence[0].text
    return f"{len(evidence)} supporting patient evidence item(s) were found."


def postgres_vector_statement(conditions, query_vector: list[float], limit: int):
    """Build the PostgreSQL ANN query with authorization scope in the SQL WHERE clause."""
    scoped = select(models.PatientRAGChunk).where(*conditions)
    if len(query_vector) == 2048:
        vector_parameter = bindparam(
            "patient_rag_query_vector", value=query_vector, type_=models.HalfVector2048()
        )
        distance = cast(models.PatientRAGChunk.embedding, models.HalfVector2048()).op(
            "<=>"
        )(vector_parameter)
    else:
        vector_parameter = bindparam(
            "patient_rag_query_vector", value=query_vector, type_=models.VectorValue()
        )
        distance = models.PatientRAGChunk.embedding.op("<=>")(vector_parameter)
    return (
        scoped.where(
            models.PatientRAGChunk.embedding.is_not(None),
            models.PatientRAGChunk.embedding_dimension == len(query_vector),
        )
        .order_by(distance)
        .limit(limit)
    )


async def search_patient(
    db: Session,
    session_id: str,
    payload: PatientRAGSearchRequest,
    provider: EmbeddingProvider | None = None,
) -> PatientRAGSearchResponse:
    started = perf_counter()
    session = db.get(models.Session, session_id)
    if session is None:
        raise WorkflowError("SESSION_NOT_FOUND", "Session not found.", 404)
    provider = provider or configured_provider(configured_search_provider())
    provider_name, provider_model, provider_version, provider_dimension = (
        provider_identity(provider)
    )
    # Refresh is idempotent and only embeds changed canonical records. Keeping this
    # in the read path guarantees that confirmations/reviews are visible even when
    # an optional embedding provider previously failed; canonical workflow writes
    # never depend on RAG succeeding.
    index_started = perf_counter()
    await reindex_patient(db, session.patient_id)
    index_ms = (perf_counter() - index_started) * 1000

    embedding_started = perf_counter()
    try:
        query_vector = await provider.embed_query(payload.query)
    except (ProviderFailure, ProviderUnavailable, ValueError):
        query_vector = []
    embedding_ms = (perf_counter() - embedding_started) * 1000

    conditions = [
        models.PatientRAGChunk.patient_id == session.patient_id,
        models.PatientRAGChunk.embedding_provider == provider_name,
        models.PatientRAGChunk.embedding_model == provider_model,
        models.PatientRAGChunk.embedding_version == provider_version,
        models.PatientRAGChunk.embedding_dimension == provider_dimension,
        models.PatientRAGChunk.index_status == "indexed",
    ]
    if payload.source_types:
        requested = {item.upper() for item in payload.source_types}
        if not requested <= ALLOWED_SOURCE_TYPES:
            raise WorkflowError("INVALID_RAG_FILTER", "Unsupported source type filter.", 422)
        conditions.append(models.PatientRAGChunk.source_type.in_(requested))
    if payload.verification_statuses:
        conditions.append(
            models.PatientRAGChunk.verification_status.in_(
                {item.upper() for item in payload.verification_statuses}
            )
        )
    if payload.document_id:
        conditions.append(models.PatientRAGChunk.document_id == payload.document_id)
    if payload.date_from:
        conditions.append(models.PatientRAGChunk.event_at >= payload.date_from)
    if payload.date_to:
        conditions.append(models.PatientRAGChunk.event_at <= payload.date_to)

    retrieval_started = perf_counter()
    scoped = select(models.PatientRAGChunk).where(*conditions)
    if db.bind is not None and db.bind.dialect.name == "postgresql" and query_vector:
        # The patient predicate is part of the vector database query. We never run
        # a global nearest-neighbour search and filter patient records afterward.
        vector_candidates = list(
            db.scalars(
                postgres_vector_statement(
                    conditions, query_vector, max(payload.top_k * 5, 30)
                )
            )
        )
        # A separately patient-scoped lexical candidate set protects exact doses,
        # abbreviations, medicine names, and lab values from semantic-search loss.
        lexical_candidates = list(db.scalars(scoped.limit(500)))
        rows = list({row.id: row for row in vector_candidates + lexical_candidates}.values())
    else:
        # SQLite E2E fallback: still scope in SQL, then use deterministic in-process
        # cosine/keyword scoring because SQLite has no pgvector operator.
        rows = list(db.scalars(scoped))
    intent = classify_query(payload.query)
    query_tokens = _tokens(payload.query)
    scored: list[tuple[models.PatientRAGChunk, float, float]] = []
    for row in rows:
        intent_match = _intent_match(intent, row)
        if intent in {"ALLERGY", "CONFLICT", "LAB", "CHIEF_COMPLAINT"} and not intent_match:
            continue
        row_tokens = _tokens(f"{row.text} {row.normalized_text or ''}")
        keyword = len(query_tokens & row_tokens) / max(1, len(query_tokens))
        vector_similarity = _cosine(query_vector, row.embedding or []) if query_vector else 0.0
        retrieval_support = (
            (0.5 * max(0.0, vector_similarity))
            + (0.3 * keyword)
            + (0.12 * intent_match)
        )

        # Intent/category matching and verification status may rank relevant
        # evidence, but must not make unrelated evidence relevant by themselves.
        has_retrieval_signal = (
            keyword >= 0.20
            or vector_similarity >= 0.20
        )
        if not has_retrieval_signal or retrieval_support < 0.13:
            continue

        score = retrieval_support + _verification_boost(row, intent)
        scored.append((row, vector_similarity, score))
    scored.sort(
        key=lambda item: (
            -item[2],
            -(item[0].event_at.timestamp() if item[0].event_at else 0),
            item[0].id,
        )
    )
    evidence = [
        PatientRAGEvidence(
            chunk_id=row.id,
            text=row.text,
            source_type=row.source_type,
            source_record_id=row.source_record_id,
            session_id=row.session_id,
            document_id=row.document_id,
            source_filename=row.metadata_json.get("filename"),
            page_number=row.page_number,
            verification_status=row.verification_status,
            timestamp=row.event_at,
            similarity=max(-1.0, min(1.0, similarity)),
            score=max(0.0, min(2.0, score)),
            clinician_verified=row.clinician_verified,
            is_current=row.is_current,
            is_conflicted=row.is_conflicted,
            provenance=row.provenance_json or {},
            metadata={"evidence_type": row.evidence_type, **(row.metadata_json or {})},
        )
        for row, similarity, score in scored[: payload.top_k]
    ]
    retrieval_ms = (perf_counter() - retrieval_started) * 1000
    compatibility_results = [
        {
            "fact_id": item.source_record_id,
            "fact_type": item.metadata.get("evidence_type", "clinical_evidence"),
            "label": item.metadata.get("label") or item.text.splitlines()[0].replace("Medication: ", ""),
            "details": {
                key: item.metadata.get(key)
                for key in ("medication", "dose", "frequency", "route", "test", "value", "reference_range", "flag")
                if item.metadata.get(key) is not None
            },
            "verification_status": item.verification_status.lower(),
            "patient_confirmation": item.verification_status.replace("_", " ").title(),
            "source_document_id": item.document_id,
            "source_filename": item.source_filename,
            "source_extraction_id": item.provenance.get("document_extraction_id"),
            "source_text": item.provenance.get("source_text"),
            "source_location": item.provenance.get("source_location"),
            "score": min(1.0, item.score),
        }
        for item in evidence
    ]
    return PatientRAGSearchResponse(
        answer=_answer(intent, evidence),
        evidence=evidence,
        patient_id=session.patient_id,
        query=payload.query,
        intent=intent,
        embedding_provider=provider.name,
        embedding_model=getattr(provider, "model", provider.name),
        index_latency_ms=round(index_ms, 3),
        embedding_latency_ms=round(embedding_ms, 3),
        retrieval_latency_ms=round(retrieval_ms, 3),
        total_latency_ms=round((perf_counter() - started) * 1000, 3),
        fallback_used=provider.name == "mock",
        results=compatibility_results,
    )


def clear_patient_index(db: Session, patient_id: str) -> int:
    result = db.execute(
        delete(models.PatientRAGChunk).where(models.PatientRAGChunk.patient_id == patient_id)
    )
    db.commit()
    return result.rowcount or 0
