from pydantic import Field

from .common import APIModel


class OtpRequest(APIModel):
    phone_number: str = Field(
        ...,
        description="Mobile phone number in Indian format (+91XXXXXXXXXX or 10 digits).",
    )


class OtpRequestResponse(APIModel):
    success: bool = True
    message: str
    expires_in: int
    cooldown_seconds: int
    delivery_mode: str
    masked_phone: str


class OtpVerifyRequest(APIModel):
    phone_number: str = Field(..., description="Mobile phone number that received the OTP.")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit numeric OTP code.")


class AuthUserResponse(APIModel):
    id: str
    name: str
    role: str
    phone_number: str | None = None
    phone_verified: bool = False
    hospital_id: str | None = None
    hospital_name: str | None = None
    specialty: str | None = None
    specialties: list[str] = []
    qualification: str | None = None


class LoginResponse(APIModel):
    success: bool = True
    user: AuthUserResponse
    token: str | None = None


class LogoutResponse(APIModel):
    success: bool = True
    message: str


class DemoLoginRequest(APIModel):
    role: str = Field(default="patient", description="Role to log in as ('patient', 'doctor', or 'triage').")
    hospital_id: str | None = Field(default=None, description="Optional active hospital ID for doctors.")
    specialty: str | None = Field(default=None, description="Optional clinical specialisation for doctors.")


class StaffLoginRequest(APIModel):
    identifier: str = Field(
        ...,
        description="Mobile phone number (+91XXXXXXXXXX or 10 digits) or staff email/ID.",
    )
    password: str = Field(..., min_length=1, description="Staff account password.")
    hospital_id: str | None = Field(default=None, description="Optional active hospital ID for doctors.")
    specialty: str | None = Field(default=None, description="Optional active specialisation for doctors.")


class StaffRegisterRequest(APIModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name of staff member.")
    role: str = Field(..., description="Role ('doctor' or 'triage').")
    phone_number: str = Field(..., description="Mobile phone number in Indian format (+91XXXXXXXXXX or 10 digits).")
    email: str | None = Field(default=None, description="Optional official staff email.")
    password: str = Field(..., min_length=6, description="Staff account password (minimum 6 characters).")
    hospital_id: str | None = Field(default=None, description="Optional active hospital ID for doctors.")
    specialty: str | None = Field(default=None, description="Optional active clinical specialisation for doctors.")
    qualification: str | None = Field(default=None, description="Optional qualification/designation for doctors (e.g. MD, MBBS).")

