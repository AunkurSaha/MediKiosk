"""Patient-scoped embedding coverage and search-readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import ProviderFailure
from app.services import patient_rag
from app.services.embedding_provider import provider_identity, validate_embedding_vector


class CoverageProvider(Protocol):
    """Provider identity required by the coverage calculation."""

    name: str
    model: str
    version: str
    dimension: int


@dataclass(frozen=True)
class PatientEmbeddingCoverage:
    patient_id: str
    provider_name: str
    provider_model: str
    provider_version: str
    provider_dimension: int
    canonical_chunk_count: int
    indexed_count: int
    pending_count: int
    failed_count: int
    missing_count: int
    stale_count: int
    coverage_percent: float
    ready_for_search: bool


def _provider_identity(provider: CoverageProvider) -> tuple[str, str, str, int]:
    return provider_identity(provider)


def _embedding_is_valid(value: object, expected_dimension: int) -> bool:
    try:
        validate_embedding_vector(value, expected_dimension)
        return True
    except (ProviderFailure, TypeError, ValueError):
        return False


def get_patient_embedding_coverage(
    db: Session,
    patient_id: str,
    provider: CoverageProvider,
) -> PatientEmbeddingCoverage:
    """Classify every current canonical chunk for one exact provider identity."""

    provider_name, provider_model, provider_version, provider_dimension = (
        _provider_identity(provider)
    )
    canonical_by_key = {
        (chunk.source_type, chunk.source_record_id, chunk.chunk_key): chunk
        for chunk in patient_rag.build_patient_chunks(db, patient_id)
    }

    # The patient predicate is deliberately part of the database query. Rows for
    # another patient and orphaned rows outside canonical_by_key cannot contribute.
    representations = list(
        db.scalars(
            select(models.PatientRAGChunk).where(
                models.PatientRAGChunk.patient_id == patient_id,
                models.PatientRAGChunk.embedding_provider == provider_name,
                models.PatientRAGChunk.embedding_model == provider_model,
                models.PatientRAGChunk.embedding_version == provider_version,
                models.PatientRAGChunk.embedding_dimension == provider_dimension,
            )
        )
    )
    representation_by_key = {
        (row.source_type, row.source_record_id, row.chunk_key): row
        for row in representations
    }

    indexed_count = 0
    pending_count = 0
    failed_count = 0
    missing_count = 0
    stale_count = 0

    for key, canonical in canonical_by_key.items():
        row = representation_by_key.get(key)
        if row is None:
            missing_count += 1
        elif row.content_checksum != canonical.checksum:
            stale_count += 1
        elif row.index_status == "pending":
            pending_count += 1
        elif row.index_status == "failed":
            failed_count += 1
        elif (
            row.index_status == "indexed"
            and row.embedding is not None
            and _embedding_is_valid(row.embedding, provider_dimension)
        ):
            indexed_count += 1
        else:
            # An exact but unusable current representation is operationally failed;
            # this keeps the five categories exhaustive without calling it missing.
            failed_count += 1

    canonical_chunk_count = len(canonical_by_key)
    coverage_percent = (
        0.0
        if canonical_chunk_count == 0
        else 100.0 * indexed_count / canonical_chunk_count
    )
    ready_for_search = (
        canonical_chunk_count > 0
        and indexed_count == canonical_chunk_count
        and pending_count == 0
        and failed_count == 0
        and missing_count == 0
        and stale_count == 0
    )

    return PatientEmbeddingCoverage(
        patient_id=patient_id,
        provider_name=provider_name,
        provider_model=provider_model,
        provider_version=provider_version,
        provider_dimension=provider_dimension,
        canonical_chunk_count=canonical_chunk_count,
        indexed_count=indexed_count,
        pending_count=pending_count,
        failed_count=failed_count,
        missing_count=missing_count,
        stale_count=stale_count,
        coverage_percent=coverage_percent,
        ready_for_search=ready_for_search,
    )
