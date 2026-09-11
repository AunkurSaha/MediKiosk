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


class LoginResponse(APIModel):
    success: bool = True
    user: AuthUserResponse
    token: str | None = None


class LogoutResponse(APIModel):
    success: bool = True
    message: str


class DemoLoginRequest(APIModel):
    role: str = Field(default="patient", description="Role to log in as ('patient' or 'doctor').")
