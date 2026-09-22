"""Deterministic, patient-scoped retrieval over persisted document-derived facts."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.medical_fact import (
    PatientEvidenceSearchResponse,
    PatientEvidenceSearchResult,
)
from app.services import medical_facts

_STOP_WORDS = {
    "a", "an", "and", "are", "document", "documents", "evidence", "find", "from",
    "in", "is", "mentioned", "patient", "related", "relevant", "show", "the", "this",
    "uploaded", "what",
}
_MEDICATION_TERMS = {"medication", "medications", "medicine", "medicines", "prescription"}
_LAB_TERMS = {"lab", "labs", "laboratory", "observation", "observations", "test", "tests"}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _confirmation_status(db: Session, session_id: str, label: str) -> str:
    needle = label.lower()
    rows = db.scalars(
        select(models.ClinicalEvidence).where(models.ClinicalEvidence.session_id == session_id)
    )
    for row in rows:
        haystack = " ".join(
            str(value or "")
            for value in (row.original_text, row.normalized_text, row.value_json)
        ).lower()
        if needle in haystack and row.verification_status in {
            "patient_confirmed",
            "clinician_verified",
        }:
            return row.verification_status.replace("_", " ").title()
    return "Needs verification"


def _score(query_tokens: set[str], text: str, category_match: bool) -> float:
    fact_tokens = _tokens(text)
    overlap = len(query_tokens & fact_tokens)
    if not overlap and not category_match:
        return 0.0
    return min(1.0, 0.45 + (0.2 * overlap) + (0.2 if category_match else 0.0))


def search(db: Session, session_id: str, query: str, top_k: int = 5):
    """Return only facts owned by ``session_id`` with their persisted provenance."""
    facts = medical_facts.get_current_facts(db, session_id)
    query_tokens = _tokens(query)
    wants_medications = bool(query_tokens & _MEDICATION_TERMS)
    wants_labs = bool(query_tokens & _LAB_TERMS)
    results: list[PatientEvidenceSearchResult] = []

    for record in facts.medications:
        value = record.current
        details = {
            "medication": value.name,
            "dose": " ".join(part for part in (value.dosage, value.unit) if part) or None,
            "frequency": value.frequency,
            "route": value.route,
        }
        searchable = " ".join(str(item or "") for item in details.values())
        score = _score(query_tokens, searchable, wants_medications)
        if score:
            results.append(
                PatientEvidenceSearchResult(
                    fact_id=record.id,
                    fact_type="medication",
                    label=value.name,
                    details=details,
                    verification_status=record.verification_status,
                    patient_confirmation=_confirmation_status(db, session_id, value.name),
                    source_document_id=record.source.document_id,
                    source_filename=record.source.document_filename,
                    source_extraction_id=record.source.extraction_id,
                    source_text=record.source.raw_text,
                    source_location=record.source.source_location,
                    score=score,
                )
            )

    for record in facts.labs:
        value = record.current
        details = {
            "test": value.test_name,
            "value": " ".join(part for part in (value.value, value.unit) if part),
            "reference_range": value.reference_range,
            "flag": value.flag,
        }
        searchable = " ".join(str(item or "") for item in details.values())
        score = _score(query_tokens, searchable, wants_labs)
        if score:
            results.append(
                PatientEvidenceSearchResult(
                    fact_id=record.id,
                    fact_type="lab",
                    label=value.test_name,
                    details=details,
                    verification_status=record.verification_status,
                    patient_confirmation=_confirmation_status(db, session_id, value.test_name),
                    source_document_id=record.source.document_id,
                    source_filename=record.source.document_filename,
                    source_extraction_id=record.source.extraction_id,
                    source_text=record.source.raw_text,
                    source_location=record.source.source_location,
                    score=score,
                )
            )

    results.sort(key=lambda item: (-item.score, item.label.lower(), item.fact_id))
    return PatientEvidenceSearchResponse(query=query, results=results[:top_k])
