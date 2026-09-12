"""Acceptance tests for RAG-driven, deterministic-coverage interview planning."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.rag import KnowledgeRetrievalService
from tests.test_workflow import consent, create


def _select(client, language="en"):
    session_id, _ = create(client, language)
    consent(client, session_id)
    response = client.put(
        f"/api/sessions/{session_id}/interview/flow", json={"flow_id": "chest_pain"}
    )
    assert response.status_code == 200, response.text
    return session_id, response.json()


def _submit(client, session_id, state, value, raw=None):
    response = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "request_id": str(uuid4()),
            "expected_revision": state["revision"],
            "question_id": state["question"]["question_id"],
            "status": "answered",
            "value": value,
            "raw_value": raw if raw is not None else str(value),
            "source": "typed",
            "language": "en",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _grounded_retrieval(monkeypatch):
    calls = []

    async def retrieve(self, **kwargs):
        calls.append(kwargs)
        chunk = SimpleNamespace(
            id="chest_pain-history_taking-001",
            source_title="History Taking",
            section="history_taking",
            content=(
                "Assess chest-pain onset, site, character, radiation, associated symptoms, "
                "timing, aggravating and relieving factors, and severity."
            ),
        )
        return [(chunk, 0.91)]

    monkeypatch.setattr(KnowledgeRetrievalService, "retrieve", retrieve)
    return calls


def test_rag_drives_consecutive_approved_coverage_questions(client, monkeypatch):
    calls = _grounded_retrieval(monkeypatch)
    monkeypatch.setenv("RAG_GENERATION_PROVIDER", "template")
    session_id, state = _select(client)

    assert state["question"]["question_id"] == "chief_complaint.description"
    assert state["question"].get("origin") is None

    state = _submit(client, session_id, state, "central chest pain")
    expected = [
        ("hpi.onset", "onset", {"amount": 2, "unit": "hours"}, "2 hours"),
        ("hpi.site", "site", "centre of chest", None),
        ("hpi.character", "character", "pressure-like", None),
        ("hpi.radiation", "radiation", False, "false"),
    ]
    for question_id, domain, value, raw in expected:
        assert state["question"]["question_id"] == question_id
        assert state["question"]["origin"] == "rag"
        assert state["rag_suggestions"][0]["target_field"] == question_id
        assert state["rag_suggestions"][0]["target_domain"] == domain
        assert state["rag_suggestions"][0]["source_chunk_ids"]
        assert question_id not in state["covered_domains"]
        state = _submit(client, session_id, state, value, raw)

    assert all(call["top_k"] == 3 for call in calls)
    assert "hpi.onset" in {answer["field"] for answer in state["active_answers"]}
    assert "hpi.radiation" in {answer["field"] for answer in state["active_answers"]}


def test_rag_failure_uses_same_deterministic_field_without_stopping(client, monkeypatch):
    async def unavailable(self, **kwargs):
        raise RuntimeError("synthetic retrieval outage")

    monkeypatch.setattr(KnowledgeRetrievalService, "retrieve", unavailable)
    session_id, state = _select(client)
    state = _submit(client, session_id, state, "chest pain")

    assert state["question"]["question_id"] == "hpi.onset"
    assert state["question"].get("origin") is None
    assert state["question"]["text"]["en"] == "How long ago did this problem start?"
    assert state["rag_suggestions"] == []
    assert state["is_complete"] is False


def test_answered_field_is_removed_from_missing_domain_candidates(client, monkeypatch):
    _grounded_retrieval(monkeypatch)
    monkeypatch.setenv("RAG_GENERATION_PROVIDER", "template")
    session_id, state = _select(client)
    state = _submit(client, session_id, state, "chest pain")
    state = _submit(
        client, session_id, state, {"amount": 1, "unit": "days"}, "one day"
    )

    assert state["question"]["question_id"] == "hpi.site"
    assert state["rag_suggestions"][0]["target_field"] == "hpi.site"
    assert "onset" in state["covered_domains"]
    assert "onset" not in state["missing_required_domains"]
