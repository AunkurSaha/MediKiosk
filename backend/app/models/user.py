import uuid

from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint, text

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="users_email_key"),
        UniqueConstraint("phone_number", name="users_phone_number_key"),
    )

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, default="Patient")
    email = Column(String, unique=True, index=True, nullable=True)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    phone_verified = Column(Boolean, default=False, nullable=False)
    phone_verified_at = Column(DateTime(timezone=True), nullable=True)
    role = Column(String, nullable=False)  # doctor / triage / admin / patient
    is_active = Column(Boolean, default=True)
    hashed_password = Column(String, nullable=True)  # for future auth
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(DateTime(timezone=True), onupdate=text("CURRENT_TIMESTAMP"))
