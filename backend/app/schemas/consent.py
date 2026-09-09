
from .common import APIModel, UTCDate


class ConsentUpdate(APIModel):
    voice_processing: bool = False
    document_processing: bool = False
    share_with_doctor: bool



class Consent(ConsentUpdate):
    id: str
    session_id: str
    recorded_at: UTCDate
    created_at: UTCDate
    updated_at: UTCDate | None = None
