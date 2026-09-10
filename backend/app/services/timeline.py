"""Deterministic, computed clinical timeline built from source-linked facts."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.medical_fact import FactSource, TimelineEntry, TimelineResponse
from app.services import intake, medical_facts

TIMELINE_NAMESPACE = uuid.UUID("66176f09-f779-42d2-af5a-c25adb211697")


def _entry_id(*parts: object) -> str:
    return str(uuid.uuid5(TIMELINE_NAMESPACE, "|".join(str(part) for part in parts)))


def _fact_source(record) -> FactSource:
    return record.source


def get_timeline(db: Session, session_id: str) -> TimelineResponse:
    intake.get_session(db, session_id)
    intake.require_consent(db, session_id)
    facts = medical_facts.get_current_facts(db, session_id)
    entries: list[TimelineEntry] = []

    documents = list(
        db.scalars(
            select(models.Document)
            .where(models.Document.session_id == session_id)
            .order_by(models.Document.created_at, models.Document.id)
        )
    )
    for document in documents:
        extractions = sorted(document.extractions, key=lambda row: (str(row.created_at), row.id))
        extraction = next(
            (row for row in extractions if row.verification_status != "rejected"), None
        )
        if extractions and extraction is None:
            continue
        verification = extraction.verification_status if extraction else "unverified"
        entries.append(
            TimelineEntry(
                id=_entry_id("document", document.id),
                event_type="document",
                canonical_label=f"Document: {document.document_type.replace('_', ' ')}",
                event_timestamp=document.document_date,
                date_status="known" if document.document_date else "unknown",
                date_precision="day" if document.document_date else "unknown",
                source=FactSource(
                    source_type="document",
                    source_id=document.id,
                    document_id=document.id,
                    extraction_id=extraction.id if extraction else None,
                    document_filename=document.original_filename,
                    raw_text=extraction.raw_text if extraction else None,
                ),
                verification_status=verification,
            )
        )

    for fact in facts.medications:
        value = fact.current
        dates = [
            ("medication_started", "Medication started", value.start_date),
            ("medication_ended", "Medication ended", value.end_date),
        ]
        known_dates = [(kind, prefix, date) for kind, prefix, date in dates if date is not None]
        if known_dates:
            for kind, prefix, date in known_dates:
                entries.append(
                    TimelineEntry(
                        id=_entry_id(kind, fact.id),
                        event_type=kind,
                        canonical_label=f"{prefix}: {value.name}",
                        event_timestamp=date,
                        date_status="known",
                        date_precision="day",
                        source=_fact_source(fact),
                        verification_status=fact.verification_status,
                    )
                )
        else:
            entries.append(
                TimelineEntry(
                    id=_entry_id("medication", fact.id),
                    event_type="medication",
                    canonical_label=f"Medication: {value.name}",
                    event_timestamp=None,
                    date_status="unknown",
                    date_precision="unknown",
                    source=_fact_source(fact),
                    verification_status=fact.verification_status,
                )
            )

    for fact in facts.labs:
        value = fact.current
        entries.append(
            TimelineEntry(
                id=_entry_id("lab", fact.id),
                event_type="lab_observation",
                canonical_label=f"Lab: {value.test_name}",
                event_timestamp=value.observation_timestamp,
                date_status="known" if value.observation_timestamp else "unknown",
                date_precision="datetime" if value.observation_timestamp else "unknown",
                source=_fact_source(fact),
                verification_status=fact.verification_status,
            )
        )

    known = sorted(
        (entry for entry in entries if entry.date_status != "unknown"),
        key=lambda entry: (
            entry.event_timestamp.isoformat() if entry.event_timestamp else "",
            entry.event_type,
            entry.canonical_label.casefold(),
            entry.id,
        ),
    )
    unknown = sorted(
        (entry for entry in entries if entry.date_status == "unknown"),
        key=lambda entry: (entry.event_type, entry.canonical_label.casefold(), entry.id),
    )
    return TimelineResponse(known_date=known, unknown_date=unknown)
