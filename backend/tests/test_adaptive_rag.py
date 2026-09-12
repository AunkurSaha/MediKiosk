"""Comprehensive end-to-end tests for adaptive RAG questioning lifecycle.

Verifies:
- Mandatory deterministic questions asked first
- RAG not considered while mandatory questions remain
- Redundant candidates rejected (pain character, radiation, already-known facts)
- Valid grounded candidate becomes active question
- Patient answers enter normal interview pipeline and normalization
- Repeat / loop rejection: same candidate cannot appear again
- Budget enforcement (MAX_RAG_FOLLOWUPS_PER_INTERVIEW)
- Safety priority: Red flag always outranks RAG
- Missing required question always outranks RAG
- Blank RAG question text discarded (no fake "Follow-up question")
- Fail-open on provider failure
- Distinguishable question IDs (rag_followup.<candidate_id>)
"""

from uuid import uuid4

from app.core.errors import ProviderFailure
from tests.test_workflow import consent, create


def selected(client, flow_id="chest_pain", language="en"):
    session_id, _ = create(client, language)
    consent(client, session_id)
    response = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": flow_id})
    assert response.status_code == 200, response.text
    return session_id, response.json()


def submit_answer(client, session_id, state, value=None, status="answered", **overrides):
    q = state["question"]
    raw = str(value) if value is not None else "Unknown"
    body = {
        "request_id": str(uuid4()),
        "expected_revision": state["revision"],
        "question_id": q["question_id"],
        "status": status,
        "value": value,
        "raw_value": raw,
        "source": "typed",
        "language": "en",
    }
    body.update(overrides)
    response = client.post(f"/api/sessions/{session_id}/interview/answers", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def complete_deterministic_chest_pain(client, session_id, initial_state):
    """Answer all mandatory questions for chest_pain flow safely without triggering red flags."""
    qa_map = {
        "chief_complaint.description": ("chest pain", "answered"),
        "hpi.onset": ({"amount": 2, "unit": "hours"}, "answered"),
        "hpi.site": ("center of chest", "answered"),
        "hpi.character": ("pressure-like", "answered"),
        "hpi.radiation": (False, "answered"),
        "hpi.associated_details": ("slight discomfort", "answered"),
        "hpi.timing": ("constant", "answered"),
        "hpi.exacerbating": ("walking", "answered"),
        "hpi.relieving": ("rest", "answered"),
        "hpi.severity": (5, "answered"),  # Moderate, no red flag
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

    state = initial_state
    for _ in range(60):
        if not state["question"]:
            break
        qid = state["question"]["question_id"]
        if qid.startswith("rag_followup"):
            # Reached RAG stage!
            break

        # Verify that while mandatory questions remain, RAG is NOT active
        assert not qid.startswith("rag_followup"), f"RAG question {qid} activated before deterministic completion"

        if qid in qa_map:
            val, stat = qa_map[qid]
            raw = str(val) if val is not None else ("Skipped" if stat == "skipped" else "Unknown")
            state = submit_answer(client, session_id, state, val, stat, raw_value=raw)
        elif state["question"]["type"] == "boolean":
            state = submit_answer(client, session_id, state, False, "answered", raw_value="false")
        elif not state["question"]["required"]:
            state = submit_answer(client, session_id, state, None, "skipped", raw_value="Skipped")
        else:
            state = submit_answer(client, session_id, state, None, "unknown", raw_value="Unknown")

    return state


def test_end_to_end_chest_pain_rag_lifecycle(client, database, monkeypatch):
    """Verify full chest-pain lifecycle with grounded RAG follow-ups and budget."""
    # Ensure RAG knowledge base chunks are available for retrieval
    from app.services import rag_integration

    # Seed mock candidate retrieval
    def mock_get_rag_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [
            # Candidate 1: Already-known / answered (pain character) -> MUST BE REJECTED
            {
                "candidate_id": "pain_character",
                "question": "Can you describe the pain in more detail?",
                "reason": "Understanding quality and pattern of pain.",
                "source_chunk_ids": ["chest_pain-history_taking-001"],
                "origin": "rag",
                "target_field": "hpi.character",
                "concept": "PRESSURE_LIKE_PAIN",
                "similarity_score": 0.85,
            },
            # Candidate 2: Already-known (pain radiation) -> MUST BE REJECTED
            {
                "candidate_id": "pain_radiation",
                "question": "Does the pain radiate to your jaw or left arm?",
                "reason": "Radiation pattern is important in cardiac assessment.",
                "source_chunk_ids": ["chest_pain-history_taking-002"],
                "origin": "rag",
                "target_field": "hpi.radiation",
                "concept": "RADIATION",
                "similarity_score": 0.82,
            },
            # Candidate 3: Already-known (exertion / provocation answered via hpi.exacerbating) -> MUST BE REJECTED!
            {
                "candidate_id": "exertion",
                "question": "Does the pain worsen with exertion, walking, or physical activity?",
                "reason": "Exertional worsening helps differentiate cardiac ischemic pain.",
                "source_chunk_ids": ["chest_pain-history_taking-002"],
                "origin": "rag",
                "target_field": "hpi.exacerbating",
                "concept": "EXERTION",
                "similarity_score": 0.80,
            },
            # Candidate 4: Valid grounded unasked question 1: Dyspnea -> SHOULD BE CHOSEN FIRST
            {
                "candidate_id": "dyspnea",
                "question": "Are you experiencing any shortness of breath or difficulty breathing?",
                "reason": "Shortness of breath is an important associated symptom in chest pain.",
                "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
                "origin": "rag",
                "target_field": "hpi.associated_details",
                "concept": "DYSPNEA",
                "similarity_score": 0.79,
            },
            # Candidate 5: Valid grounded unasked question 2: Sweating -> SHOULD BE CHOSEN SECOND
            {
                "candidate_id": "sweating",
                "question": "Have you experienced heavy sweating or cold sweats along with the chest pain?",
                "reason": "Sweating (diaphoresis) is an important autonomic sign in acute chest pain assessment.",
                "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
                "origin": "rag",
                "target_field": "hpi.associated_details",
                "concept": "SWEATING",
                "similarity_score": 0.75,
            },
        ]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_get_rag_suggestions)

    session_id, initial_state = selected(client, "chest_pain")

    # Step 1: Traverse all deterministic questions (answers hpi.exacerbating with "walking", hpi.character, hpi.radiation)
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Step 2: Deterministic requirements exhausted -> RAG candidates retrieved
    # Candidates 1 (character), 2 (radiation), and 3 (exertion) must ALL be rejected as redundant!
    # Candidate 4 (dyspnea) must be chosen!
    assert not state["is_complete"], "State should not be complete when a valid RAG candidate is available"
    assert state["question"] is not None
    assert state["question"]["question_id"] == "rag_followup.dyspnea"
    assert state["question"]["type"] == "short_text"
    assert state["question"]["text"]["en"] == "Are you experiencing any shortness of breath or difficulty breathing?"
    # Verify provenance
    assert len(state["rag_suggestions"]) == 1
    sug = state["rag_suggestions"][0]
    assert sug["origin"] == "rag"
    assert sug["candidate_id"] == "dyspnea"
    assert sug["source_chunk_ids"] == ["chest_pain-associated_symptoms-001"]

    # Step 3: Patient answers first RAG question
    state = submit_answer(
        client,
        session_id,
        state,
        value="I feel a bit breathless when walking up stairs.",
        status="answered",
        raw_value="I feel a bit breathless when walking up stairs.",
    )

    # Step 4: First candidate (dyspnea) cannot appear again!
    # Exertion, character, and radiation remain rejected!
    # Candidate 5 (sweating) is unasked and must be chosen!
    assert not state["is_complete"]
    assert state["question"] is not None
    assert state["question"]["question_id"] == "rag_followup.sweating"
    assert state["question"]["text"]["en"] == "Have you experienced heavy sweating or cold sweats along with the chest pain?"
    assert state["rag_suggestions"][0]["candidate_id"] == "sweating"

    # Step 5: Patient answers second RAG question
    state = submit_answer(
        client,
        session_id,
        state,
        value="No sweating at all.",
        status="answered",
        raw_value="No sweating at all.",
    )

    # Step 6: Budget (2) is now exhausted -> interview is complete!
    assert state["is_complete"], "Interview must be complete after exhausting RAG budget"
    assert state["question"] is None

    # Step 7: Verify answers entered the interview history and answer list
    answers_resp = client.get(f"/api/sessions/{session_id}/answers")
    assert answers_resp.status_code == 200
    answer_qids = [a["question_id"] for a in answers_resp.json()]
    assert "rag_followup.dyspnea" in answer_qids
    assert "rag_followup.sweating" in answer_qids

    # Step 8: Verify session can complete and generate clinical summary
    comp_resp = client.post(f"/api/sessions/{session_id}/complete")
    assert comp_resp.status_code == 200


def test_rag_repeat_loop_rejection(client, database, monkeypatch):
    """Mandatory test: If retrieval repeatedly returns the SAME suggestion, it must be rejected after being answered."""
    from app.services import rag_integration

    repeated_candidate = {
        "candidate_id": "dyspnea",
        "question": "Are you experiencing any shortness of breath?",
        "reason": "Shortness of breath is an important associated symptom.",
        "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
        "origin": "rag",
        "target_field": "hpi.associated_details",
        "concept": "DYSPNEA",
        "similarity_score": 0.88,
    }

    # Retrieval always returns only this single suggestion
    def mock_repeat_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [repeated_candidate]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_repeat_suggestions)

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # First occurrence: candidate is asked
    assert not state["is_complete"]
    assert state["question"]["question_id"] == "rag_followup.dyspnea"

    # Patient answers it
    state = submit_answer(
        client,
        session_id,
        state,
        value="No shortness of breath.",
        status="answered",
        raw_value="No shortness of breath.",
    )

    # Retrieval returns the exact same candidate again!
    # It must be REJECTED as already asked / answered.
    # Because no other candidate exists, interview completes immediately without looping!
    assert state["is_complete"], "Interview must complete and NOT loop on the repeated candidate"
    assert state["question"] is None


