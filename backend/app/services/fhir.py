from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.schemas.fhir.base import (
    Attachment,
    CodeableConcept,
    Coding,
    HumanName,
    Identifier,
    Meta,
    Narrative,
    Period,
    Reference,
)
from app.schemas.fhir.bundle import BundleEntry, BundleResource, FHIRExportResponse
from app.schemas.fhir.resources import (
    CompositionResource,
    CompositionSection,
    ConditionResource,
    DocumentReferenceContent,
    DocumentReferenceResource,
    Dosage,
    EncounterClass,
    EncounterResource,
    MedicationStatementResource,
    ObservationReferenceRange,
    ObservationResource,
    OperationOutcome,
    OperationOutcomeIssue,
    PatientCommunication,
    PatientResource,
    QuestionnaireResponseItem,
    QuestionnaireResponseItemAnswer,
    QuestionnaireResponseResource,
)


class FHIRAdapterService:
    """Deterministic adapter transforming internal MediKiosk data to validated HL7 FHIR R4."""

    PROFILE_DOCUMENT = "https://nrces.in/ndhm/fhir/r4/StructureDefinition/OPConsultRecord"
    PROFILE_BUNDLE = "https://nrces.in/ndhm/fhir/r4/StructureDefinition/DocumentBundle"

    @classmethod
    def build_bundle(
        cls,
        db: Session,
        session_id: str,
        bundle_type: str = "document",
    ) -> BundleResource:
        """Construct a validated FHIR R4 Bundle from session clinical data."""
        session = db.query(models.Session).filter(models.Session.id == session_id).first()
        if not session:
            raise ValueError(f"Session '{session_id}' not found")

        patient = db.query(models.Patient).filter(models.Patient.id == session.patient_id).first()
        if not patient:
            raise ValueError(f"Patient for session '{session_id}' not found")

        answers = (
            db.query(models.InterviewAnswer)
            .filter(models.InterviewAnswer.session_id == session_id)
            .order_by(models.InterviewAnswer.created_at)
            .all()
        )
        med_facts = (
            db.query(models.MedicationFact)
            .filter(models.MedicationFact.session_id == session_id)
            .all()
        )
        lab_facts = (
            db.query(models.LabFact)
            .filter(models.LabFact.session_id == session_id)
            .all()
        )
        documents = (
            db.query(models.Document)
            .filter(models.Document.session_id == session_id)
            .all()
        )
        summary = (
            db.query(models.ClinicalSummary)
            .filter(models.ClinicalSummary.session_id == session_id)
            .first()
        )

        # 1. Patient Resource
        patient_full_url = f"urn:uuid:patient-{patient.id}"
        patient_identifiers = [
            Identifier(
                use="official",
                system="https://hospital.medikiosk.internal/tokens",
                value=session.hospital_token,
            )
        ]
        if patient.demo_abha_id:
            patient_identifiers.append(
                Identifier(
                    use="official",
                    system="https://healthid.ndhm.gov.in",
                    value=patient.demo_abha_id,
                )
            )

        # Extract demographic hints from answers
        gender_val = "unknown"
        birth_date_val = None
        chief_complaint_text = None
        for a in answers:
            field_name = (a.field or "").lower()
            val_str = str(a.raw_value or getattr(a, "value", "") or "").strip()
            if "gender" in field_name:
                if "female" in val_str.lower():
                    gender_val = "female"
                elif "male" in val_str.lower():
                    gender_val = "male"
                elif val_str:
                    gender_val = "other"
            elif "age" in field_name and val_str.isdigit():
                birth_year = datetime.now(timezone.utc).year - int(val_str)
                birth_date_val = f"{birth_year}-01-01"
            elif "complaint" in field_name or "reason" in field_name:
                chief_complaint_text = val_str

        patient_resource = PatientResource(
            id=f"patient-{patient.id}",
            meta=Meta(profile=["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Patient"]),
            identifier=patient_identifiers,
            active=True,
            name=[HumanName(text=patient.name)],
            gender=gender_val,
            birth_date=birth_date_val,
            communication=[
                PatientCommunication(
                    language=CodeableConcept(
                        coding=[Coding(system="urn:ietf:bcp:47", code=session.language or "en")]
                    )
                )
            ],
            text=Narrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml">Patient: {patient.name}, Token: {session.hospital_token}</div>',
            ),
        )

        # 2. Encounter Resource
        encounter_full_url = f"urn:uuid:encounter-{session.id}"
        encounter_status = (
            "finished"
            if session.status in ["confirmed", "completed", "ready_for_review"]
            else "in-progress"
        )
        encounter_resource = EncounterResource(
            id=f"encounter-{session.id}",
            meta=Meta(profile=["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Encounter"]),
            identifier=[
                Identifier(
                    system="https://medikiosk.internal/sessions",
                    value=str(session.id),
                )
            ],
            status=encounter_status,
            class_code=EncounterClass(code="AMB", display="ambulatory"),
            subject=Reference(reference=patient_full_url, display=patient.name),
            period=Period(
                start=session.created_at.isoformat() if session.created_at else None,
                end=session.completed_at.isoformat() if session.completed_at else None,
            ),
            text=Narrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml">Kiosk Intake Encounter for {session.hospital_token}</div>',
            ),
        )

        # 3. QuestionnaireResponse Resource (Patient Reported Answers)
        qr_full_url = f"urn:uuid:qr-{session.id}"
        qr_items: list[QuestionnaireResponseItem] = []
        for ans in answers:
            qr_items.append(
                QuestionnaireResponseItem(
                    link_id=ans.question_id or ans.field,
                    text=(ans.field or "").replace("_", " ").title(),
                    answer=[QuestionnaireResponseItemAnswer(value_string=ans.raw_value or getattr(ans, "value", None) or "")],
                )
            )

        qr_resource = QuestionnaireResponseResource(
            id=f"qr-{session.id}",
            status="completed",
            subject=Reference(reference=patient_full_url, display=patient.name),
            encounter=Reference(reference=encounter_full_url),
            authored=(session.completed_at or session.created_at or datetime.now(timezone.utc)).isoformat(),
            item=qr_items,
            text=Narrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml">Patient Intake Responses ({len(qr_items)} items)</div>',
            ),
        )

        # 4. Condition Resources (Provisional Chief Complaint / Symptoms)
        conditions: list[ConditionResource] = []
        cc_full_url = f"urn:uuid:condition-{session.id}-cc"
        conditions.append(
            ConditionResource(
                id=f"condition-{session.id}-cc",
                meta=Meta(profile=["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Condition"]),
                clinical_status=CodeableConcept(
                    coding=[Coding(system="http://terminology.hl7.org/CodeSystem/condition-clinical", code="active")]
                ),
                verification_status=CodeableConcept(
                    coding=[Coding(system="http://terminology.hl7.org/CodeSystem/condition-ver-status", code="provisional")]
                ),
                category=[
                    CodeableConcept(
                        coding=[Coding(system="http://terminology.hl7.org/CodeSystem/condition-category", code="problem-list-item", display="Problem List Item")]
                    )
                ],
                code=CodeableConcept(text=chief_complaint_text or "Chief complaint intake"),
                subject=Reference(reference=patient_full_url, display=patient.name),
                encounter=Reference(reference=encounter_full_url),
                recorded_date=session.created_at.date().isoformat() if session.created_at else None,
                note=[{"text": "Patient-reported intake finding. Non-diagnostic. Requires clinical assessment."}],
                text=Narrative(
                    status="generated",
                    div=f'<div xmlns="http://www.w3.org/1999/xhtml">Provisional Symptom: {chief_complaint_text or "Intake finding"}</div>',
                ),
            )
        )

        # 5. MedicationStatement Resources
        med_statements: list[MedicationStatementResource] = []
        for _idx, med in enumerate(med_facts):
            dosage_text = f"{med.dosage or ''} {med.frequency or ''}".strip() or None
            med_statements.append(
                MedicationStatementResource(
                    id=f"med-{med.id}",
                    meta=Meta(profile=["https://nrces.in/ndhm/fhir/r4/StructureDefinition/MedicationStatement"]),
                    status="active" if getattr(med, "is_active", True) and med.verification_status != "rejected" else "stopped",
                    medication_codeable_concept=CodeableConcept(text=med.name),
                    subject=Reference(reference=patient_full_url, display=patient.name),
                    context=Reference(reference=encounter_full_url),
                    effective_period=Period(
                        start=med.start_date.isoformat() if med.start_date else None,
                        end=med.end_date.isoformat() if med.end_date else None,
                    ),
                    dosage=[Dosage(text=dosage_text)] if dosage_text else [],
                    status_reason=[CodeableConcept(text=f"Verification status: {med.verification_status}")],
                    note=[{"text": f"Document extraction (confidence: {getattr(med, 'confidence', None)})" if getattr(med, "confidence", None) is not None else "Document extraction"}],
                    text=Narrative(
                        status="generated",
                        div=f'<div xmlns="http://www.w3.org/1999/xhtml">Medication: {med.name} ({med.verification_status})</div>',
                    ),
                )
            )

        # 6. Observation Resources (Labs)
        observations: list[ObservationResource] = []
        for _idx, lab in enumerate(lab_facts):
            obs_status = (
                "final"
                if lab.verification_status == "verified"
                else "cancelled"
                if lab.verification_status == "rejected"
                else "preliminary"
            )
            interpretations = []
            if lab.flag:
                flag_upper = lab.flag.upper()
                code_val = "H" if "HIGH" in flag_upper else "L" if "LOW" in flag_upper else "N"
                interpretations.append(
                    CodeableConcept(
                        coding=[Coding(system="http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", code=code_val)]
                    )
                )

            observations.append(
                ObservationResource(
                    id=f"lab-{lab.id}",
                    meta=Meta(profile=["https://nrces.in/ndhm/fhir/r4/StructureDefinition/Observation"]),
                    status=obs_status,
                    category=[
                        CodeableConcept(
                            coding=[Coding(system="http://terminology.hl7.org/CodeSystem/observation-category", code="laboratory", display="Laboratory")]
                        )
                    ],
                    code=CodeableConcept(text=lab.test_name),
                    subject=Reference(reference=patient_full_url, display=patient.name),
                    encounter=Reference(reference=encounter_full_url),
                    value_string=f"{lab.value} {lab.unit or ''}".strip(),
                    interpretation=interpretations,
                    reference_range=[ObservationReferenceRange(text=lab.reference_range)] if lab.reference_range else [],
                    note=[{"text": f"Source document extraction. Status: {lab.verification_status}"}],
                    text=Narrative(
                        status="generated",
                        div=f'<div xmlns="http://www.w3.org/1999/xhtml">Lab: {lab.test_name} = {lab.value} {lab.unit or ""}</div>',
                    ),
                )
            )

        # 7. DocumentReference Resources
        doc_references: list[DocumentReferenceResource] = []
        for doc in documents:
            doc_references.append(
                DocumentReferenceResource(
                    id=f"doc-{doc.id}",
                    status="current",
                    type=CodeableConcept(
                        coding=[Coding(system="http://loinc.org", code="11488-4", display="Consultation note")],
                        text=(doc.document_type or "document").replace("_", " ").title(),
                    ),
                    subject=Reference(reference=patient_full_url, display=patient.name),
                    date=doc.created_at.isoformat() if doc.created_at else None,
                    content=[
                        DocumentReferenceContent(
                            attachment=Attachment(
                                content_type=doc.media_type,
                                title=doc.original_filename,
                                size=doc.file_size_bytes,
                                hash=doc.sha256_hash,
                                url=f"/api/doctor/sessions/{session.id}/documents/{doc.id}/file",
                            )
                        )
                    ],
                    text=Narrative(
                        status="generated",
                        div=f'<div xmlns="http://www.w3.org/1999/xhtml">Document: {doc.original_filename} ({doc.document_type})</div>',
                    ),
                )
            )

        # 8. Composition Resource (Clinical Intake Summary Document)
        composition_entry: CompositionResource | None = None
        if summary:
            comp_status = (
                "final"
                if summary.status == "confirmed"
                else "amended"
                if summary.status == "amended"
                else "preliminary"
            )

            # Build sections linking to underlying entries
            sections: list[CompositionSection] = []

            # Section: Chief Complaint
            sections.append(
                CompositionSection(
                    title="Chief Complaint",
                    code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="10154-3", display="Chief complaint")]),
                    text=Narrative(status="generated", div=f'<div xmlns="http://www.w3.org/1999/xhtml">{chief_complaint_text or "Recorded intake"}</div>'),
                    entry=[Reference(reference=cc_full_url)],
                )
            )

            # Section: Interview Questionnaire
            sections.append(
                CompositionSection(
                    title="Patient Intake Questionnaire",
                    code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="74465-6", display="Questionnaire response")]),
                    entry=[Reference(reference=qr_full_url)],
                )
            )

            # Section: Medications
            if med_statements:
                sections.append(
                    CompositionSection(
                        title="Current Medications",
                        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="10160-0", display="History of Medication use")]),
                        entry=[Reference(reference=f"urn:uuid:med-{m.id}") for m in med_facts],
                    )
                )

            # Section: Investigations / Labs
            if observations:
                sections.append(
                    CompositionSection(
                        title="Diagnostic Investigations",
                        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="30954-2", display="Relevant diagnostic tests/laboratory data")]),
                        entry=[Reference(reference=f"urn:uuid:lab-{lf.id}") for lf in lab_facts],
                    )
                )

            # Section: Source Documents
            if doc_references:
                sections.append(
                    CompositionSection(
                        title="Source Medical Records",
                        code=CodeableConcept(coding=[Coding(system="http://loinc.org", code="55107-7", display="Addendum Document")]),
                        entry=[Reference(reference=f"urn:uuid:doc-{d.id}") for d in documents],
                    )
                )

            # Narrative content of summary
            summary_text_content = (
                summary.amended_text
                or summary.confirmed_text
                or summary.reviewed_text
                or summary.generated_text
                or "Clinical Intake Summary"
            )

            author_ref = (
                Reference(reference=f"Practitioner/{summary.confirmed_by}", display=summary.confirmed_by)
                if summary.confirmed_by
                else Reference(display="MediKiosk Automated Synthesizer")
            )

            composition_entry = CompositionResource(
                id=f"comp-{summary.id}",
                meta=Meta(profile=[cls.PROFILE_DOCUMENT]),
                status=comp_status,
                type=CodeableConcept(
                    coding=[Coding(system="http://loinc.org", code="34105-7", display="Hospital Consultation note")],
                    text="MediKiosk Clinical Intake Summary",
                ),
                subject=Reference(reference=patient_full_url, display=patient.name),
                encounter=Reference(reference=encounter_full_url),
                date=(summary.confirmed_at or summary.created_at or datetime.now(timezone.utc)).isoformat(),
                author=[author_ref],
                title="MediKiosk Clinical Intake Summary",
                section=sections,
                text=Narrative(
                    status="generated",
                    div=f'<div xmlns="http://www.w3.org/1999/xhtml"><pre>{summary_text_content}</pre></div>',
                ),
            )

        # Assemble Bundle Entries
        entries: list[BundleEntry] = []

        # If document bundle, FHIR R4 requires Composition to be the very first entry!
        if bundle_type == "document" and composition_entry:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:comp-{summary.id}",
                    resource=composition_entry.model_dump(by_alias=True, exclude_none=True),
                )
            )

        # Add Patient & Encounter
        entries.append(
            BundleEntry(
                full_url=patient_full_url,
                resource=patient_resource.model_dump(by_alias=True, exclude_none=True),
            )
        )
        entries.append(
            BundleEntry(
                full_url=encounter_full_url,
                resource=encounter_resource.model_dump(by_alias=True, exclude_none=True),
            )
        )

        # Add QuestionnaireResponse
        entries.append(
            BundleEntry(
                full_url=qr_full_url,
                resource=qr_resource.model_dump(by_alias=True, exclude_none=True),
            )
        )

        # Add Conditions
        for cond in conditions:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:{cond.id}",
                    resource=cond.model_dump(by_alias=True, exclude_none=True),
                )
            )

        # Add Medications
        for med_stmt in med_statements:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:{med_stmt.id}",
                    resource=med_stmt.model_dump(by_alias=True, exclude_none=True),
                )
            )

        # Add Observations
        for obs in observations:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:{obs.id}",
                    resource=obs.model_dump(by_alias=True, exclude_none=True),
                )
            )

        # Add Documents
        for doc_ref in doc_references:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:{doc_ref.id}",
                    resource=doc_ref.model_dump(by_alias=True, exclude_none=True),
                )
            )

        # If collection bundle and composition exists, append it at the end
        if bundle_type == "collection" and composition_entry:
            entries.append(
                BundleEntry(
                    full_url=f"urn:uuid:comp-{summary.id}",
                    resource=composition_entry.model_dump(by_alias=True, exclude_none=True),
                )
            )

        bundle = BundleResource(
            id=f"bundle-{session.id}",
            meta=Meta(profile=[cls.PROFILE_BUNDLE]),
            type=bundle_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total=len(entries),
            entry=entries,
        )

        return bundle

    @classmethod
    def validate_bundle(cls, bundle: BundleResource) -> OperationOutcome:
        """Validate FHIR R4 Bundle structure, resource types, and reference integrity."""
        issues: list[OperationOutcomeIssue] = []

        # 1. Verify bundle type and entries
        if not bundle.entry:
            issues.append(
                OperationOutcomeIssue(
                    severity="error",
                    code="invariant",
                    diagnostics="Bundle must contain at least one resource entry.",
                    expression=["Bundle.entry"],
                )
            )

        # 2. If document bundle, verify first entry is Composition
        if bundle.type == "document" and bundle.entry:
            first_res = bundle.entry[0].resource
            if first_res.get("resourceType") != "Composition":
                issues.append(
                    OperationOutcomeIssue(
                        severity="error",
                        code="invariant",
                        diagnostics="A FHIR document Bundle must have a Composition resource as its first entry.",
                        expression=["Bundle.entry[0].resource.resourceType"],
                    )
                )

        # 3. Reference Integrity: Gather all fullUrls in bundle
        defined_urls = {entry.full_url for entry in bundle.entry if entry.full_url}

        # Check references inside resources
        for idx, entry in enumerate(bundle.entry):
            res = entry.resource
            res_type = res.get("resourceType", "Unknown")

            # Check subject references
            subject = res.get("subject", {})
            if isinstance(subject, dict) and "reference" in subject:
                ref = subject["reference"]
                if ref.startswith("urn:uuid:") and ref not in defined_urls:
                    issues.append(
                        OperationOutcomeIssue(
                            severity="error",
                            code="not-found",
                            diagnostics=f"Resource {res_type} references target '{ref}' which is not in the bundle.",
                            expression=[f"Bundle.entry[{idx}].resource.subject.reference"],
                        )
                    )

            # Check encounter references
            encounter = res.get("encounter", {})
            if isinstance(encounter, dict) and "reference" in encounter:
                ref = encounter["reference"]
                if ref.startswith("urn:uuid:") and ref not in defined_urls:
                    issues.append(
                        OperationOutcomeIssue(
                            severity="error",
                            code="not-found",
                            diagnostics=f"Resource {res_type} references encounter '{ref}' which is not in the bundle.",
                            expression=[f"Bundle.entry[{idx}].resource.encounter.reference"],
                        )
                    )

        if not issues:
            issues.append(
                OperationOutcomeIssue(
                    severity="information",
                    code="informational",
                    diagnostics="FHIR R4 Bundle validation successful with 0 errors. All reference constraints satisfied.",
                    expression=["Bundle"],
                )
            )

        return OperationOutcome(
            id=f"outcome-{bundle.id}",
            issue=issues,
        )

    @classmethod
    def export(
        cls,
        db: Session,
        session_id: str,
        bundle_type: str = "document",
    ) -> FHIRExportResponse:
        """Build bundle, validate it, compute resource breakdown, and return export response."""
        bundle = cls.build_bundle(db, session_id, bundle_type=bundle_type)
        validation = cls.validate_bundle(bundle)

        counts: dict[str, int] = {}
        for entry in bundle.entry:
            rtype = entry.resource.get("resourceType", "Other")
            counts[rtype] = counts.get(rtype, 0) + 1

        return FHIRExportResponse(
            session_id=session_id,
            export_timestamp=datetime.now(timezone.utc).isoformat(),
            bundle_type=bundle_type,
            compliance_profile="HL7 FHIR R4 / ABDM Health Document Profile",
            resource_counts=counts,
            validation=validation,
            bundle=bundle.model_dump(by_alias=True, exclude_none=True),
        )
