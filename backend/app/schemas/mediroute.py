from .common import APIModel, UTCDate


class FacilityRecommendation(APIModel):
    facility_id: str
    facility_name: str
    rank: int
    distance_km: float | None
    eligibility_reasons: list[str]
    ranking_reasons: list[str]
    capabilities: list[str]
    emergency_available: bool


class MediRouteResponse(APIModel):
    id: str
    session_id: str
    clinical_routing_result_id: str
    status: str
    routing_state: str
    suggested_specialty: str
    directory_version: str
    protocol_version: str
    required_specialty: str
    required_capabilities: list[str]
    preferred_capabilities: list[str]
    generated_at: UTCDate
    recommendations: list[FacilityRecommendation]


class FacilitySelection(APIModel):
    facility_id: str
