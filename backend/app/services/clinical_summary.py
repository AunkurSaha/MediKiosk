"""Deterministic, clinician-controlled clinical summary generation service.

Synthesizes structured clinical sources:
- Patient interview answers & normalization
- Source-linked medical facts (medications, labs)
- Chronological clinical timeline (known & undated)
- Conservative discrepancies
- Safety screening red-flag alerts

Strictly preserves unknowns. Generates zero hallucinations (no diagnosis, no
prescriptions, no invented dates, no fabricated clinical conclusions).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.schemas.clinical_summary import (
    EvidenceReference,
    StructuredClinicalSummary,
    StructuredSummarySection,
)
from app.services import (
    adaptive,
    intake,
    medical_facts,
    red_flags,
)
from app.services import (
    discrepancies as discrepancy_service,
)
from app.services import (
    timeline as timeline_service,
)

STATEMENT_NAMESPACE = uuid.UUID("3d4b6c89-2e1f-4a5b-9c7d-8e0f1a2b3c4d")


def _statement_id(*parts: object) -> str:
    return str(uuid.uuid5(STATEMENT_NAMESPACE, "|".join(str(part) for part in parts)))


class ClinicalSummaryService:
    @classmethod
    def generate_draft(
        cls,
        db: Session,
        session_id: str,
        draft_version: int = 1,
    ) -> tuple[str, StructuredClinicalSummary]:
        session = intake.get_session(db, session_id)
        intake.require_consent(db, session_id)

        patient = db.get(models.Patient, session.patient_id)
        patient_name = patient.name if patient else "Unknown Patient"
        patient_id = patient.id if patient else session.patient_id
        run = db.get(models.InterviewRun, session_id)
        history = adaptive.state(db, session_id).history if run else None
        answers = intake.latest_answers(db, session_id)
        facts = medical_facts.get_current_facts(db, session_id)
        timeline = timeline_service.get_timeline(db, session_id)
        discrepancies = discrepancy_service.get_discrepancies(db, session_id)
        alerts = red_flags.get_session_alerts(db, session_id)

        sections: list[StructuredSummarySection] = []
        all_evidence: list[EvidenceReference] = []

        is_ayush = (
            (history is not None and getattr(history, "namespace", None) == "ayush_demo")
            or (
                history is not None
                and getattr(history, "selected_complaint", None)
                and "ayush" in str(history.selected_complaint).lower()
            )
            or any(
                "ayush" in (a.raw_value or "").lower() or "ayurved" in (a.raw_value or "").lower()
                for a in answers
            )
        )
        disclaimer = (
            "AYUSH DEMONSTRATION PATHWAY: Supportive documentation only. "
            "No clinical interpretation or diagnosis. Requires independent clinician verification."
            if is_ayush
            else None
        )

        # ---------------------------------------------------------------------
        # 1. Patient Information
        # ---------------------------------------------------------------------
        p_lines = [
            f"Patient Name: {patient_name}",
            f"Hospital Token: {session.hospital_token}",
            f"Session Language: {session.language.upper()}",
            f"Session Status: {session.status.replace('_', ' ').title()}",
            f"Intake Session ID: {session.id}",
        ]
        p_ev = EvidenceReference(
            statement_id=_statement_id("patient_info", session.id),
            section="patient_info",
            statement_text=f"Patient {patient_name} (Token: {session.hospital_token})",
            source_type="patient_answer",
            source_id=patient_id,
            source_text=patient_name,
            source_metadata={
                "hospital_token": session.hospital_token,
                "language": session.language,
                "session_id": session.id,
            },
        )
        sections.append(
            StructuredSummarySection(
                section_key="patient_info",
                title="1. Patient Information",
                content_lines=p_lines,
                items=[{"patient_name": patient_name, "token": session.hospital_token}],
                evidence=[p_ev],
            )
        )
        all_evidence.append(p_ev)

        # ---------------------------------------------------------------------
        # 2. Chief Complaint
        # ---------------------------------------------------------------------
        cc_lines: list[str] = []
        cc_evidence: list[EvidenceReference] = []
        if history and history.selected_complaint:
            cc_text = f"Primary Concern: {history.selected_complaint.en}"
            cc_lines.append(cc_text)
            ev = EvidenceReference(
                statement_id=_statement_id("chief_complaint", history.selected_complaint.en),
                section="chief_complaint",
                statement_text=cc_text,
                source_type="patient_answer",
                source_id=session.id,
                source_text=history.selected_complaint.en,
                source_metadata={"complaint_id": history.selected_complaint.en},
            )
            cc_evidence.append(ev)
        else:
            cc_ans = next(
                (a for a in answers if a.field == "chief_complaint" and a.status == "answered"),
                None,
            )
            if cc_ans:
                cc_text = f"Primary Concern (Patient-reported): {cc_ans.raw_value}"
                cc_lines.append(cc_text)
                ev = EvidenceReference(
                    statement_id=_statement_id("chief_complaint", cc_ans.id),
                    section="chief_complaint",
                    statement_text=cc_text,
                    source_type="patient_answer",
                    source_id=cc_ans.id,
                    source_text=cc_ans.raw_value,
                )
                cc_evidence.append(ev)
            else:
                cc_lines.append("Primary Concern: Not reported")

        sections.append(
            StructuredSummarySection(
                section_key="chief_complaint",
                title="2. Chief Complaint",
                content_lines=cc_lines,
                evidence=cc_evidence,
            )
        )
        all_evidence.extend(cc_evidence)

        # ---------------------------------------------------------------------
        # 3. History of Present Illness (HPI)
        # ---------------------------------------------------------------------
        hpi_lines: list[str] = []
        hpi_evidence: list[EvidenceReference] = []
        if history:
            hpi_sec = next(
                (s for s in history.sections if s.section_id in ("hpi", "chief_complaint")), None
            )
            if hpi_sec and hpi_sec.facts:
                for fact in hpi_sec.facts:
                    norm_label = ""
                    if fact.normalization and fact.normalization.facts:
                        concepts = ", ".join(
                            f.normalized_display for f in fact.normalization.facts
                        )
                        norm_label = f" [Machine-normalized: {concepts} (Needs clinician review)]"
                    line = f"- {fact.label.en}: {fact.raw_value} (Reported via {fact.source}){norm_label}"
                    hpi_lines.append(line)

                    ev = EvidenceReference(
                        statement_id=_statement_id("hpi", fact.question_id),
                        section="hpi",
                        statement_text=line,
                        source_type="normalized_fact" if fact.normalization else "patient_answer",
                        source_id=fact.question_id,
                        source_text=fact.raw_value,
                        source_metadata={
                            "status": fact.status,
                            "source": fact.source,
                            "language": fact.language,
                        },
                    )
                    hpi_evidence.append(ev)
        if not hpi_lines:
            # Fallback to legacy answers
            dur_ans = next(
                (a for a in answers if a.field == "onset_duration" and a.status == "answered"), None
            )
            if dur_ans:
                line = f"- Onset and Duration: {dur_ans.raw_value} (Patient-reported)"
                hpi_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("hpi", dur_ans.id),
                    section="hpi",
                    statement_text=line,
                    source_type="patient_answer",
                    source_id=dur_ans.id,
                    source_text=dur_ans.raw_value,
                )
                hpi_evidence.append(ev)
            else:
                hpi_lines.append("- No specific HPI findings reported.")

        sections.append(
            StructuredSummarySection(
                section_key="hpi",
                title="3. History of Present Illness",
                content_lines=hpi_lines,
                evidence=hpi_evidence,
            )
        )
        all_evidence.extend(hpi_evidence)

        # ---------------------------------------------------------------------
        # 4. Relevant Medical History
        # ---------------------------------------------------------------------
        hist_lines: list[str] = []
        hist_evidence: list[EvidenceReference] = []
        if history:
            other_sections = [
                s
                for s in history.sections
                if s.section_id not in ("hpi", "chief_complaint", "medications")
            ]
            for s in other_sections:
                if s.facts:
                    hist_lines.append(f"{s.label.en}:")
                    for fact in s.facts:
                        line = f"  - {fact.label.en}: {fact.raw_value}"
                        hist_lines.append(line)
                        ev = EvidenceReference(
                            statement_id=_statement_id("med_history", fact.question_id),
                            section="relevant_medical_history",
                            statement_text=line,
                            source_type="patient_answer",
                            source_id=fact.question_id,
                            source_text=fact.raw_value,
                        )
                        hist_evidence.append(ev)
        if not hist_lines:
            hist_ans = next(
                (a for a in answers if a.field == "past_history" and a.status == "answered"), None
            )
            if hist_ans:
                line = f"- Past Medical History: {hist_ans.raw_value}"
                hist_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("med_history", hist_ans.id),
                    section="relevant_medical_history",
                    statement_text=line,
                    source_type="patient_answer",
                    source_id=hist_ans.id,
                    source_text=hist_ans.raw_value,
                )
                hist_evidence.append(ev)
            else:
                hist_lines.append("- No significant past medical history reported.")

        sections.append(
            StructuredSummarySection(
                section_key="relevant_medical_history",
                title="4. Relevant Medical History",
                content_lines=hist_lines,
                evidence=hist_evidence,
            )
        )
        all_evidence.extend(hist_evidence)

        # ---------------------------------------------------------------------
        # 5. Current Medications
        # ---------------------------------------------------------------------
        med_lines: list[str] = []
        med_evidence: list[EvidenceReference] = []

        # Patient reported medications
        patient_med_answers = [
            a
            for a in answers
            if a.field in ("medications", "medications.details") and a.status == "answered"
        ]
        if patient_med_answers:
            med_lines.append("Patient-Reported:")
            for a in patient_med_answers:
                line = f"  - {a.raw_value} [Patient-reported]"
                med_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("med_patient", a.id),
                    section="current_medications",
                    statement_text=line,
                    source_type="patient_answer",
                    source_id=a.id,
                    source_text=a.raw_value,
                )
                med_evidence.append(ev)

        # Document extracted medications
        if facts.medications:
            med_lines.append("Document-Extracted (Clinical Records):")
            for m in facts.medications:
                curr = m.current
                parts = [curr.name]
                if curr.dosage:
                    parts.append(curr.dosage)
                if curr.unit:
                    parts.append(curr.unit)
                if curr.route:
                    parts.append(f"route: {curr.route}")
                if curr.frequency:
                    parts.append(f"frequency: {curr.frequency}")
                if curr.duration:
                    parts.append(f"duration: {curr.duration}")

                date_part = ""
                if curr.start_date:
                    date_part += f" (Started: {curr.start_date.strftime('%Y-%m-%d')}"
                    if curr.end_date:
                        date_part += f", Ended: {curr.end_date.strftime('%Y-%m-%d')}"
                    date_part += ")"

                doc_label = m.source.document_filename or "Document"
                line = (
                    f"  - {' '.join(parts)}{date_part} "
                    f"[{doc_label}; Status: {m.verification_status}]"
                )
                med_lines.append(line)

                ev = EvidenceReference(
                    statement_id=_statement_id("med_doc", m.id),
                    section="current_medications",
                    statement_text=line,
                    source_type="medical_fact",
                    source_id=m.id,
                    source_text=m.source.raw_text or curr.name,
                    source_metadata={
                        "document_id": m.source.document_id,
                        "document_filename": m.source.document_filename,
                        "verification_status": m.verification_status,
                    },
                )
                med_evidence.append(ev)

        if not med_lines:
            med_lines.append("No current medications reported or documented.")

        sections.append(
            StructuredSummarySection(
                section_key="current_medications",
                title="5. Current Medications",
                content_lines=med_lines,
                evidence=med_evidence,
            )
        )
        all_evidence.extend(med_evidence)

        # ---------------------------------------------------------------------
        # 6. Investigations / Laboratory Findings
        # ---------------------------------------------------------------------
        lab_lines: list[str] = []
        lab_evidence: list[EvidenceReference] = []
        if facts.labs:
            for lab_item in facts.labs:
                curr = lab_item.current
                unit_str = f" {curr.unit}" if curr.unit else ""
                ref_str = f" (Ref: {curr.reference_range})" if curr.reference_range else ""
                flag_str = f" [Flag: {curr.flag}]" if curr.flag else ""
                obs_str = (
                    f" [Observed: {curr.observation_timestamp.strftime('%Y-%m-%d %H:%M')}]"
                    if curr.observation_timestamp
                    else ""
                )
                doc_label = lab_item.source.document_filename or "Document"
                line = (
                    f"- {curr.test_name}: {curr.value}{unit_str}{ref_str}{flag_str}{obs_str} "
                    f"[{doc_label}; Status: {lab_item.verification_status}]"
                )
                lab_lines.append(line)

                ev = EvidenceReference(
                    statement_id=_statement_id("lab", lab_item.id),
                    section="investigations_labs",
                    statement_text=line,
                    source_type="medical_fact",
                    source_id=lab_item.id,
                    source_text=lab_item.source.raw_text or curr.test_name,
                    source_metadata={
                        "document_id": lab_item.source.document_id,
                        "document_filename": lab_item.source.document_filename,
                        "verification_status": lab_item.verification_status,
                        "flag": curr.flag,
                    },
                )
                lab_evidence.append(ev)
        else:
            lab_lines.append("No laboratory findings documented.")

        sections.append(
            StructuredSummarySection(
                section_key="investigations_labs",
                title="6. Investigations / Laboratory Findings",
                content_lines=lab_lines,
                evidence=lab_evidence,
            )
        )
        all_evidence.extend(lab_evidence)

        # ---------------------------------------------------------------------
        # 7. Clinical Timeline
        # ---------------------------------------------------------------------
        tl_lines: list[str] = []
        tl_evidence: list[EvidenceReference] = []
        if timeline.known_date:
            tl_lines.append("Chronological Events (Known Dates):")
            for entry in timeline.known_date:
                ts_str = entry.event_timestamp.strftime("%Y-%m-%d") if entry.event_timestamp else ""
                doc_str = (
                    f" [{entry.source.document_filename}]"
                    if entry.source.document_filename
                    else ""
                )
                line = f"  - {ts_str}: {entry.canonical_label}{doc_str} (Status: {entry.verification_status})"
                tl_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("timeline", entry.id),
                    section="clinical_timeline",
                    statement_text=line,
                    source_type=entry.source.source_type,
                    source_id=entry.source.source_id,
                    source_text=entry.canonical_label,
                    source_metadata={
                        "date_status": entry.date_status,
                        "verification_status": entry.verification_status,
                    },
                )
                tl_evidence.append(ev)

        if timeline.unknown_date:
            tl_lines.append("Undated / Historical Observations:")
            for entry in timeline.unknown_date:
                doc_str = (
                    f" [{entry.source.document_filename}]"
                    if entry.source.document_filename
                    else ""
                )
                line = f"  - [Undated]: {entry.canonical_label}{doc_str} (Status: {entry.verification_status})"
                tl_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("timeline_undated", entry.id),
                    section="clinical_timeline",
                    statement_text=line,
                    source_type=entry.source.source_type,
                    source_id=entry.source.source_id,
                    source_text=entry.canonical_label,
                    source_metadata={"date_status": "unknown"},
                )
                tl_evidence.append(ev)

        if not tl_lines:
            tl_lines.append("No timeline events recorded.")

        sections.append(
            StructuredSummarySection(
                section_key="clinical_timeline",
                title="7. Clinical Timeline",
                content_lines=tl_lines,
                evidence=tl_evidence,
            )
        )
        all_evidence.extend(tl_evidence)

        # ---------------------------------------------------------------------
        # 8. Safety Alerts
        # ---------------------------------------------------------------------
        alert_lines: list[str] = []
        alert_evidence: list[EvidenceReference] = []
        if alerts:
            for al in alerts:
                line = (
                    f"- ⚠️ [{al.priority.upper()}] {al.rule_id} ({al.category}): "
                    f"{al.reason} (Status: {al.status})"
                )
                alert_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("alert", al.id),
                    section="safety_alerts",
                    statement_text=line,
                    source_type="alert",
                    source_id=al.id,
                    source_text=al.reason,
                    source_metadata={
                        "priority": al.priority,
                        "rule_id": al.rule_id,
                        "category": al.category,
                        "status": al.status,
                    },
                )
                alert_evidence.append(ev)
        else:
            alert_lines.append("No red-flag emergency symptoms detected during screening.")

        sections.append(
            StructuredSummarySection(
                section_key="safety_alerts",
                title="8. Safety Alerts",
                content_lines=alert_lines,
                evidence=alert_evidence,
            )
        )
        all_evidence.extend(alert_evidence)

        # ---------------------------------------------------------------------
        # 9. Potential Discrepancies
        # ---------------------------------------------------------------------
        disc_lines: list[str] = []
        disc_evidence: list[EvidenceReference] = []
        if discrepancies.items:
            for d in discrepancies.items:
                line = (
                    f"- ⚡ [REQUIRES CLINICIAN REVIEW] {d.type.replace('_', ' ').title()}: {d.reason}\n"
                    f"    Source A ({d.source_a.label}): \"{d.source_a.displayed_value}\"\n"
                    f"    Source B ({d.source_b.label}): \"{d.source_b.displayed_value}\""
                )
                disc_lines.append(line)
                ev = EvidenceReference(
                    statement_id=_statement_id("discrepancy", d.discrepancy_id),
                    section="potential_discrepancies",
                    statement_text=line,
                    source_type="discrepancy",
                    source_id=d.discrepancy_id,
                    source_text=d.reason,
                    source_metadata={
                        "type": d.type,
                        "source_a_type": d.source_a.source_type,
                        "source_b_type": d.source_b.source_type,
                    },
                )
                disc_evidence.append(ev)
        else:
            disc_lines.append(
                "No discrepancies detected between patient-reported history and records."
            )

        sections.append(
            StructuredSummarySection(
                section_key="potential_discrepancies",
                title="9. Potential Discrepancies",
                content_lines=disc_lines,
                evidence=disc_evidence,
            )
        )
        all_evidence.extend(disc_evidence)

        # ---------------------------------------------------------------------
        # 10. Unknown / Not Reported Information
        # ---------------------------------------------------------------------
        unk_lines: list[str] = []
        unk_evidence: list[EvidenceReference] = []
        unknown_answers = [
            a
            for a in answers
            if a.status in ("unknown", "not_reported", "skipped")
        ]
        for ua in unknown_answers:
            label = ua.field.replace("_", " ").title()
            line = f"- {label}: Patient reported {ua.status.replace('_', ' ')}"
            unk_lines.append(line)
            ev = EvidenceReference(
                statement_id=_statement_id("unknown", ua.id),
                section="unknown_not_reported",
                statement_text=line,
                source_type="patient_answer",
                source_id=ua.id,
                source_text=ua.raw_value or ua.status,
                source_metadata={"status": ua.status, "field": ua.field},
            )
            unk_evidence.append(ev)

        if not unk_lines:
            unk_lines.append("All core interview domains addressed.")

        sections.append(
            StructuredSummarySection(
                section_key="unknown_not_reported",
                title="10. Unknown / Not Reported Information",
                content_lines=unk_lines,
                evidence=unk_evidence,
            )
        )
        all_evidence.extend(unk_evidence)

        # Assemble consultation draft text
        draft_parts: list[str] = []
        if disclaimer:
            draft_parts.append(f"*** {disclaimer.upper()} ***\n")

        for sec in sections:
            draft_parts.append(f"## {sec.title}")
            for line_text in sec.content_lines:
                draft_parts.append(line_text)
            draft_parts.append("")  # blank line separator

        draft_text = "\n".join(draft_parts).strip()

        structured = StructuredClinicalSummary(
            session_id=session_id,
            generated_at=datetime.now(timezone.utc),
            draft_version=draft_version,
            draft_provider="deterministic",
            sections=sections,
            evidence_references=all_evidence,
            disclaimer=disclaimer,
        )

        return draft_text, structured
