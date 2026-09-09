from pydantic import Field

from .common import APIModel, UTCDate


class PatientCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    demo_abha_id: str | None = Field(default=None, max_length=80)


class Patient(PatientCreate):
    id: str
    created_at: UTCDate
    updated_at: UTCDate | None = None
