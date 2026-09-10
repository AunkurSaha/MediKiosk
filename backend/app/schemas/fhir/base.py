from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FHIRBaseModel(BaseModel):
    """Base class for all FHIR R4 data models."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


class Coding(FHIRBaseModel):
    system: str | None = None
    version: str | None = None
    code: str | None = None
    display: str | None = None
    user_selected: bool | None = Field(default=None, alias="userSelected")


class CodeableConcept(FHIRBaseModel):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Identifier(FHIRBaseModel):
    use: str | None = None
    type: CodeableConcept | None = None
    system: str | None = None
    value: str | None = None


class Reference(FHIRBaseModel):
    reference: str | None = None
    type: str | None = None
    identifier: Identifier | None = None
    display: str | None = None


class Period(FHIRBaseModel):
    start: datetime | str | None = None
    end: datetime | str | None = None


class Quantity(FHIRBaseModel):
    value: float | int | None = None
    comparator: str | None = None
    unit: str | None = None
    system: str | None = None
    code: str | None = None


class Narrative(FHIRBaseModel):
    status: str = "generated"
    div: str


class Meta(FHIRBaseModel):
    version_id: str | None = Field(default=None, alias="versionId")
    last_updated: datetime | str | None = Field(default=None, alias="lastUpdated")
    profile: list[str] = Field(default_factory=list)
    security: list[Coding] = Field(default_factory=list)
    tag: list[Coding] = Field(default_factory=list)


class HumanName(FHIRBaseModel):
    use: str = "usual"
    text: str | None = None
    family: str | None = None
    given: list[str] = Field(default_factory=list)


class Attachment(FHIRBaseModel):
    content_type: str | None = Field(default=None, alias="contentType")
    language: str | None = None
    data: str | None = None
    url: str | None = None
    size: int | None = None
    hash: str | None = None
    title: str | None = None
    creation: datetime | str | None = None