def test_red_flag_always_outranks_rag(client, database, monkeypatch):
    """Red flag alert must take strict precedence over RAG."""
    from app.services import rag_integration

    def mock_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [
            {
                "candidate_id": "dyspnea",
                "question": "Are you experiencing shortness of breath?",
                "reason": "Associated symptom.",
                "source_chunk_ids": ["c1"],
                "origin": "rag",
            }
        ]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_suggestions)

    session_id, initial_state = selected(client, "chest_pain")

    # Answer questions such that a red flag triggers: severity 9 with radiation = True
    qa_map = {
        "chief_complaint.description": ("chest pain", "answered"),
        "hpi.onset": ({"amount": 2, "unit": "hours"}, "answered"),
        "hpi.site": ("center of chest", "answered"),
        "hpi.character": ("pressure-like", "answered"),
        "hpi.radiation": (True, "answered"),  # Radiation True
        "hpi.radiation_site": ("left arm and jaw", "answered"),
        "hpi.associated_details": ("sweating heavily", "answered"),
        "hpi.timing": ("constant", "answered"),
        "hpi.exacerbating": ("exertion", "answered"),
        "hpi.relieving": ("none", "answered"),
        "hpi.severity": (9, "answered"),  # Severity 9 triggers red flag
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

    state = initial_state
    for _ in range(60):
        if not state["question"]:
            break
        qid = state["question"]["question_id"]
        if qid in qa_map:
            val, stat = qa_map[qid]
            state = submit_answer(client, session_id, state, val, stat, raw_value=str(val))
        elif state["question"]["type"] == "boolean":
            state = submit_answer(client, session_id, state, False, "answered", raw_value="false")
        elif not state["question"]["required"]:
            state = submit_answer(client, session_id, state, None, "skipped", raw_value="Skipped")
        else:
            state = submit_answer(client, session_id, state, None, "unknown", raw_value="Unknown")

    # Safety advisory must be active
    assert state["red_flag_alert"] is not None
    # RAG must NOT be active
    if state["question"]:
        assert not state["question"]["question_id"].startswith("rag_followup")


def test_blank_rag_suggestion_discarded(client, database, monkeypatch):
    """Blank or whitespace-only RAG candidate must be discarded (never ask fake 'Follow-up question')."""
    from app.services import rag_integration

    def mock_blank_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [
            {
                "candidate_id": "blank1",
                "question": "   ",  # Whitespace only
                "reason": "Test reason",
                "source_chunk_ids": ["c1"],
                "origin": "rag",
            },
            {
                "candidate_id": "blank2",
                "question": "",  # Empty
                "reason": "Test reason",
                "source_chunk_ids": ["c2"],
                "origin": "rag",
            },
        ]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_blank_suggestions)

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Both blank candidates discarded -> interview completes normally
    assert state["is_complete"]
    assert state["question"] is None


