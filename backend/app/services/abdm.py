import json
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DBSession

from app.models.abdm_record import ABDMRecord
from app.models.audit_log import AuditLog
from app.models.patient import Patient
from app.models.session import Session as IntakeSession
from app.schemas.abdm import (
    ABDMCareContextLinkResponse,
    ABDMProfile,
    ABDMStatusResponse,
    ABDMVerificationResponse,
)


class ABDMService:
    @staticmethod
    def _is_valid_abha(abha_str: str) -> bool:
        clean = abha_str.strip()
        # 14-digit pattern with optional hyphens: 91-1234-5678-9012 or 12345678901234
        if re.match(r"^\d{2}-\d{4}-\d{4}-\d{4}$", clean) or re.match(r"^\d{14}$", clean):
            return True
        # ABHA address pattern: user@abdm or user@sbx or user.name@domain
        if re.match(r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9_-]+$", clean):
            return True
        return False

    @staticmethod
    def _format_abha_number(abha_str: str) -> str:
        digits = re.sub(r"\D", "", abha_str)
        if len(digits) == 14:
            return f"{digits[0:2]}-{digits[2:6]}-{digits[6:10]}-{digits[10:14]}"
        # Generate deterministic mock 14-digit ABHA from string
        h = abs(hash(abha_str))
        num_str = f"91{str(h).ljust(12, '0')[:12]}"
        return f"{num_str[0:2]}-{num_str[2:6]}-{num_str[6:10]}-{num_str[10:14]}"

    @classmethod
    def get_or_create_record(cls, db: DBSession, session_id: str) -> ABDMRecord:
        record = db.query(ABDMRecord).filter(ABDMRecord.session_id == session_id).first()
        if not record:
            session = db.query(IntakeSession).filter(IntakeSession.id == session_id).first()
            if not session:
                raise ValueError(f"Session {session_id} not found")
            patient = db.query(Patient).filter(Patient.id == session.patient_id).first()
            patient_id = patient.id if patient else ""

            abha_addr = patient.demo_abha_id if patient and patient.demo_abha_id else None
            abha_num = cls._format_abha_number(abha_addr) if abha_addr else None

            record = ABDMRecord(
                id=str(uuid.uuid4()),
                session_id=session_id,
                patient_id=patient_id,
                abha_number=abha_num,
                abha_address=abha_addr,
                abha_status="mock_verified" if abha_addr else "unverified",
                care_context_status="unlinked",
                his_dispatch_status="not_dispatched",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
        return record

    @classmethod
    def verify_standalone_abha(
        cls, abha_input: str, auth_method: str = "mock_otp"
    ) -> ABDMVerificationResponse:
        clean = abha_input.strip()
        if not cls._is_valid_abha(clean):
            return ABDMVerificationResponse(
                success=False,
                profile=None,
                message="Invalid ABHA format. Expected 14-digit ABHA number (e.g. 91-1234-5678-9012) or ABHA address (e.g. user@abdm).",
            )

        if "@" in clean:
            addr = clean
            num = cls._format_abha_number(clean)
            display_name = clean.split("@")[0].replace(".", " ").title()
        else:
            num = cls._format_abha_number(clean)
            addr = f"patient_{digits_only(clean)[-4:]}@abdm"
            display_name = "Synthetic Patient"

        profile = ABDMProfile(
            abha_number=num,
            abha_address=addr,
            name=display_name,
            gender="Male",
            dob="1992-05-15",
            mobile_masked="XXXXXX9012",
            status="mock_verified",
        )
        return ABDMVerificationResponse(
            success=True,
            profile=profile,
            message="ABHA verified via ABDM Sandbox mock gateway.",
        )

    @classmethod
    def verify_abha(
        cls, db: DBSession, session_id: str, abha_input: str, auth_method: str = "mock_otp"
    ) -> ABDMVerificationResponse:
        session = db.query(IntakeSession).filter(IntakeSession.id == session_id).first()
        if not session:
            return ABDMVerificationResponse(success=False, profile=None, message="Session not found")
        patient = db.query(Patient).filter(Patient.id == session.patient_id).first()

        clean = abha_input.strip()
        if not cls._is_valid_abha(clean):
            return ABDMVerificationResponse(
                success=False,
                profile=None,
                message="Invalid ABHA format. Expected 14-digit ABHA number (e.g. 91-1234-5678-9012) or ABHA address (e.g. user@abdm).",
            )

        record = cls.get_or_create_record(db, session_id)

        if "@" in clean:
            addr = clean
            num = cls._format_abha_number(clean)
        else:
            num = cls._format_abha_number(clean)
            digits = re.sub(r"\D", "", clean)
            addr = f"{patient.name.lower().replace(' ', '') if patient else 'patient'}{digits[-4:]}@abdm"

        patient_name = patient.name if patient else "Synthetic Patient"
        profile = ABDMProfile(
            abha_number=num,
            abha_address=addr,
            name=patient_name,
            gender="Male",
            dob="1992-05-15",
            mobile_masked="XXXXXX9012",
            status="mock_verified",
        )

        record.abha_number = num
        record.abha_address = addr
        record.abha_status = "mock_verified"
        if patient:
            patient.demo_abha_id = addr

        # Record audit log
        audit = AuditLog(
            actor_user_id=None,
            actor_type="SYSTEM",
            action="ABHA_VERIFIED",
            entity_type="abdm_record",
            entity_id=session_id,
            metadata_json={
                "abha_number": num,
                "abha_address": addr,
                "auth_method": auth_method,
                "gateway": "abdm_sandbox_mock",
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(record)

        return ABDMVerificationResponse(
            success=True,
            profile=profile,
            message="ABHA verified via ABDM Sandbox mock gateway.",
        )

    @classmethod
    def link_care_context(
        cls, db: DBSession, session_id: str, current_user_id: str | None = None
    ) -> ABDMCareContextLinkResponse:
        session = db.query(IntakeSession).filter(IntakeSession.id == session_id).first()
        if not session:
            raise ValueError("Session not found")
        patient = db.query(Patient).filter(Patient.id == session.patient_id).first()

        record = cls.get_or_create_record(db, session_id)

        # Auto-populate demo ABHA if missing
        if not record.abha_address:
            addr = patient.demo_abha_id if patient and patient.demo_abha_id else f"{patient.name.lower().replace(' ', '') if patient else 'patient'}@abdm"
            record.abha_address = addr
            record.abha_number = cls._format_abha_number(addr)
            record.abha_status = "mock_verified"

        ctx_ref = f"medikiosk_ctx_{session_id[:8]}"
        display = f"MediKiosk OPD Intake - Token {session.hospital_token}"
        now_dt = datetime.now(timezone.utc)

        record.care_context_reference = ctx_ref
        record.care_context_display = display
        record.care_context_status = "linked"
        record.care_context_linked_at = now_dt

        # Log audit event
        audit = AuditLog(
            actor_user_id=current_user_id,
            actor_type="DOCTOR" if current_user_id else "SYSTEM",
            action="ABDM_CARE_CONTEXT_LINKED",
            entity_type="abdm_record",
            entity_id=session_id,
            metadata_json={
                "care_context_reference": ctx_ref,
                "display": display,
                "abha_address": record.abha_address,
                "abha_number": record.abha_number,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(record)

        return ABDMCareContextLinkResponse(
            success=True,
            care_context_reference=ctx_ref,
            display=display,
            status="linked",
            linked_at=now_dt,
            message="Care context successfully linked in ABDM Sandbox (M2).",
        )

    @classmethod
    def get_status(cls, db: DBSession, session_id: str) -> ABDMStatusResponse:
        record = cls.get_or_create_record(db, session_id)
        receipt_dict = None
        if record.his_dispatch_receipt:
            try:
                receipt_dict = json.loads(record.his_dispatch_receipt)
            except Exception:
                receipt_dict = {"raw": record.his_dispatch_receipt}

        return ABDMStatusResponse(
            session_id=record.session_id,
            patient_id=record.patient_id,
            abha_number=record.abha_number,
            abha_address=record.abha_address,
            abha_status=record.abha_status,
            care_context_reference=record.care_context_reference,
            care_context_display=record.care_context_display,
            care_context_status=record.care_context_status,
            care_context_linked_at=record.care_context_linked_at,
            his_dispatch_status=record.his_dispatch_status,
            his_dispatch_receipt=receipt_dict,
            his_dispatched_at=record.his_dispatched_at,
            consent_artefact_id=record.consent_artefact_id,
        )


def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)
