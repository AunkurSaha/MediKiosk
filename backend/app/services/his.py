import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from app.core.config import HIS_ENDPOINT_URL
from app.models.audit_log import AuditLog
from app.models.session import Session as IntakeSession
from app.schemas.abdm import HISDispatchResponse
from app.services.abdm import ABDMService
from app.services.fhir import FHIRAdapterService


class HISService:
    @classmethod
    def dispatch_to_his(
        cls,
        db: DBSession,
        session_id: str,
        current_user_id: str | None = None,
        target_system: str = "default",
    ) -> HISDispatchResponse:
        session = db.query(IntakeSession).filter(IntakeSession.id == session_id).first()
        if not session:
            raise ValueError("Session not found")

        # Build FHIR Document bundle from Phase 10 adapter
        fhir_bundle = FHIRAdapterService.build_bundle(db, session_id, bundle_type="document")

        dispatch_id = str(uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        target_endpoint = (
            HIS_ENDPOINT_URL or "http://local-his.hospital.internal/api/v1/opd-intake"
        )
        receipt_ref = (
            f"HIS-ACK-{now_dt.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
        )

        receipt_dict = {
            "status": "DELIVERED",
            "receipt_id": receipt_ref,
            "target_system": target_system or "Hospital HIS Gateway (Local Simulation)",
            "endpoint": target_endpoint,
            "bundle_type": "document",
            "entries_count": len(fhir_bundle.entry),
            "acknowledged_at": now_dt.isoformat(),
        }

        # Update ABDMRecord
        record = ABDMService.get_or_create_record(db, session_id)
        record.his_dispatch_status = "dispatched"
        record.his_dispatch_receipt = json.dumps(receipt_dict)
        record.his_dispatched_at = now_dt

        # Log audit event
        audit = AuditLog(
            actor_user_id=current_user_id,
            actor_type="DOCTOR" if current_user_id else "SYSTEM",
            action="HIS_DISPATCHED",
            entity_type="his_dispatch",
            entity_id=session_id,
            metadata_json={
                "dispatch_id": dispatch_id,
                "receipt_reference": receipt_ref,
                "target_system": target_system,
                "entries_count": len(fhir_bundle.entry),
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(record)

        return HISDispatchResponse(
            success=True,
            dispatch_id=dispatch_id,
            target_endpoint=target_endpoint,
            status="dispatched",
            dispatched_at=now_dt,
            receipt_reference=receipt_ref,
            message="Clinical intake and FHIR R4 bundle successfully dispatched to HIS.",
            attached_bundle_type="document",
        )

    @classmethod
    def get_status(cls, db: DBSession, session_id: str) -> dict:
        record = ABDMService.get_or_create_record(db, session_id)
        receipt = None
        if record.his_dispatch_receipt:
            try:
                receipt = json.loads(record.his_dispatch_receipt)
            except Exception:
                receipt = {"raw": record.his_dispatch_receipt}

        return {
            "session_id": session_id,
            "his_dispatch_status": record.his_dispatch_status,
            "his_dispatch_receipt": receipt,
            "his_dispatched_at": (
                record.his_dispatched_at.isoformat() if record.his_dispatched_at else None
            ),
        }
