"""Deterministic, non-generative explanations for clinical-summary evidence."""

from app.schemas.clinical_summary import EvidenceReference


def resolve(reference: EvidenceReference) -> EvidenceReference:
    metadata = reference.source_metadata
    source_type = reference.source_type
    verification = str(metadata.get("verification_status") or "").upper()
    confirmed = bool(metadata.get("patient_confirmed"))

    if source_type == "discrepancy":
        status, badge = "conflicting", "Conflict"
        explanation = [
            "Shown because the uploaded document and patient-reported history differ.",
            "Both source values are preserved for clinician clarification.",
        ]
    elif source_type == "alert":
        status, badge = "safety_rule", "Safety Rule"
        rule_id = metadata.get("rule_id") or "the recorded safety rule"
        explanation = [
            f"Highlighted because deterministic safety rule {rule_id} was triggered by reported information.",
            f"Acknowledgment state: {metadata.get('status', 'unacknowledged')}.",
        ]
    elif source_type in ("medical_fact", "document"):
        filename = metadata.get("document_filename") or "uploaded document"
        page = metadata.get("page_number")
        location = f", page {page}" if page else ""
        if verification in ("VERIFIED", "CLINICIAN_VERIFIED"):
            status, badge = "clinician_verified", "Clinician Verified"
        elif confirmed:
            status, badge = "patient_confirmed", "Patient Confirmed"
        else:
            status, badge = "document_unverified", "Document — Unverified"
        explanation = [f"Extracted from {filename}{location}."]
        if reference.source_text:
            explanation.append(f'OCR extracted: "{reference.source_text}"')
        if confirmed:
            explanation.append("Patient confirmed current use during intake.")
        if status == "clinician_verified":
            explanation.append(
                "Verified by the reviewing clinician; the original extraction is retained."
            )
        elif status == "document_unverified":
            explanation.append("Document-derived information has not been clinician verified.")
    elif source_type == "normalized_fact":
        status, badge = "normalized_unverified", "Normalized"
        explanation = [
            "Derived from a patient answer by deterministic/provider normalization.",
            "Normalization does not constitute clinician verification.",
        ]
    elif source_type == "timeline":
        status, badge = "timeline", "Timeline"
        explanation = ["Included from the source-linked longitudinal clinical timeline."]
    else:
        answer_status = str(metadata.get("status") or metadata.get("answer_status") or "")
        if answer_status in ("unknown", "not_reported", "skipped"):
            status, badge = "not_reported", "Not Reported"
            explanation = ["This interview field was not reported by the patient."]
        elif confirmed:
            status, badge = "patient_confirmed", "Patient Confirmed"
            explanation = [
                "Found in an uploaded document and confirmed by the patient during intake."
            ]
        else:
            status, badge = "patient_reported", "Patient"
            explanation = ["Reported by the patient during the structured intake interview."]

    reference.status = status
    reference.badge = badge
    reference.evidence_refs = list(
        dict.fromkeys([reference.source_id, *metadata.get("evidence_refs", [])])
    )
    reference.source_summary = [
        badge,
        *([str(metadata["document_filename"])] if metadata.get("document_filename") else []),
    ]
    reference.provenance_explanation = explanation
    return reference


def resolve_all(references: list[EvidenceReference]) -> list[EvidenceReference]:
    return [resolve(reference) for reference in references]
