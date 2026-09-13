from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_current_user, require_assigned_doctor_session
from app.database import get_db
from app.services import intake

router = APIRouter()


@router.get("/context", response_model=schemas.AuthUserResponse)
def get_doctor_context(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.auth_service import get_auth_user_response

    return get_auth_user_response(db, user)


@router.put("/context", response_model=schemas.AuthUserResponse)
def update_doctor_context(
    payload: schemas.AuthUserResponse,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.auth_service import get_auth_user_response, sync_doctor_memberships

    sync_doctor_memberships(
        db,
        doctor_id=user.id,
        hospital_id=payload.hospital_id,
        specialty=payload.specialty,
        qualification=payload.qualification,
        name=payload.name if payload.name != user.name else None,
    )
    db.commit()
    return get_auth_user_response(db, user)


@router.get("/sessions", response_model=schemas.SessionList)
def read_doctor_sessions(
    hospital_id: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = (
        select(
            models.Session,
            models.Patient.name,
            models.DoctorQueueEntry.status,
            models.DoctorQueueEntry.joined_at,
        )
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .join(models.Consent, models.Consent.session_id == models.Session.id)
        .outerjoin(models.DoctorQueueEntry, models.DoctorQueueEntry.session_id == models.Session.id)
        .where(
            models.Consent.share_with_doctor.is_(True),
            models.Session.selected_doctor_id == user.id,
            models.Session.status.in_(["ready_for_review", "under_review", "confirmed"]),
        )
    )
    if hospital_id:
        query = query.where(models.Session.hospital_id == hospital_id)

    rows = db.execute(
        query.order_by(
            models.DoctorQueueEntry.status != "WAITING",
            models.DoctorQueueEntry.joined_at.asc(),
            models.Session.id,
        )
    ).all()
    return schemas.SessionList(
        items=[
            schemas.SessionListItem(
                **schemas.Session.model_validate(s).model_dump(),
                patient_name=name,
                queue_status=queue_status,
                queue_joined_at=joined_at,
            )
            for s, name, queue_status, joined_at in rows
        ]
    )


@router.put("/sessions/{session_id}/queue", response_model=schemas.QueueEntryResponse)
def update_queue(
    session_id: UUID,
    payload: schemas.QueueTransition,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.doctor_routing import transition_queue

    return transition_queue(db, str(session_id), payload.status, user)


@router.get("/sessions/{session_id}", response_model=schemas.SessionDetail)
def read_session_detail(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    result = intake.detail(db, str(session_id), doctor=True, user=user)
    intake.audit(db, "session_viewed", str(session_id), user)
    db.commit()
    return result


@router.get("/sessions/{session_id}/summary", response_model=schemas.ClinicalSummary)
def read_summary(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.get_summary(db, str(session_id))


@router.post("/sessions/{session_id}/summary/regenerate", response_model=schemas.ClinicalSummary)
def regenerate_summary(
    session_id: UUID,
    payload: schemas.SummaryRegenerateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.regenerate_summary(db, str(session_id), payload, user)


@router.put("/sessions/{session_id}/summary", response_model=schemas.ClinicalSummary)
def update_summary(
    session_id: UUID,
    payload: schemas.ClinicalSummaryUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.review_summary(db, str(session_id), payload, user)


@router.post("/sessions/{session_id}/summary/confirm", response_model=schemas.ClinicalSummary)
def confirm_summary(
    session_id: UUID,
    payload: schemas.SummaryConfirm,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.review_summary(db, str(session_id), payload, user, confirm=True)


@router.get(
    "/sessions/{session_id}/summary/revisions",
    response_model=list[schemas.SummaryRevisionRecord],
)
def read_summary_revisions(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.get_summary_revisions(db, str(session_id))


@router.get(
    "/sessions/{session_id}/summary/evidence",
    response_model=list[schemas.EvidenceReference],
)
def read_summary_evidence(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
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
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.amend_summary(db, str(session_id), payload, user)


@router.get(
    "/sessions/{session_id}/field-verifications",
    response_model=schemas.FieldVerificationList,
)
def read_field_verifications(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
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
    user: models.User = Depends(require_assigned_doctor_session),
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
    user: models.User = Depends(require_assigned_doctor_session),
):
    return intake.get_audit_trail(db, str(session_id))


@router.get(
    "/sessions/{session_id}/cross-references",
    response_model=schemas.CrossReferenceResponse,
)
def read_cross_references(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_assigned_doctor_session),
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

    intake.detail(db, str(session_id), doctor=True, user=user)
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

    intake.detail(db, str(session_id), doctor=True, user=user)
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

    intake.detail(db, str(session_id), doctor=True, user=user)
    bundle = FHIRAdapterService.build_bundle(db, str(session_id), bundle_type=bundle_type)
    return FHIRAdapterService.validate_bundle(bundle)


@router.get(
    "/sessions/{session_id}/abdm/status",
    response_model=schemas.ABDMStatusResponse,
)
def get_abdm_status(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.abdm import ABDMService

    intake.detail(db, str(session_id), doctor=True, user=user)
    return ABDMService.get_status(db, str(session_id))


@router.post(
    "/sessions/{session_id}/abdm/verify-abha",
    response_model=schemas.ABDMVerificationResponse,
)
def verify_abha(
    session_id: UUID,
    req: schemas.ABDMVerifyRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.abdm import ABDMService

    intake.detail(db, str(session_id), doctor=True, user=user)
    return ABDMService.verify_abha(db, str(session_id), req.abha_input, auth_method=req.auth_method)


@router.post(
    "/sessions/{session_id}/abdm/link-care-context",
    response_model=schemas.ABDMCareContextLinkResponse,
)
def link_care_context(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.abdm import ABDMService

    intake.detail(db, str(session_id), doctor=True, user=user)
    return ABDMService.link_care_context(db, str(session_id), current_user_id=user.id)


@router.post(
    "/sessions/{session_id}/his/dispatch",
    response_model=schemas.HISDispatchResponse,
)
def dispatch_to_his(
    session_id: UUID,
    req: schemas.HISDispatchRequest | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.his import HISService

    intake.detail(db, str(session_id), doctor=True, user=user)
    target_system = req.target_system if req else "default"
    return HISService.dispatch_to_his(
        db, str(session_id), current_user_id=user.id, target_system=target_system
    )


@router.get("/sessions/{session_id}/his/status")
def get_his_status(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.services.his import HISService

    return HISService.get_status(db, str(session_id))


@router.post("/demo/seed-showcase", response_model=schemas.ShowcaseSeedResponse)
def seed_showcase(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.core.config import demo_enabled
    from app.services.showcase import ShowcaseService

    if not demo_enabled():
        raise HTTPException(status_code=403, detail="Demo endpoints disabled in this environment.")
    return ShowcaseService.seed_showcase_patient(db, actor_user_id=user.id)


@router.post("/demo/reset", response_model=schemas.DemoResetResponse)
def reset_demo(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    from app.core.config import demo_enabled
    from app.services.showcase import ShowcaseService

    if not demo_enabled():
        raise HTTPException(status_code=403, detail="Demo endpoints disabled in this environment.")
    return ShowcaseService.reset_demo_data(db)


@router.post(
    "/sessions/{session_id}/translate", response_model=schemas.translation.TranslationResponse
)
async def translate_text(
    session_id: UUID,
    payload: schemas.translation.TranslationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = db.get(models.Session, str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from app.services.translation_provider import get_translation_provider

    provider = get_translation_provider()
    return await provider.translate(
        text=payload.text,
        source_language=payload.source_language,
        target_language=payload.target_language,
    )


@router.post(
    "/sessions/{session_id}/transliterate",
    response_model=schemas.translation.TransliterationResponse,
)
async def transliterate_text(
    session_id: UUID,
    payload: schemas.translation.TransliterationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = db.get(models.Session, str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from app.services.translation_provider import get_translation_provider

    provider = get_translation_provider()
    return await provider.transliterate(
        text=payload.text,
        source_language=payload.source_language,
        target_language=payload.target_language,
    )


@router.post(
    "/sessions/{session_id}/identify-language",
    response_model=schemas.translation.LanguageIdentificationResponse,
)
async def identify_language(
    session_id: UUID,
    payload: schemas.translation.LanguageIdentificationRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session = db.get(models.Session, str(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    from app.services.translation_provider import get_translation_provider

    provider = get_translation_provider()
    return await provider.identify_language(text=payload.text)
