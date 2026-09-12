"""Verify POST /api/rag/retrieve endpoint with live NVIDIA configuration.

No secrets, tokens, or credentials are printed or logged.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.database import SessionLocal
from app.main import app

# Load backend/.env
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)



def test_rag_endpoint():
    print("====================================================================")
    print("TESTING POST /api/rag/retrieve ENDPOINT WITH REAL NVIDIA PROVIDER")
    print("====================================================================")

    # Ensure demo doctor exists in DB for auth
    with SessionLocal() as db:
        doctor = db.query(models.User).filter(models.User.id == DEMO_DOCTOR_ID).first()
        if not doctor:
            doctor = models.User(
                id=DEMO_DOCTOR_ID,
                username="doctor_demo",
                full_name="Dr. Demo Specialist",
                role="specialist",
                is_active=True,
            )
            db.add(doctor)
            db.commit()

    client = TestClient(app)
    headers = {"X-Demo-Doctor": "true"}

    payload = {
        "query": "Patient experiencing crushing chest pain radiating to the jaw and left arm",
        "topic": "chest_pain",
        "language": "en",
        "top_k": 3,
        # min_similarity omitted to test that calibrated default (0.25) is used automatically
    }

    response = client.post("/api/rag/retrieve", headers=headers, json=payload)
    print(f"HTTP Status Code: {response.status_code}")
    assert response.status_code == 200, response.text
    data = response.json()
    results = data["results"]
    print(f"Total Chunks Returned: {len(results)}")
    assert len(results) > 0, "Expected non-empty chunks for realistic chest-pain query"

    for i, item in enumerate(results, 1):
        print(f"  #{i}: [score={item['similarity_score']:.4f}] chunk_id={item['chunk_id']} section={item['section']}")
        print(f"      content snippet: \"{item['content'][:80].replace(chr(10), ' ')}...\"")

    print("\n[ENDPOINT VERIFICATION SUCCESSFUL]")


if __name__ == "__main__":
    test_rag_endpoint()