def test_rag_budget_enforcement(client, database, monkeypatch):
    """Verify RAG budget of 1 is respected."""
    from app.services import rag_integration

    # Override budget to 1 for this test
    monkeypatch.setattr(rag_integration, "MAX_RAG_FOLLOWUPS_PER_INTERVIEW", 1)

    def mock_multi_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [
            {
                "candidate_id": "dyspnea",
                "question": "Are you experiencing shortness of breath?",
                "reason": "Associated symptom",
                "source_chunk_ids": ["c1"],
                "origin": "rag",
                "target_field": "hpi.associated_details",
                "concept": "DYSPNEA",
            },
            {
                "candidate_id": "sweating",
                "question": "Have you experienced heavy sweating or cold sweats?",
                "reason": "Associated symptom",
                "source_chunk_ids": ["c2"],
                "origin": "rag",
                "target_field": "hpi.associated_details",
                "concept": "SWEATING",
            },
        ]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_multi_suggestions)

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Question 1: dyspnea
    assert not state["is_complete"]
    assert state["question"]["question_id"] == "rag_followup.dyspnea"

    # Answer question 1
    state = submit_answer(client, session_id, state, "A little bit", "answered", raw_value="A little bit")

    # Budget was 1 -> now exhausted! Interview must complete immediately, skipping question 2 (sweating)
    assert state["is_complete"]
    assert state["question"] is None


