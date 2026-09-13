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
