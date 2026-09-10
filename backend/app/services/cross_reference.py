from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.schemas.cross_reference import (
    CrossReferenceResponse,
    DocumentCrossReference,
    DocumentFactLink,
)
from app.services import discrepancies as discrepancy_service
from app.services import intake


def get_cross_references(db: Session, session_id: str) -> CrossReferenceResponse:
    # Ensure session exists
    intake.get_session(db, session_id)

    # 1. Fetch documents
    docs = db.scalars(
        select(models.Document)
        .where(models.Document.session_id == session_id)
        .order_by(models.Document.created_at.asc())
    ).all()

    # 2. Fetch extractions for this session
    extractions = db.scalars(
        select(models.DocumentExtraction)
        .where(models.DocumentExtraction.session_id == session_id)
    ).all()
    extraction_doc_map = {e.id: e.document_id for e in extractions}

    # 3. Fetch active medication and lab facts
    med_facts = db.scalars(
        select(models.MedicationFact)
        .where(
            models.MedicationFact.session_id == session_id,
            models.MedicationFact.verification_status != "rejected",
        )
    ).all()

    lab_facts = db.scalars(
        select(models.LabFact)
        .where(
            models.LabFact.session_id == session_id,
            models.LabFact.verification_status != "rejected",
        )
    ).all()

    # 4. Fetch discrepancies
    disc_resp = discrepancy_service.get_discrepancies(db, session_id)

    # 5. Fetch summary evidence statements
    try:
        evidence_items = intake.get_summary_evidence(db, session_id)
    except Exception:
        evidence_items = []

    statement_cross_refs: dict[str, dict[str, Any]] = {}
    doc_statements_map: dict[str, list[str]] = {d.id: [] for d in docs}

    for ev in evidence_items:
        statement_cross_refs[ev.statement_id] = {
            "section": ev.section,
            "statement_text": ev.statement_text,
            "source_type": ev.source_type,
            "source_id": ev.source_id,
            "source_text": ev.source_text,
            "source_metadata": ev.source_metadata,
        }
        # Check if linked to a document
        doc_id = ev.source_metadata.get("document_id") if ev.source_metadata else None
        if doc_id and doc_id in doc_statements_map:
            doc_statements_map[doc_id].append(ev.statement_id)

    # 6. Group facts by document
    doc_meds_map: dict[str, list[DocumentFactLink]] = {d.id: [] for d in docs}
    for m in med_facts:
        d_id = extraction_doc_map.get(m.source_extraction_id)
        if d_id and d_id in doc_meds_map:
            dosage_str = f" {m.dosage}" if m.dosage else ""
            freq_str = f" ({m.frequency})" if m.frequency else ""
            doc_meds_map[d_id].append(
                DocumentFactLink(
                    fact_id=m.id,
                    fact_type="medication",
                    label=f"{m.name}{dosage_str}{freq_str}".strip(),
                    verification_status=m.verification_status,
                )
            )

    doc_labs_map: dict[str, list[DocumentFactLink]] = {d.id: [] for d in docs}
    for lab_item in lab_facts:
        d_id = extraction_doc_map.get(lab_item.source_extraction_id)
        if d_id and d_id in doc_labs_map:
            unit_str = f" {lab_item.unit}" if lab_item.unit else ""
            doc_labs_map[d_id].append(
                DocumentFactLink(
                    fact_id=lab_item.id,
                    fact_type="lab",
                    label=f"{lab_item.test_name}: {lab_item.value}{unit_str}".strip(),
                    verification_status=lab_item.verification_status,
                )
            )

    doc_discrepancies_map: dict[str, list[str]] = {d.id: [] for d in docs}
    for disc in disc_resp.items:
        # Check if source_b references a document
        if disc.source_b.source_type == "document" and disc.source_b.source_id in doc_discrepancies_map:
            doc_discrepancies_map[disc.source_b.source_id].append(disc.id)

    # 7. Assemble DocumentCrossReference items
    doc_xrefs: list[DocumentCrossReference] = []
    for d in docs:
        doc_xrefs.append(
            DocumentCrossReference(
                document_id=d.id,
                filename=d.original_filename,
                document_type=d.document_type,
                created_at=d.created_at,
                medications=doc_meds_map.get(d.id, []),
                labs=doc_labs_map.get(d.id, []),
                discrepancies=doc_discrepancies_map.get(d.id, []),
                summary_statements=doc_statements_map.get(d.id, []),
            )
        )

    return CrossReferenceResponse(
        session_id=session_id,
        documents=doc_xrefs,
        statement_cross_references=statement_cross_refs,
    )
