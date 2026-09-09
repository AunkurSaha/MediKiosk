from typing import Any, Literal

from pydantic import Field

from .common import APIModel, UTCDate

AlertPriority = Literal["emergency", "urgent", "priority"]
AlertStatus = Literal["new", "acknowledged", "resolved"]


class TriggeringFact(APIModel):
    question_id: str
    field: str
    value: Any
    raw_value: str | None = None
    label: Any | None = None


class AlertSummary(APIModel):
    id: str
    rule_id: str
    priority: AlertPriority
    category: str
    reason: str
    created_at: UTCDate


class AlertItem(APIModel):
    id: str
    session_id: str
    rule_id: str
    rule_version: str
    priority: AlertPriority
    category: str
    reason: str
    triggering_facts: list[TriggeringFact]
    status: AlertStatus
    acknowledged_at: UTCDate | None = None
    acknowledged_by: str | None = None
    acknowledgement_note: str | None = None
    created_at: UTCDate
    updated_at: UTCDate | None = None
    hospital_token: str | None = None
    patient_name: str | None = None


class AlertList(APIModel):
    items: list[AlertItem]
    total: int
    emergency_count: int
    urgent_count: int
    acknowledged_count: int


class AlertAcknowledgeRequest(APIModel):
    acknowledged_by: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
