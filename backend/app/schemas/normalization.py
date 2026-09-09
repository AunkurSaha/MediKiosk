"""Provider output is untrusted; provenance is attached exclusively by the service."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import APIModel, Language, UTCDate

Concept = Literal[
    "CHEST_PAIN",
    "ABDOMINAL_PAIN",
    "HEADACHE",
    "FEVER",
    "COUGH",
    "DYSPNEA",
    "NAUSEA",
    "VOMITING",
    "SWEATING",
    "DIZZINESS",
    "PRESSURE_LIKE_PAIN",
    "SHARP_PAIN",
    "BURNING_PAIN",
]
Certainty = Literal["certain", "uncertain", "unknown"]
Polarity = Literal["present", "absent"]
ResultStatus = Literal["normalized", "unrecognized", "unknown", "unavailable"]
Reason = Literal[
    "no_match",
    "explicit_unknown",
    "timeout",
    "invalid_result",
    "provider_unavailable",
    "unsupported_language",
    "disabled",
    "not_processed",
    "not_applicable",
    "missing_api_key",
    "authentication_failed",
    "rate_limited",
    "network_error",
    "server_error",
    "truncated_response",
]


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=4000)
    language: str
    canonical_field: str
    context: dict[str, str]


class ProviderFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    concept: Concept
    evidence: str = Field(min_length=1, max_length=4000)
    certainty: Certainty
    polarity: Polarity = "present"
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0", "1.1"]
    canonical_field: str
    language: Language
    status: Literal["normalized", "unrecognized", "unknown"]
    facts: list[ProviderFact] = Field(max_length=5)

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "normalized") != bool(self.facts):
            raise ValueError("normalized results require facts; other statuses forbid facts")
        if len({f.concept for f in self.facts}) != len(self.facts):
            raise ValueError("duplicate concept")
        if any(f.certainty == "unknown" for f in self.facts):
            raise ValueError("unknown certainty must not assert a concept")
        if self.schema_version == "1.1" and any(
            "polarity" not in f.model_fields_set for f in self.facts
        ):
            raise ValueError("schema 1.1 requires explicit polarity")
        if self.schema_version == "1.0" and any(f.polarity != "present" for f in self.facts):
            raise ValueError("negation requires schema 1.1")
        return self


class LiveProviderFact(ProviderFact):
    polarity: Polarity
    confidence: None


class LiveProviderResult(ProviderResult):
    """Live extraction must state polarity and must not invent semantic confidence."""

    schema_version: Literal["1.1"]
    facts: list[LiveProviderFact] = Field(max_length=5)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class NormalizedFact(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    normalized_concept: Concept
    normalized_display: str
    normalized_value: bool | str | None
    polarity: Polarity = "present"
    evidence: str
    confidence: float | None = Field(ge=0, le=1, allow_inf_nan=False)
    certainty: Certainty
    verification_status: Literal["machine_normalized", "needs_verification"]


class Normalization(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    id: str | None = None
    source_answer_id: str
    source_question_id: str
    canonical_field: str
    original_language: str
    original_text: str
    status: ResultStatus
    reason: Reason | None = None
    facts: list[NormalizedFact] = Field(default_factory=list)
    provider: str | None = None
    provider_version: str | None = None
    schema_version: Literal["1.0", "1.1"] = "1.0"
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    token_usage: TokenUsage | None = None
    policy_version: Literal["1.0"] = "1.0"
    created_at: UTCDate | None = None


class ComplaintCandidate(APIModel):
    flow_id: str
    source_normalization_id: str
    requires_confirmation: Literal[True] = True
