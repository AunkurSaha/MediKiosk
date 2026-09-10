from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.fhir.base import (
    Attachment,
    CodeableConcept,
    Coding,
    FHIRBaseModel,
    HumanName,
    Identifier,
    Meta,
    Narrative,
    Period,
    Quantity,
    Reference,
)


class PatientCommunication(FHIRBaseModel):
    language: CodeableConcept
    preferred: bool = True


class PatientResource(FHIRBaseModel):
    resource_type: str = Field(default="Patient", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    active: bool = True
    name: list[HumanName] = Field(default_factory=list)
    gender: str | None = None  # male | female | other | unknown
    birth_date: str | None = Field(default=None, alias="birthDate")
    communication: list[PatientCommunication] = Field(default_factory=list)


class EncounterStatusHistory(FHIRBaseModel):
    status: str
    period: Period


class EncounterClass(FHIRBaseModel):
    system: str = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
    code: str = "AMB"
    display: str = "ambulatory"


class EncounterResource(FHIRBaseModel):
    resource_type: str = Field(default="Encounter", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    status: str = "finished"  # planned | arrived | triaged | in-progress | onleave | finished | cancelled
    class_code: EncounterClass = Field(default_factory=EncounterClass, alias="class")
    subject: Reference
    period: Period | None = None


class QuestionnaireResponseItemAnswer(FHIRBaseModel):
    value_string: str | None = Field(default=None, alias="valueString")
    value_boolean: bool | None = Field(default=None, alias="valueBoolean")
    value_integer: int | None = Field(default=None, alias="valueInteger")
    value_coding: Coding | None = Field(default=None, alias="valueCoding")


class QuestionnaireResponseItem(FHIRBaseModel):
    link_id: str = Field(alias="linkId")
    text: str | None = None
    answer: list[QuestionnaireResponseItemAnswer] = Field(default_factory=list)
    item: list["QuestionnaireResponseItem"] = Field(default_factory=list)


class QuestionnaireResponseResource(FHIRBaseModel):
    resource_type: str = Field(default="QuestionnaireResponse", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: Identifier | None = None
    status: str = "completed"  # in-progress | completed | amended | entered-in-error | stopped
    subject: Reference
    encounter: Reference | None = None
    authored: datetime | str | None = None
    author: Reference | None = None
    item: list[QuestionnaireResponseItem] = Field(default_factory=list)


class ConditionResource(FHIRBaseModel):
    resource_type: str = Field(default="Condition", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    clinical_status: CodeableConcept = Field(
        default_factory=lambda: CodeableConcept(
            coding=[Coding(system="http://terminology.hl7.org/CodeSystem/condition-clinical", code="active")]
        ),
        alias="clinicalStatus",
    )
    verification_status: CodeableConcept = Field(
        default_factory=lambda: CodeableConcept(
            coding=[Coding(system="http://terminology.hl7.org/CodeSystem/condition-ver-status", code="provisional")]
        ),
        alias="verificationStatus",
    )
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference
    encounter: Reference | None = None
    onset_date_time: str | None = Field(default=None, alias="onsetDateTime")
    recorded_date: str | None = Field(default=None, alias="recordedDate")
    note: list[dict[str, str]] = Field(default_factory=list)


class Dosage(FHIRBaseModel):
    text: str | None = None
    timing: dict[str, Any] | None = None
    route: CodeableConcept | None = None


class MedicationStatementResource(FHIRBaseModel):
    resource_type: str = Field(default="MedicationStatement", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    status: str = "active"  # active | completed | entered-in-error | intended | stopped | on-hold | unknown | not-taken
    status_reason: list[CodeableConcept] = Field(default_factory=list, alias="statusReason")
    category: CodeableConcept | None = None
    medication_codeable_concept: CodeableConcept = Field(alias="medicationCodeableConcept")
    subject: Reference
    context: Reference | None = None
    effective_period: Period | None = Field(default=None, alias="effectivePeriod")
    date_asserted: str | None = Field(default=None, alias="dateAsserted")
    information_source: Reference | None = Field(default=None, alias="informationSource")
    dosage: list[Dosage] = Field(default_factory=list)
    note: list[dict[str, str]] = Field(default_factory=list)


class ObservationReferenceRange(FHIRBaseModel):
    text: str | None = None


class ObservationResource(FHIRBaseModel):
    resource_type: str = Field(default="Observation", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    status: str = "final"  # registered | preliminary | final | amended | corrected | cancelled | entered-in-error | unknown
    category: list[CodeableConcept] = Field(default_factory=list)
    code: CodeableConcept
    subject: Reference
    encounter: Reference | None = None
    effective_date_time: str | None = Field(default=None, alias="effectiveDateTime")
    value_quantity: Quantity | None = Field(default=None, alias="valueQuantity")
    value_string: str | None = Field(default=None, alias="valueString")
    interpretation: list[CodeableConcept] = Field(default_factory=list)
    reference_range: list[ObservationReferenceRange] = Field(default_factory=list, alias="referenceRange")
    note: list[dict[str, str]] = Field(default_factory=list)


class DocumentReferenceContent(FHIRBaseModel):
    attachment: Attachment


class DocumentReferenceResource(FHIRBaseModel):
    resource_type: str = Field(default="DocumentReference", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: list[Identifier] = Field(default_factory=list)
    status: str = "current"  # current | superseded | entered-in-error
    doc_status: str = Field(default="final", alias="docStatus")
    type: CodeableConcept
    category: list[CodeableConcept] = Field(default_factory=list)
    subject: Reference
    date: str | None = None
    content: list[DocumentReferenceContent] = Field(default_factory=list)


class CompositionSection(FHIRBaseModel):
    title: str
    code: CodeableConcept | None = None
    text: Narrative | None = None
    entry: list[Reference] = Field(default_factory=list)


class CompositionResource(FHIRBaseModel):
    resource_type: str = Field(default="Composition", alias="resourceType")
    id: str
    meta: Meta | None = None
    text: Narrative | None = None
    identifier: Identifier | None = None
    status: str = "final"  # preliminary | final | amended | entered-in-error
    type: CodeableConcept
    category: list[CodeableConcept] = Field(default_factory=list)
    subject: Reference
    encounter: Reference | None = None
    date: str
    author: list[Reference] = Field(default_factory=list)
    title: str
    section: list[CompositionSection] = Field(default_factory=list)


class OperationOutcomeIssue(FHIRBaseModel):
    severity: str = "information"  # fatal | error | warning | information
    code: str = "informational"
    diagnostics: str | None = None
    expression: list[str] = Field(default_factory=list)


class OperationOutcome(FHIRBaseModel):
    resource_type: str = Field(default="OperationOutcome", alias="resourceType")
    id: str | None = None
    issue: list[OperationOutcomeIssue] = Field(default_factory=list)
