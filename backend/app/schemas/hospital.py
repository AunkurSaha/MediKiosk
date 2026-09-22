from uuid import UUID

from pydantic import Field

from .common import APIModel


class HospitalBase(APIModel):
    id: UUID
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    address: str | None = Field(max_length=240)
    city: str | None = Field(max_length=100)
    latitude: float | None = None
    longitude: float | None = None
    facility_type: str | None = Field(max_length=80)
    capabilities_json: list[str] = Field(default_factory=list)
    emergency_available: bool = False
    opening_status: str = Field(max_length=20)  # OPEN, CLOSED, UNKNOWN
    is_demo: bool = False
    directory_version: str | None = Field(max_length=80)
    active: bool = True


class HospitalCreate(HospitalBase):
    pass


class HospitalUpdate(APIModel):
    code: str | None = Field(min_length=1, max_length=40)
    name: str | None = Field(min_length=1, max_length=160)
    address: str | None = Field(max_length=240)
    city: str | None = Field(max_length=100)
    latitude: float | None = None
    longitude: float | None = None
    facility_type: str | None = Field(max_length=80)
    capabilities_json: list[str] | None = None
    emergency_available: bool | None = None
    opening_status: str | None = Field(max_length=20)
    is_demo: bool | None = None
    directory_version: str | None = Field(max_length=80)
    active: bool | None = None


class HospitalResponse(HospitalBase):
    pass
