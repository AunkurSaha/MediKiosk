import uuid

from sqlalchemy import Column, DateTime, Integer, String, text

from app.database import Base


class OTPChallenge(Base):
    __tablename__ = "otp_challenges"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(32), index=True, nullable=False)
    purpose = Column(String(32), nullable=False, default="login")
    otp_salt = Column(String(64), nullable=False)
    otp_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)
