"""Conservative deterministic comparisons of explicitly comparable evidence."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.document import StructuredDocument
from app.schemas.medical_fact import Discrepancy, DiscrepancyResponse, DiscrepancySource
from app.services import intake, medical_facts

DISCREPANCY_NAMESPACE = uuid.UUID("a244f2f7-24d8-466c-8198-cd30925744e1")
DOSE_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mcg|mg|g|ml|iu)\b", re.IGNORECASE)
FORM_PREFIX = re.compile(r"^(?:tab|tablet|cap|capsule|syp|syrup|inj|injection|oint)\s+", re.I)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _medication_name(value: str) -> str:
    return _normalized(FORM_PREFIX.sub("", value.strip()))


def _discrepancy_id(kind: str, source_a: str, source_b: str, reason: str) -> str:
    return str(uuid.uuid5(DISCREPANCY_NAMESPACE, "|".join((kind, source_a, source_b, reason))))


def _patient_source(answer, label: str | None = None) -> DiscrepancySource:
    return DiscrepancySource(
        source_type="patient_answer",
        source_id=answer.id,
        label=label or "Patient-reported history",
        displayed_value=answer.raw_value,
        raw_text=answer.raw_value,
    )


def _document_source(record, label: str, displayed_value: str) -> DiscrepancySource:
    return DiscrepancySource(
        source_type="document_fact",
        source_id=record.id,
        label=label,
        displayed_value=displayed_value,
        document_id=record.source.document_id,
        extraction_id=record.source.extraction_id,
        raw_text=record.source.raw_text,
    )


def _make(kind, source_a, source_b, reason):
    return Discrepancy(
        discrepancy_id=_discrepancy_id(kind, source_a.source_id, source_b.source_id, reason),
        type=kind,
        source_a=source_a,
        source_b=source_b,
        reason=reason,
    )


def _patient_medication_evidence(db: Session, session_id: str):
    answers = intake.latest_answers(db, session_id)
    details = [
        answer
        for answer in answers
        if answer.status == "answered"
        and answer.field in ("medications", "medications.details")
        and isinstance(answer.value, str)
    ]
    explicit_none = next(
        (
            answer
            for answer in answers
            if answer.status == "answered"
            and answer.field == "medications.any"
            and answer.value is False
        ),
        None,
    )
    return details, explicit_none


def _patient_dose(text: str, medication_name: str) -> str | None:
    normalized_name = _medication_name(medication_name)
    if not normalized_name:
        return None
    match = re.search(re.escape(normalized_name), _normalized(text))
    if match is None:
        return None
    direct = re.search(re.escape(normalized_name), text, re.IGNORECASE)
    if direct is None:
        return None
    window = text[direct.start() : direct.end() + 32]
    dose = DOSE_PATTERN.search(window)
    return re.sub(r"\s+", "", dose.group(0).casefold()) if dose else None


def _medication_discrepancies(db: Session, session_id: str, facts):
    items = []
    detail_answers, explicit_none = _patient_medication_evidence(db, session_id)
    if not detail_answers and explicit_none is None:
        return items
    combined = " ; ".join(answer.raw_value for answer in detail_answers)
    normalized_report = _normalized(combined)
    patient_source = (
        _patient_source(detail_answers[0], "Patient-reported medication list")
        if detail_answers
        else _patient_source(explicit_none, "Patient reported no current medication")
    )
    for fact in facts.medications:
        value = fact.current
        name = _medication_name(value.name)
        source = _document_source(fact, "Document-derived medication", value.name)
        if explicit_none is not None or name not in normalized_report:
            reason = (
                f"Patient-reported medication list does not include {value.name} "
                "found in a prescription document."
            )
            items.append(
                _make("MEDICATION_MISSING_FROM_PATIENT_REPORT", patient_source, source, reason)
            )
            continue
        patient_dose = _patient_dose(combined, value.name)
        document_dose_match = DOSE_PATTERN.search(
            " ".join(filter(None, (value.dosage, value.unit)))
        )
        document_dose = (
            re.sub(r"\s+", "", document_dose_match.group(0).casefold())
            if document_dose_match
            else None
        )
        if patient_dose and document_dose and patient_dose != document_dose:
            reason = f"Patient-reported and document-derived dosage text for {value.name} differ."
            items.append(_make("MEDICATION_MISMATCH", patient_source, source, reason))
    return items


def _allergy_discrepancies(db: Session, session_id: str):
    answers = intake.latest_answers(db, session_id)
    any_answer = next(
        (
            answer
            for answer in answers
            if answer.status == "answered" and answer.field == "allergies.any"
        ),
        None,
    )
    detail = next(
        (
            answer
            for answer in answers
            if answer.status == "answered"
            and answer.field in ("allergies", "allergies.details")
            and isinstance(answer.value, str)
        ),
        None,
    )
    if any_answer is None and detail is None:
        return []
    patient_positive = detail is not None or (any_answer is not None and any_answer.value is True)
    patient_negative = any_answer is not None and any_answer.value is False
    source_answer = detail or any_answer
    items = []
    extractions = list(
        db.scalars(
            select(models.DocumentExtraction)
            .where(
                models.DocumentExtraction.session_id == session_id,
                models.DocumentExtraction.verification_status != "rejected",
            )
            .order_by(models.DocumentExtraction.created_at, models.DocumentExtraction.id)
        )
    )
    for extraction in extractions:
        structured = StructuredDocument.model_validate(extraction.structured_json)
        document = db.get(models.Document, extraction.document_id)
        for index, statement in enumerate(structured.allergies):
            conflict = (patient_positive and statement.statement == "no_known_allergies") or (
                patient_negative and statement.statement == "allergy" and statement.substance
            )
            if not conflict:
                continue
            source_a = _patient_source(source_answer, "Patient-reported allergy history")
            displayed = statement.substance or statement.raw_text
            source_b = DiscrepancySource(
                source_type="document_fact",
                source_id=f"{extraction.id}:allergy:{index}",
                label="Document-derived allergy statement",
                displayed_value=displayed,
                document_id=document.id if document else None,
                extraction_id=extraction.id,
                raw_text=statement.raw_text,
            )
            reason = "Patient-reported allergy history conflicts with an explicit document allergy statement."
            items.append(_make("ALLERGY_CONFLICT", source_a, source_b, reason))
    return items


def _lab_discrepancies(facts):
    items = []
    labs = facts.labs
    for index, left in enumerate(labs):
        left_value = left.current
        for right in labs[index + 1 :]:
            right_value = right.current
            comparable = (
                left.source.extraction_id != right.source.extraction_id
                and left_value.observation_timestamp is not None
                and right_value.observation_timestamp is not None
                and left_value.observation_timestamp == right_value.observation_timestamp
                and left_value.unit is not None
                and right_value.unit is not None
                and _normalized(left_value.test_name) == _normalized(right_value.test_name)
                and _normalized(left_value.unit) == _normalized(right_value.unit)
            )
            if not comparable or _normalized(left_value.value) == _normalized(right_value.value):
                continue
            source_a = _document_source(
                left,
                "Document-derived lab result A",
                f"{left_value.test_name}: {left_value.value} {left_value.unit}",
            )
            source_b = _document_source(
                right,
                "Document-derived lab result B",
                f"{right_value.test_name}: {right_value.value} {right_value.unit}",
            )
            reason = f"Two document sources report different {left_value.test_name} values for the same explicit observation time and unit."
            items.append(_make("LAB_VALUE_CONFLICT", source_a, source_b, reason))
    return items


def get_discrepancies(db: Session, session_id: str) -> DiscrepancyResponse:
    intake.get_session(db, session_id)
    intake.require_consent(db, session_id)
    facts = medical_facts.get_current_facts(db, session_id)
    items = [
        *_medication_discrepancies(db, session_id, facts),
        *_allergy_discrepancies(db, session_id),
        *_lab_discrepancies(facts),
    ]
    return DiscrepancyResponse(
        items=sorted(
            items,
            key=lambda item: (
                item.type,
                item.source_a.source_id,
                item.source_b.source_id,
                item.discrepancy_id,
            ),
        )
    )