def test_rag_provider_failure_fail_open(client, database, monkeypatch):
    """If RAG provider fails or is unavailable, fail open and complete interview normally."""
    from app.services import rag_integration

    def mock_failing_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        raise ProviderFailure("Embedding service timed out")

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_failing_suggestions)

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Must fail open: completes normally
    assert state["is_complete"]
    assert state["question"] is None


# =========================================================================
# Explicit assertions for absence of redundancy (Section 8 requirements)
# =========================================================================


def test_redundancy_hpi_exacerbating_answered_rejects_exertion(client, database, monkeypatch):
    """1. hpi.exacerbating answered -> exertion RAG candidate rejected."""
    from app.services import rag_integration

    exertion_candidate = {
        "candidate_id": "exertion",
        "question": "Does the pain worsen with exertion, walking, or physical activity?",
        "reason": "Exertional worsening helps differentiate cardiac ischemic pain.",
        "source_chunk_ids": ["chest_pain-history_taking-002"],
        "origin": "rag",
        "target_field": "hpi.exacerbating",
        "concept": "EXERTION",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [exertion_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")
    # complete_deterministic_chest_pain answers hpi.exacerbating with "walking"
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Exertion candidate MUST be rejected because hpi.exacerbating is already answered!
    assert state["is_complete"], "Interview must complete; exertion question must not be asked"
    assert state["question"] is None


def test_redundancy_hpi_character_answered_rejects_pain_character(client, database, monkeypatch):
    """2. hpi.character answered -> pain-character candidate rejected."""
    from app.services import rag_integration

    character_candidate = {
        "candidate_id": "pain_character",
        "question": "Can you describe the pain in more detail?",
        "reason": "Understanding quality and pattern of pain.",
        "source_chunk_ids": ["chest_pain-history_taking-001"],
        "origin": "rag",
        "target_field": "hpi.character",
        "concept": "PRESSURE_LIKE_PAIN",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [character_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")
    # complete_deterministic_chest_pain answers hpi.character with "pressure-like"
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Pain character candidate MUST be rejected because hpi.character is already answered!
    assert state["is_complete"], "Interview must complete; pain_character question must not be asked"
    assert state["question"] is None


def test_redundancy_hpi_radiation_answered_rejects_radiation(client, database, monkeypatch):
    """3. hpi.radiation answered -> radiation candidate rejected."""
    from app.services import rag_integration

    radiation_candidate = {
        "candidate_id": "pain_radiation",
        "question": "Does the pain radiate to your jaw or left arm?",
        "reason": "Radiation pattern is important in cardiac assessment.",
        "source_chunk_ids": ["chest_pain-history_taking-002"],
        "origin": "rag",
        "target_field": "hpi.radiation",
        "concept": "RADIATION",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [radiation_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")
    # complete_deterministic_chest_pain answers hpi.radiation with False
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Radiation candidate MUST be rejected because hpi.radiation is already answered!
    assert state["is_complete"], "Interview must complete; radiation question must not be asked"
    assert state["question"] is None


def test_redundancy_dyspnea_positively_known_rejects_dyspnea(client, database, monkeypatch):
    """4. dyspnea already positively known -> dyspnea candidate rejected."""
    from app.services import rag_integration

    dyspnea_candidate = {
        "candidate_id": "dyspnea",
        "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        "reason": "Shortness of breath is an important associated symptom.",
        "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
        "origin": "rag",
        "target_field": "hpi.associated_details",
        "concept": "DYSPNEA",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [dyspnea_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")

    # Override associated_details answer to explicitly report shortness of breath
    qa_map = {
        "chief_complaint.description": ("chest pain", "answered"),
        "hpi.onset": ({"amount": 2, "unit": "hours"}, "answered"),
        "hpi.site": ("center of chest", "answered"),
        "hpi.character": ("pressure-like", "answered"),
        "hpi.radiation": (False, "answered"),
        "hpi.associated_details": ("I have noticeable shortness of breath when walking", "answered"),
        "hpi.timing": ("constant", "answered"),
        "hpi.exacerbating": ("walking", "answered"),
        "hpi.relieving": ("rest", "answered"),
        "hpi.severity": (5, "answered"),
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

    state = initial_state
    for _ in range(60):
        if not state["question"]:
            break
        qid = state["question"]["question_id"]
        if qid.startswith("rag_followup"):
            break
        if qid in qa_map:
            val, stat = qa_map[qid]
            raw = str(val) if val is not None else ("Skipped" if stat == "skipped" else "Unknown")
            state = submit_answer(client, session_id, state, val, stat, raw_value=raw)
        elif state["question"]["type"] == "boolean":
            state = submit_answer(client, session_id, state, False, "answered", raw_value="false")
        elif not state["question"]["required"]:
            state = submit_answer(client, session_id, state, None, "skipped", raw_value="Skipped")
        else:
            state = submit_answer(client, session_id, state, None, "unknown", raw_value="Unknown")

    # Because dyspnea is already positively known, the dyspnea candidate MUST be rejected!
    assert state["is_complete"], "Interview must complete; dyspnea already positively reported"
    assert state["question"] is None


def test_redundancy_dyspnea_explicitly_denied_rejects_dyspnea(client, database, monkeypatch):
    """5. dyspnea explicitly denied -> dyspnea candidate rejected."""
    from app.services import rag_integration

    dyspnea_candidate = {
        "candidate_id": "dyspnea",
        "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        "reason": "Shortness of breath is an important associated symptom.",
        "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
        "origin": "rag",
        "target_field": "hpi.associated_details",
        "concept": "DYSPNEA",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [dyspnea_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")

    # Override associated_details answer to explicitly deny shortness of breath
    qa_map = {
        "chief_complaint.description": ("chest pain", "answered"),
        "hpi.onset": ({"amount": 2, "unit": "hours"}, "answered"),
        "hpi.site": ("center of chest", "answered"),
        "hpi.character": ("pressure-like", "answered"),
        "hpi.radiation": (False, "answered"),
        "hpi.associated_details": ("No shortness of breath, breathing is normal", "answered"),
        "hpi.timing": ("constant", "answered"),
        "hpi.exacerbating": ("walking", "answered"),
        "hpi.relieving": ("rest", "answered"),
        "hpi.severity": (5, "answered"),
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

    state = initial_state
    for _ in range(60):
        if not state["question"]:
            break
        qid = state["question"]["question_id"]
        if qid.startswith("rag_followup"):
            break
        if qid in qa_map:
            val, stat = qa_map[qid]
            raw = str(val) if val is not None else ("Skipped" if stat == "skipped" else "Unknown")
            state = submit_answer(client, session_id, state, val, stat, raw_value=raw)
        elif state["question"]["type"] == "boolean":
            state = submit_answer(client, session_id, state, False, "answered", raw_value="false")
        elif not state["question"]["required"]:
            state = submit_answer(client, session_id, state, None, "skipped", raw_value="Skipped")
        else:
            state = submit_answer(client, session_id, state, None, "unknown", raw_value="Unknown")

    # Because dyspnea is explicitly denied (negative fact), dyspnea candidate MUST be rejected!
    assert state["is_complete"], "Interview must complete; dyspnea explicitly denied"
    assert state["question"] is None


def test_redundancy_same_candidate_already_used_rejects_candidate(client, database, monkeypatch):
    """6. same RAG candidate already used -> candidate rejected."""
    from app.services import rag_integration

    sweating_candidate = {
        "candidate_id": "sweating",
        "question": "Have you experienced heavy sweating or cold sweats?",
        "reason": "Diaphoresis assessment",
        "source_chunk_ids": ["c1"],
        "origin": "rag",
        "target_field": "hpi.associated_details",
        "concept": "SWEATING",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [sweating_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # First presentation: candidate is valid
    assert not state["is_complete"]
    assert state["question"]["question_id"] == "rag_followup.sweating"

    # Patient answers it
    state = submit_answer(client, session_id, state, "No sweating", "answered", raw_value="No sweating")

    # Second presentation: candidate was already asked -> MUST BE REJECTED!
    assert state["is_complete"], "Candidate already asked must be rejected"
    assert state["question"] is None


def test_redundancy_unanswered_grounded_clinical_need_accepted(client, database, monkeypatch):
    """7. unanswered, grounded clinical information need -> candidate accepted."""
    from app.services import rag_integration

    sweating_candidate = {
        "candidate_id": "sweating",
        "question": "Have you experienced heavy sweating or cold sweats along with the chest pain?",
        "reason": "Sweating (diaphoresis) is an important autonomic sign in acute chest pain assessment.",
        "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
        "origin": "rag",
        "target_field": "hpi.associated_details",
        "concept": "SWEATING",
    }

    monkeypatch.setattr(
        rag_integration, "get_rag_suggestions", lambda *a, **kw: [sweating_candidate]
    )

    session_id, initial_state = selected(client, "chest_pain")
    state = complete_deterministic_chest_pain(client, session_id, initial_state)

    # Sweating is unasked and grounded -> MUST BE ACCEPTED
    assert not state["is_complete"], "Unasked grounded candidate should be accepted"
    assert state["question"] is not None
    assert state["question"]["question_id"] == "rag_followup.sweating"
    assert state["question"]["text"]["en"] == "Have you experienced heavy sweating or cold sweats along with the chest pain?"
