import sys
sys.path.insert(0, 'C:/MEDIKIOSK/backend')
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app import models
import uuid

# Override dependency to use a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

# Create a session
payload = {
    "id": str(uuid.uuid4()),
    "patient": {"name": "Synthetic Patient", "demo_abha_id": None},
    "hospital_token": "DEMO-104",
    "language": "en",
}
response = client.post("/api/sessions", json=payload)
print("Create session:", response.status_code, response.json())
if response.status_code != 201:
    print("Failed to create session")
    sys.exit(1)
session_id = response.json()["id"]
print("Session ID:", session_id)

# Consent
consent_payload = {"share_with_doctor": True, "voice_processing": False, "document_processing": False}
response = client.put(f"/api/sessions/{session_id}/consent", json=consent_payload)
print("Consent:", response.status_code, response.json())
if response.status_code != 200:
    print("Failed to set consent")
    sys.exit(1)

# Now call completion endpoint (should fail because no answers)
response = client.post(f"/api/sessions/{session_id}/complete")
print("Complete response:", response.status_code, response.text)
print("Response JSON:", response.json())