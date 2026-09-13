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


def _valid_answer(question):
    kind = question["type"]
    if kind == "duration":
        return {"amount": 2, "unit": "hours"}, "2 hours"
    if kind in ("number", "severity"):
        return 4, "4"
    if kind == "boolean":
        return False, "false"
    if kind == "single_choice":
        value = question["options"][0]["value"]
        return value, value
    if kind == "multiple_choice":
        value = [question["options"][0]["value"]]
        return value, value[0]
    return "patient response", "patient response"


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
    seen = set()
    for _ in range(3):
        question_id = state["question"]["question_id"]
        assert question_id not in seen
        seen.add(question_id)
        assert state["question"]["origin"] == "rag"
        assert state["rag_suggestions"][0]["target_field"] == question_id
        assert state["rag_suggestions"][0]["source_chunk_ids"]
        value, raw = _valid_answer(state["question"])
        state = _submit(client, session_id, state, value, raw)

    assert all(call["top_k"] == 3 for call in calls)
    assert len({answer["field"] for answer in state["active_answers"]}) >= 4


def test_remote_rag_failure_uses_local_grounded_fallback(client, monkeypatch):
    async def unavailable(self, **kwargs):
        raise RuntimeError("synthetic retrieval outage")

    monkeypatch.setattr(KnowledgeRetrievalService, "retrieve", unavailable)
    session_id, state = _select(client)
    state = _submit(client, session_id, state, "chest pain")

    assert state["question"].get("origin") == "rag"
    assert state["rag_suggestions"]
    assert state["rag_suggestions"][0]["source_chunk_ids"][0].startswith("local-")
    assert state["is_complete"] is False


def test_answered_field_is_removed_from_missing_domain_candidates(client, monkeypatch):
    _grounded_retrieval(monkeypatch)
    monkeypatch.setenv("RAG_GENERATION_PROVIDER", "template")
    session_id, state = _select(client)
    state = _submit(client, session_id, state, "chest pain")
    answered_field = state["question"]["field"]
    value, raw = _valid_answer(state["question"])
    state = _submit(client, session_id, state, value, raw)

    assert state["rag_suggestions"][0]["target_field"] != answered_field
    assert answered_field in {answer["field"] for answer in state["active_answers"]}


def test_live_api_uses_answer_context_to_change_the_next_question(client, monkeypatch):
    _grounded_retrieval(monkeypatch)
    monkeypatch.setenv("RAG_GENERATION_PROVIDER", "template")
    session_id, state = _select(client)

    state = _submit(
        client,
        session_id,
        state,
        "It started suddenly 30 minutes ago while walking and spreads to my left arm.",
    )

    assert state["question"]["origin"] == "rag"
    assert state["question"]["question_id"] != "hpi.onset"
    assert state["rag_suggestions"][0]["target_field"] == state["question"]["field"]
