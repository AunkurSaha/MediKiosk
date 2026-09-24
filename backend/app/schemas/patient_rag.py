from datetime import datetime

from pydantic import ConfigDict, Field, model_validator

from .common import APIModel


class PatientRAGSearchRequest(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=8, ge=1, le=20)
    source_types: list[str] = Field(default_factory=list, max_length=12)
    verification_statuses: list[str] = Field(default_factory=list, max_length=12)
    document_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class PatientRAGEvidence(APIModel):
    chunk_id: str
    text: str
    source_type: str
    source_record_id: str
    session_id: str | None = None
    document_id: str | None = None
    source_filename: str | None = None
    page_number: int | None = None
    verification_status: str
    timestamp: datetime | None = None
    similarity: float = Field(ge=-1, le=1)
    score: float = Field(ge=0, le=2)
    clinician_verified: bool
    is_current: bool
    is_conflicted: bool
    provenance: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class PatientRAGSearchResponse(APIModel):
    answer: str
    evidence: list[PatientRAGEvidence]
    patient_id: str
    query: str
    intent: str
    retrieval_strategy: str = "patient_scoped_hybrid"
    embedding_provider: str
    embedding_model: str
    index_latency_ms: float
    embedding_latency_ms: float
    retrieval_latency_ms: float
    generation_latency_ms: float = 0
    total_latency_ms: float
    retrieval_mode: str = "deterministic_patient_scoped"
    fallback_used: bool = False
    results: list[dict] = Field(default_factory=list)
    disclaimer: str = "Retrieved patient evidence only. No diagnosis or treatment recommendation."


class PatientRAGIndexStatus(APIModel):
    patient_id: str
    session_id: str | None = None
    canonical_records: int
    chunks_total: int
    chunks_embedded: int
    chunks_failed: int
    embedding_provider: str | None = None
    embedding_model: str | None = None
    last_indexed_at: datetime | None = None
    failures: list[str] = Field(default_factory=list)
