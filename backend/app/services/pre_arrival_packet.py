import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import HANDOFF_TOKEN_EXPIRY_MINUTES, PACKET_EXPIRY_MINUTES
from app.core.errors import WorkflowError
from app.services import intake

PACKET_VERSION = "1.0"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _audit(db: Session, action: str, packet, user) -> None:
    db.add(
        models.AuditLog(
            actor_user_id=user.id if user else None,
            actor_type=user.role if user else "system",
            action=action,
            entity_type="pre_arrival_packet",
            entity_id=packet.id,
            metadata_json={"packet_id": packet.id},
        )
    )


def _session_for_patient(db: Session, session_id: str, user):
    session = intake.get_session(db, session_id)
    intake.verify_session_access(db, session, user)
    if user is None or user.role != "patient":
        raise WorkflowError("FORBIDDEN", "Patient access is required.", 403)
    return session


def _metadata(packet) -> schemas.PacketMetadata:
    status = packet.status
    if status == "ACTIVE" and _aware(packet.expires_at) <= _now():
        status = "EXPIRED"
    return schemas.PacketMetadata(
        packet_id=packet.id,
        session_id=packet.session_id,
        packet_version=packet.packet_version,
        status=status,
        created_at=packet.created_at,
        expires_at=packet.expires_at,
    )


def get_or_create(db: Session, session_id: str, user) -> schemas.PacketMetadata:
    session = _session_for_patient(db, session_id, user)
    if session.status not in ("ready_for_review", "under_review", "confirmed"):
        raise WorkflowError(
            "PACKET_NOT_READY", "Complete the intake before creating a packet.", 409
        )
    if not session.hospital_id or not session.selected_doctor_id:
        raise WorkflowError("PACKET_NOT_READY", "Facility and doctor selection are required.", 409)
    packet = db.scalar(
        select(models.PreArrivalPacketRecord).where(
            models.PreArrivalPacketRecord.session_id == session.id,
            models.PreArrivalPacketRecord.packet_version == PACKET_VERSION,
        )
    )
    if packet:
        return _metadata(packet)
    snapshot = intake.build_pre_arrival_packet(db, session.id)
    packet = models.PreArrivalPacketRecord(
        session_id=session.id,
        patient_id=session.patient_id,
        hospital_id=session.hospital_id,
        doctor_id=session.selected_doctor_id,
        packet_version=PACKET_VERSION,
        snapshot_json=snapshot.model_dump(mode="json"),
        status="ACTIVE",
        expires_at=_now() + timedelta(minutes=PACKET_EXPIRY_MINUTES),
        created_by=user.id,
    )
    db.add(packet)
    try:
        db.flush()
        _audit(db, "PACKET_CREATED", packet, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        packet = db.scalar(
            select(models.PreArrivalPacketRecord).where(
                models.PreArrivalPacketRecord.session_id == session.id,
                models.PreArrivalPacketRecord.packet_version == PACKET_VERSION,
            )
        )
        if packet is None:
            raise
    db.refresh(packet)
    return _metadata(packet)


def get_packet(db: Session, session_id: str, user) -> schemas.PacketView:
    _session_for_patient(db, session_id, user)
    packet = db.scalar(
        select(models.PreArrivalPacketRecord).where(
            models.PreArrivalPacketRecord.session_id == session_id
        )
    )
    if packet is None:
        raise WorkflowError("PACKET_NOT_FOUND", "Pre-arrival packet not found.", 404)
    queue = db.scalar(
        select(models.DoctorQueueEntry).where(
            models.DoctorQueueEntry.session_id == packet.session_id
        )
    )
    return schemas.PacketView(
        **_metadata(packet).model_dump(),
        snapshot=schemas.PreArrivalPacket.model_validate(packet.snapshot_json).model_dump(
            mode="json"
        ),
        live_queue={"status": queue.status, "visit_token": queue.visit_token} if queue else None,
    )


def issue_token(db: Session, session_id: str, user) -> schemas.HandoffTokenIssued:
    _session_for_patient(db, session_id, user)
    packet = db.scalar(
        select(models.PreArrivalPacketRecord)
        .where(models.PreArrivalPacketRecord.session_id == session_id)
        .with_for_update()
    )
    if packet is None:
        raise WorkflowError("PACKET_NOT_FOUND", "Pre-arrival packet not found.", 404)
    _validate_packet(packet)
    rotated = packet.handoff_token_hash is not None
    raw_token = secrets.token_urlsafe(32)
    packet.handoff_token_hash = _hash_token(raw_token)
    packet.handoff_token_expires_at = _now() + timedelta(minutes=HANDOFF_TOKEN_EXPIRY_MINUTES)
    _audit(db, "HANDOFF_TOKEN_ROTATED" if rotated else "HANDOFF_TOKEN_ISSUED", packet, user)
    db.commit()
    metadata = _metadata(packet)
    return schemas.HandoffTokenIssued(
        **metadata.model_dump(),
        handoff_token=raw_token,
        handoff_url=f"/handoff/p/{raw_token}",
        handoff_token_expires_at=packet.handoff_token_expires_at,
    )


def revoke(db: Session, session_id: str, user) -> schemas.PacketMetadata:
    _session_for_patient(db, session_id, user)
    packet = db.scalar(
        select(models.PreArrivalPacketRecord)
        .where(models.PreArrivalPacketRecord.session_id == session_id)
        .with_for_update()
    )
    if packet is None:
        raise WorkflowError("PACKET_NOT_FOUND", "Pre-arrival packet not found.", 404)
    if packet.status != "REVOKED":
        packet.status = "REVOKED"
        packet.revoked_at = _now()
        _audit(db, "PACKET_REVOKED", packet, user)
        db.commit()
    return _metadata(packet)


def _validate_packet(packet) -> None:
    if packet.status == "REVOKED" or packet.revoked_at is not None:
        raise WorkflowError("PACKET_REVOKED", "This handoff link is no longer active.", 410)
    if _aware(packet.expires_at) <= _now():
        raise WorkflowError("PACKET_EXPIRED", "This handoff link has expired.", 410)


def resolve(db: Session, raw_token: str, user) -> schemas.HandoffResolution | schemas.PacketView:
    packet = db.scalar(
        select(models.PreArrivalPacketRecord).where(
            models.PreArrivalPacketRecord.handoff_token_hash == _hash_token(raw_token)
        )
    )
    if packet is None:
        raise WorkflowError("PACKET_NOT_FOUND", "This handoff link is invalid.", 404)
    _validate_packet(packet)
    if packet.handoff_token_expires_at is None or _aware(packet.handoff_token_expires_at) <= _now():
        raise WorkflowError("HANDOFF_TOKEN_EXPIRED", "This handoff link has expired.", 410)
    if user is None:
        return schemas.HandoffResolution(status="AUTH_REQUIRED")
    if user.role != "doctor" or user.id != packet.doctor_id:
        raise WorkflowError("FORBIDDEN", "You do not have access to this patient handoff.", 403)
    session = intake.get_session(db, packet.session_id)
    intake.verify_session_access(db, session, user)
    queue = db.scalar(
        select(models.DoctorQueueEntry).where(
            models.DoctorQueueEntry.session_id == packet.session_id
        )
    )
    packet.last_accessed_at = _now()
    _audit(db, "PACKET_VIEWED", packet, user)
    db.commit()
    return schemas.PacketView(
        **_metadata(packet).model_dump(),
        snapshot=schemas.PreArrivalPacket.model_validate(packet.snapshot_json).model_dump(
            mode="json"
        ),
        live_queue={"status": queue.status, "visit_token": queue.visit_token} if queue else None,
    )
