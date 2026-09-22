import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, String, text

from app.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(40), nullable=False, unique=True, index=True)
    name = Column(String(160), nullable=False)
    address = Column(String(240), nullable=True)
    city = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    facility_type = Column(String(80), nullable=True)
    locality = Column(String(120), nullable=True)
    capabilities_json = Column(JSON, nullable=False, default=list)
    emergency_available = Column(Boolean, nullable=False, default=False)
    opening_status = Column(String(20), nullable=False, default="OPEN")  # OPEN, CLOSED, UNKNOWN
    is_demo = Column(Boolean, nullable=False, default=False)
    directory_version = Column(String(80), nullable=True)  # e.g., "demo_facilities_v1"
    active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
