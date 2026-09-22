from typing import Literal

from pydantic import Field, model_validator

from .common import APIModel, UTCDate


class PatientRoutingLocationCreate(APIModel):
    source: Literal["BROWSER_GEOLOCATION", "MANUAL_LOCALITY", "MANUAL_POSTAL_CODE", "DEMO"]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    locality: str | None = Field(default=None, min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, pattern=r"^[0-9A-Za-z -]{3,20}$")
    precision: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def source_shape(self):
        if self.source == "BROWSER_GEOLOCATION" and (
            self.latitude is None or self.longitude is None
        ):
            raise ValueError("browser location requires coordinates")
        if self.source == "MANUAL_LOCALITY" and not self.locality:
            raise ValueError("manual locality is required")
        if self.source == "MANUAL_POSTAL_CODE" and not self.postal_code:
            raise ValueError("postal code is required")
        return self


class PatientRoutingLocationResponse(APIModel):
    id: str
    session_id: str
    patient_id: str
    source: str
    latitude: float | None
    longitude: float | None
    locality: str | None
    postal_code: str | None
    precision: str | None
    revision: int
    captured_at: UTCDate
