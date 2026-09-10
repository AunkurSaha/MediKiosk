from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.fhir.base import FHIRBaseModel, Identifier, Meta
from app.schemas.fhir.resources import OperationOutcome


class BundleEntry(FHIRBaseModel):
    full_url: str = Field(alias="fullUrl")
    resource: dict[str, Any]


class BundleResource(FHIRBaseModel):
    resource_type: str = Field(default="Bundle", alias="resourceType")
    id: str
    meta: Meta | None = None
    identifier: Identifier | None = None
    type: str = "document"  # document | collection
    timestamp: datetime | str
    total: int | None = None
    entry: list[BundleEntry] = Field(default_factory=list)


class FHIRExportResponse(FHIRBaseModel):
    session_id: str
    export_timestamp: str
    bundle_type: str
    compliance_profile: str
    resource_counts: dict[str, int]
    validation: OperationOutcome
    bundle: dict[str, Any]
