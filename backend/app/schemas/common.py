from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer

Language = Literal["en", "bn", "hi"]
SessionStatus = Literal["intake", "ready_for_review", "under_review", "confirmed", "cancelled"]
FieldName = Literal["chief_complaint", "onset_duration", "medications", "allergies", "past_history"]
UTCDate = Annotated[
    datetime,
    PlainSerializer(
        lambda value: (
            value.replace(tzinfo=timezone.utc).isoformat()
            if value.tzinfo is None
            else value.astimezone(timezone.utc).isoformat()
        ),
        return_type=str,
        when_used="json",
    ),
]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)
