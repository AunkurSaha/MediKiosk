import uuid

from sqlalchemy import Boolean, Column, DateTime, String, text

from app.database import Base


class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(40), nullable=False, unique=True, index=True)
    name = Column(String(160), nullable=False)
    address = Column(String(240), nullable=True)
    city = Column(String(100), nullable=True)
    active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    # Fields added for facility directory (Unit 1)
    is_demo = Column(Boolean, nullable=False, default=False, server_default="0")
    latitude = Column(String, nullable=True)  # Storing as string to be consistent with address/city, or could use Float
    longitude = Column(String, nullable=True)
    capabilities = Column(String, nullable=True)  # Comma-separated list of capabilities
    directory_version = Column(String, nullable=True)
