"""Verification script for RAG activation & visual indicator contract in chest-pain interview."""

import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["APP_ENV"] = "test"
os.environ["DEMO_MODE"] = "true"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CLINICAL_NORMALIZATION_PROVIDER"] = "mock"
os.environ["RAG_EMBEDDING_PROVIDER"] = "mock"
os.environ["RAG_GENERATION_PROVIDER"] = "template"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.services import rag_integration
from tests.test_workflow import consent, create

test_engine = create_engine(
    "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
)
Base.metadata.create_all(bind=test_engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

def mock_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
    return [
        {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
            "reason": "Shortness of breath is an important associated symptom in chest pain.",
            "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
            "source_title": "Associated Symptoms in Chest Pain",
            "origin": "rag",
            "target_field": "hpi.associated_details",
            "concept": "DYSPNEA",
            "similarity_score": 0.85,
        },
        {
            "candidate_id": "sweating",
            "question": "Have you experienced heavy sweating or cold sweats along with the chest pain?",
            "reason": "Sweating is an important autonomic sign in acute chest pain assessment.",
            "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
            "source_title": "Associated Symptoms in Chest Pain",
            "origin": "rag",
            "target_field": "hpi.associated_details",
            "concept": "SWEATING",
            "similarity_score": 0.82,
        },
    ]

rag_integration.get_rag_suggestions = mock_suggestions

client = TestClient(app)
session_id, _ = create(client, "en")
consent(client, session_id)
resp = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": "chest_pain"})
assert resp.status_code == 200
state = resp.json()

qa_map = {
    "chief_complaint.description": ("Chest discomfort for two hours", "answered"),
    "hpi.onset": ({"amount": 2, "unit": "hours"}, "answered"),
    "hpi.site": ("substernal", "answered"),
    "hpi.character": ("pressure", "answered"),
    "hpi.radiation": (False, "answered"),
    "hpi.associated_details": ("mild nausea", "answered"),
    "hpi.timing": ("constant", "answered"),
    "hpi.exacerbating": ("walking", "answered"),
    "hpi.relieving": ("rest", "answered"),
    "hpi.severity": (6, "answered"),
    "past_medical_history.diabetes": (False, "answered"),
    "past_medical_history.other": (False, "answered"),
    "past_surgical_history.any": (False, "answered"),
    "medications.any": (False, "answered"),
    "allergies.any": (False, "answered"),
    "family_history.any": (False, "answered"),
    "personal_history.tobacco": ("never", "answered"),
    "personal_history.alcohol": (False, "answered"),
    "personal_history.context": (None, "skipped"),
    "review_of_systems.other": (False, "answered"),
}

print("=" * 60)
print("VERIFYING CHEST PAIN INTERVIEW RAG ACTIVATION")
print("=" * 60)

deterministic_count = 0
while state.get("question") and not state["question"]["question_id"].startswith("rag_followup"):
    q = state["question"]
    qid = q["question_id"]
    origin = q.get("origin")
    rag_sugs = state.get("rag_suggestions") or []
    
    assert origin != "rag", f"Normal question {qid} had origin='rag'"
    assert len(rag_sugs) == 0, f"Normal question {qid} had rag_suggestions: {rag_sugs}"
    
    val, stat = qa_map.get(
        qid,
        (False, "answered") if q["type"] == "boolean" else (None, "skipped"),
    )
    raw = str(val) if val is not None else ("Skipped" if stat == "skipped" else "Unknown")
    res = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "request_id": str(uuid4()),
            "expected_revision": state["revision"],
            "question_id": qid,
            "status": stat,
            "value": val,
            "raw_value": raw,
            "source": "typed",
            "language": "en",
        },
    )
    assert res.status_code == 200, res.text
    state = res.json()
    deterministic_count += 1

print(f"Verified {deterministic_count} deterministic questions: NONE had origin='rag' or rag_suggestions.")

# 1st RAG Question
q1 = state["question"]
assert q1 is not None, "Expected RAG question 1"
print("\n[RAG Question 1]")
print(f"  question_id: {q1['question_id']}")
print(f"  origin: {q1.get('origin')}")
print(f"  text: {q1['text']['en']}")
assert q1["question_id"] == "rag_followup.dyspnea"
assert q1.get("origin") == "rag"
assert len(state["rag_suggestions"]) == 1
sug1 = state["rag_suggestions"][0]
print(f"  candidate_id: {sug1['candidate_id']}")
print(f"  source_chunk_ids: {sug1['source_chunk_ids']}")
print(f"  similarity_score: {sug1['similarity_score']}")
print(f"  source_title: {sug1['source_title']}")
print(f"  generation_provider: {sug1['generation_provider']}")
assert sug1["candidate_id"] == "dyspnea"
assert sug1["source_chunk_ids"] == ["chest_pain-associated_symptoms-001"]
assert sug1["similarity_score"] == 0.85

# Answer 1st RAG Question
ans1 = client.post(
    f"/api/sessions/{session_id}/interview/answers",
    json={
        "request_id": str(uuid4()),
        "expected_revision": state["revision"],
        "question_id": q1["question_id"],
        "status": "answered",
        "value": "I feel slight breathlessness when walking",
        "raw_value": "I feel slight breathlessness when walking",
        "source": "typed",
        "language": "en",
    },
)
assert ans1.status_code == 200
state = ans1.json()

# 2nd RAG Question
q2 = state["question"]
assert q2 is not None, "Expected RAG question 2"
print("\n[RAG Question 2]")
print(f"  question_id: {q2['question_id']}")
print(f"  origin: {q2.get('origin')}")
print(f"  text: {q2['text']['en']}")
assert q2["question_id"] == "rag_followup.sweating"
assert q2.get("origin") == "rag"
assert len(state["rag_suggestions"]) == 1
sug2 = state["rag_suggestions"][0]
print(f"  candidate_id: {sug2['candidate_id']}")
print(f"  source_chunk_ids: {sug2['source_chunk_ids']}")
print(f"  similarity_score: {sug2['similarity_score']}")
print(f"  source_title: {sug2['source_title']}")
print(f"  generation_provider: {sug2['generation_provider']}")
assert sug2["candidate_id"] == "sweating"
assert sug2["source_chunk_ids"] == ["chest_pain-associated_symptoms-001"]

# Answer 2nd RAG Question
ans2 = client.post(
    f"/api/sessions/{session_id}/interview/answers",
    json={
        "request_id": str(uuid4()),
        "expected_revision": state["revision"],
        "question_id": q2["question_id"],
        "status": "answered",
        "value": "No unusual sweating",
        "raw_value": "No unusual sweating",
        "source": "typed",
        "language": "en",
    },
)
assert ans2.status_code == 200
state = ans2.json()

# Completed (budget 2 reached)
print("\n[Interview Complete]")
print(f"  is_complete: {state['is_complete']}")
print(f"  question: {state['question']}")
assert state["is_complete"] is True
assert state["question"] is None

print("\n" + "=" * 60)
print("ALL ACTIVATION CHECKS VERIFIED SUCCESSFULLY")
print("=" * 60)
