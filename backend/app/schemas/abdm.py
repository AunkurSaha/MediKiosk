from datetime import datetime

from pydantic import BaseModel, Field


class ABDMVerifyRequest(BaseModel):
    abha_input: str = Field(
        ...,
        min_length=3,
        max_length=128,
        description="ABHA address (e.g. user@abdm) or 14-digit ABHA number",
    )
    auth_method: str = Field(
        default="mock_otp", description="Authentication mode: mock_otp or demographic"
    )


class ABDMProfile(BaseModel):
    abha_number: str
    abha_address: str
    name: str
    gender: str
    dob: str
    mobile_masked: str
    status: str = Field(default="mock_verified")


class ABDMVerificationResponse(BaseModel):
    success: bool
    profile: ABDMProfile | None = None
    message: str


class ABDMCareContextLinkRequest(BaseModel):
    session_id: str


class ABDMCareContextLinkResponse(BaseModel):
    success: bool
    care_context_reference: str
    display: str
    status: str
    linked_at: datetime
    message: str


class ABDMStatusResponse(BaseModel):
    session_id: str
    patient_id: str
    abha_number: str | None = None
    abha_address: str | None = None
    abha_status: str = "unverified"
    care_context_reference: str | None = None
    care_context_display: str | None = None
    care_context_status: str = "unlinked"
    care_context_linked_at: datetime | None = None
    his_dispatch_status: str = "not_dispatched"
    his_dispatch_receipt: dict | None = None
    his_dispatched_at: datetime | None = None
    consent_artefact_id: str | None = None


class HISDispatchRequest(BaseModel):
    target_system: str = Field(default="default", max_length=64)


class HISDispatchResponse(BaseModel):
    success: bool
    dispatch_id: str
    target_endpoint: str
    status: str
    dispatched_at: datetime
    receipt_reference: str
    message: str
    attached_bundle_type: str = "document"
