from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_current_user
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.get("/sessions", response_model=schemas.SessionList)
def read_doctor_sessions(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows = db.execute(
        select(models.Session, models.Patient.name)
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .join(models.Consent, models.Consent.session_id == models.Session.id)
        .where(
            models.Consent.share_with_doctor.is_(True),
            models.Session.status.in_(["ready_for_review", "under_review", "confirmed"]),
        )
        .order_by(models.Session.created_at.desc(), models.Session.id)
    ).all()
    return schemas.SessionList(
        items=[
            schemas.SessionListItem(
                **schemas.Session.model_validate(s).model_dump(), patient_name=name
            )
            for s, name in rows
        ]
    )


@router.get("/sessions/{session_id}", response_model=schemas.SessionDetail)
def read_session_detail(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    result = intake.detail(db, str(session_id), doctor=True)
    intake.audit(db, "session_viewed", str(session_id), user)
    db.commit()
    return result


@router.get("/sessions/{session_id}/summary", response_model=schemas.ClinicalSummary)
def read_summary(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.get_summary(db, str(session_id))


@router.post("/sessions/{session_id}/summary/regenerate", response_model=schemas.ClinicalSummary)
def regenerate_summary(
    session_id: UUID,
    payload: schemas.SummaryRegenerateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.regenerate_summary(db, str(session_id), payload, user)


@router.put("/sessions/{session_id}/summary", response_model=schemas.ClinicalSummary)
def update_summary(
    session_id: UUID,
    payload: schemas.ClinicalSummaryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.review_summary(db, str(session_id), payload, user)


@router.post("/sessions/{session_id}/summary/confirm", response_model=schemas.ClinicalSummary)
def confirm_summary(
    session_id: UUID,
    payload: schemas.SummaryConfirm,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.review_summary(db, str(session_id), payload, user, confirm=True)


@router.get(
    "/sessions/{session_id}/summary/revisions",
    response_model=list[schemas.SummaryRevisionRecord],
)
def read_summary_revisions(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.get_summary_revisions(db, str(session_id))


@router.get(
    "/sessions/{session_id}/summary/evidence",
    response_model=list[schemas.EvidenceReference],
)
def read_summary_evidence(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.get_summary_evidence(db, str(session_id))


@router.post(
    "/sessions/{session_id}/summary/amend",
    response_model=schemas.ClinicalSummary,
)
def amend_summary(
    session_id: UUID,
    payload: schemas.SummaryAmendRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.amend_summary(db, str(session_id), payload, user)


@router.get(
    "/sessions/{session_id}/field-verifications",
    response_model=schemas.FieldVerificationList,
)
def read_field_verifications(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services import field_verification

    return field_verification.get_verifications(db, str(session_id))


@router.post(
    "/sessions/{session_id}/field-verifications",
    response_model=schemas.FieldVerificationRecord,
)
def create_or_update_field_verification(
    session_id: UUID,
    payload: schemas.FieldVerificationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services import field_verification

    return field_verification.verify_field(db, str(session_id), payload, user)


@router.get(
    "/sessions/{session_id}/audit-trail",
    response_model=schemas.AuditTrailResponse,
)
def read_audit_trail(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return intake.get_audit_trail(db, str(session_id))


@router.get(
    "/sessions/{session_id}/cross-references",
    response_model=schemas.CrossReferenceResponse,
)
def read_cross_references(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services import cross_reference

    return cross_reference.get_cross_references(db, str(session_id))


@router.get(
    "/sessions/{session_id}/fhir/export",
    response_model=schemas.FHIRExportResponse,
)
def export_fhir(
    session_id: UUID,
    bundle_type: str = "document",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.fhir import FHIRAdapterService

    intake.detail(db, str(session_id), doctor=True)
    res = FHIRAdapterService.export(db, str(session_id), bundle_type=bundle_type)
    intake.audit(db, "FHIR_EXPORTED", str(session_id), user, {"bundle_type": bundle_type})
    db.commit()
    return res


@router.get("/sessions/{session_id}/fhir/bundle")
def get_fhir_bundle(
    session_id: UUID,
    bundle_type: str = "document",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from fastapi.responses import JSONResponse

    from app.services.fhir import FHIRAdapterService

    intake.detail(db, str(session_id), doctor=True)
    bundle = FHIRAdapterService.build_bundle(db, str(session_id), bundle_type=bundle_type)
    intake.audit(db, "FHIR_BUNDLE_ACCESSED", str(session_id), user, {"bundle_type": bundle_type})
    db.commit()
    return JSONResponse(
        content=bundle.model_dump(by_alias=True, exclude_none=True),
        media_type="application/fhir+json",
    )


@router.post(
    "/sessions/{session_id}/fhir/validate",
    response_model=schemas.OperationOutcome,
)
def validate_fhir(
    session_id: UUID,
    bundle_type: str = "document",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.fhir import FHIRAdapterService

    intake.detail(db, str(session_id), doctor=True)
    bundle = FHIRAdapterService.build_bundle(db, str(session_id), bundle_type=bundle_type)
    return FHIRAdapterService.validate_bundle(bundle)

