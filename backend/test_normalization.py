import os
from uuid import uuid4

from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.database import Base, get_db
from app.main import app

# Read the backend/.env to get the password for the test database
env_path = "/c/MEDIKIOSK/backend/.env"
env = dotenv_values(env_path) if os.path.exists(env_path) else {}
# The DATABASE_URL is in the format: postgresql+psycopg://medikiosk:<password>@127.0.0.1:55432/medikiosk
# We want to change the database to medikiosk_test for testing
db_url = env.get("DATABASE_URL", "")
if db_url:
    # Replace the database name with the test database
    SQLALCHEMY_DATABASE_URL = db_url.replace("/medikiosk", "/medikiosk_test")
else:
    # Fallback to SQLite if no DATABASE_URL is found (should not happen in development)
    SQLALCHEMY_DATABASE_URL = "sqlite:///./test_normalization.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Seed the demo doctor in the test database
with TestingSessionLocal() as db:
    if db.get(models.User, DEMO_DOCTOR_ID) is None:
        db.add(
            models.User(
                id=DEMO_DOCTOR_ID,
                name="Demo Doctor",
                email="demo@medikiosk.invalid",
                role="doctor",
                is_active=True,
            )
        )
        db.commit()

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_normalization_persistence():
    # Create session
    payload = {
        "id": str(uuid4()),
        "patient": {"name": "Test Patient", "demo_abha_id": None},
        "hospital_token": "DEMO-104",
        "language": "en",
    }
    response = client.post("/api/sessions", json=payload)
    assert response.status_code == 201, response.text
    session_id = response.json()["id"]
    print(f"Created session: {session_id}")

    # Consent
    response = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": False,
            "document_processing": False,
            "share_with_doctor": True,
        },
    )
    assert response.status_code == 200, response.text
    print("Consent given")

    # Answer chief_complaint with "chest pain" (should normalize)
    response = client.post(
        f"/api/sessions/{session_id}/answers",
        json={
            "question_id": "chief_complaint",
            "field": "chief_complaint",
            "value": "chest pain",
            "raw_value": "chest pain",
            "source": "typed",
            "language": "en",
        },
    )
    assert response.status_code == 200, response.text
    print("Answered chief_complaint: chest pain")

    # Answer a few other questions to complete the intake
    from app.services.intake import FIELDS
    for field in FIELDS[1:]:  # skip chief_complaint since we already answered
        response = client.post(
            f"/api/sessions/{session_id}/answers",
            json={
                "question_id": field,
                "field": field,
                "value": f"Reported {field}",
                "raw_value": f"Reported {field}",
                "source": "typed",
                "language": "en",
            },
        )
        assert response.status_code == 200, response.text
        print(f"Answered {field}")

    # Complete the intake
    response = client.post(f"/api/sessions/{session_id}/complete")
    assert response.status_code == 200, response.text
    print("Intake completed")

    # Fetch the session from the doctor endpoint
    response = client.get(f"/api/doctor/sessions/{session_id}", headers={"X-Demo-Doctor": "true"})
    assert response.status_code == 200, response.text
    data = response.json()
    print(f"Session status: {data['session']['status']}")
    assert data["session"]["status"] == "ready_for_review"

    # Check that we have answers
    assert len(data["answers"]) == len(FIELDS)
    print(f"Got {len(data['answers'])} answers")

    # Check the chief_complaint answer for normalization
    chief_answer = next((a for a in data["answers"] if a["field"] == "chief_complaint"), None)
    assert chief_answer is not None, "Chief complaint answer not found"
    print(f"Chief complaint raw_value: {chief_answer['raw_value']}")
    print(f"Chief complaint value: {chief_answer['value']}")

    # Check if normalization is present in the history (since doctor endpoint shows history)
    # The doctor endpoint returns a history object that includes normalization per fact
    assert "history" in data, "History not found in doctor response"
    history = data["history"]
    assert history is not None, "History is None"
    assert "sections" in history, "Sections not found in history"

    # Find the chief complaint fact in the history
    chief_fact = None
    for section in history["sections"]:
        for fact in section["facts"]:
            if fact["field"] == "chief_complaint":
                chief_fact = fact
                break
        if chief_fact:
            break

    assert chief_fact is not None, "Chief complaint fact not found in history"
    # Print only ASCII-safe fields to avoid encoding issues
    print(f"Chief complaint fact field: {chief_fact.get('field', 'N/A')}")
    print(f"Chief complaint fact value: {chief_fact.get('value', 'N/A')}")

    # Check that normalization is present
    assert "normalization" in chief_fact, "Normalization not found in chief complaint fact"
    normalization = chief_fact["normalization"]
    assert normalization is not None, "Normalization is None"
    # Print only ASCII-safe fields
    print(f"Normalization status: {normalization.get('status', 'N/A')}")
    print(f"Normalization facts count: {len(normalization.get('facts', []))}")

    # Check that the normalization has a fact with the expected concept
    assert "facts" in normalization, "No facts in normalization"
    assert len(normalization["facts"]) > 0, "No normalization facts"
    norm_fact = normalization["facts"][0]
    assert norm_fact["normalized_concept"] == "CHEST_PAIN", f"Expected CHEST_PAIN, got {norm_fact['normalized_concept']}"
    print(f"Normalized concept: {norm_fact['normalized_concept']}")
    print(f"Normalized display: {norm_fact.get('normalized_display', 'N/A')}")

    # Check that the original text is preserved
    assert normalization["original_text"] == "chest pain", f"Original text mismatch: {normalization['original_text']}"
    print(f"Original text preserved: {normalization['original_text']}")

    print("All tests passed!")

if __name__ == "__main__":
    test_normalization_persistence()