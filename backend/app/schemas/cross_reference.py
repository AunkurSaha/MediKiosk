from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentFactLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_id: str
    fact_type: str  # "medication" | "lab"
    label: str
    verification_status: str


class DocumentCrossReference(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    filename: str
    document_type: str
    created_at: datetime
    medications: list[DocumentFactLink] = Field(default_factory=list)
    labs: list[DocumentFactLink] = Field(default_factory=list)
    discrepancies: list[str] = Field(default_factory=list)
    summary_statements: list[str] = Field(default_factory=list)


class CrossReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: str
    documents: list[DocumentCrossReference] = Field(default_factory=list)
    statement_cross_references: dict[str, dict[str, Any]] = Field(default_factory=dict)
