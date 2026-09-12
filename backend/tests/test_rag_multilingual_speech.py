"""Unit and integration tests for multilingual RAG question presentation and speech synthesis."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.translation import TranslationResponse
from app.services.rag_integration import clear_rag_question_cache
from app.services.rag_localization import (
    clear_translation_cache,
    localize_rag_question,
)
from app.services.translation_provider import MockTranslationProvider
from tests.test_workflow import consent, create


@pytest.fixture(autouse=True)
def _clean_caches():
    clear_translation_cache()
    clear_rag_question_cache()
    yield
    clear_translation_cache()
    clear_rag_question_cache()


def test_english_rag_bypasses_translation():
    """English canonical question should bypass translation calls to eliminate latency."""
    canonical = "Have you noticed any shortness of breath with the chest discomfort?"
    localized, meta = localize_rag_question(canonical_en=canonical, target_language="en", candidate_id="dyspnea")

    assert localized.en == canonical
    assert localized.bn == canonical  # Safe fallback for unused language
    assert localized.hi == canonical
    assert meta.provider == "none"
    assert meta.fallback_used is False
    assert meta.latency_ms == 0


def test_bengali_rag_uses_translation():
    """Bengali selected language should invoke the translation provider."""
    canonical = "Have you noticed any shortness of breath with the chest discomfort?"
    localized, meta = localize_rag_question(canonical_en=canonical, target_language="bn", candidate_id="dyspnea")

    assert localized.en == canonical
    assert localized.bn != ""
    assert localized.bn != canonical  # Mock translated
    assert meta.provider == "mock"
    assert meta.fallback_used is False


def test_hindi_rag_uses_translation():
    """Hindi selected language should invoke the translation provider."""
    canonical = "Have you noticed any shortness of breath with the chest discomfort?"
    localized, meta = localize_rag_question(canonical_en=canonical, target_language="hi", candidate_id="dyspnea")

    assert localized.en == canonical
    assert localized.hi != ""
    assert localized.hi != canonical
    assert meta.provider == "mock"
    assert meta.fallback_used is False


def test_translation_failure_is_failsafe():
    """If translation fails or raises, system must fall back to canonical English safely."""
    canonical = "Have you noticed any shortness of breath with the chest discomfort?"

    with patch.object(
        MockTranslationProvider,
        "translate",
        new=AsyncMock(side_effect=RuntimeError("Sarvam service unreachable")),
    ):
        localized, meta = localize_rag_question(canonical_en=canonical, target_language="bn", candidate_id="dyspnea")

    assert localized.en == canonical
    assert localized.bn == canonical  # Fell back safely to canonical English
    assert meta.fallback_used is True
    assert meta.reason == "RuntimeError"


def test_translation_unavailable_status_fallback():
    """If translation returns status='unavailable', fallback to canonical English."""
    canonical = "Have you noticed any shortness of breath with the chest discomfort?"

    with patch.object(
        MockTranslationProvider,
        "translate",
        new=AsyncMock(
            return_value=TranslationResponse(
                status="unavailable",
                source_text=canonical,
                source_language="en",
                target_language="bn",
                provider="mock",
                reason="rate_limited",
            )
        ),
    ):
        localized, meta = localize_rag_question(canonical_en=canonical, target_language="bn", candidate_id="dyspnea")

    assert localized.en == canonical
    assert localized.bn == canonical
    assert meta.fallback_used is True
    assert meta.reason == "rate_limited"


def test_translation_cache_prevents_duplicate_calls():
    """Identical canonical English and language should be served from cache."""
    canonical = "Do you have any dizziness?"
    loc1, meta1 = localize_rag_question(canonical_en=canonical, target_language="bn", candidate_id="dizziness")

    # Mutate mock to fail - second call must return cached result
    with patch.object(
        MockTranslationProvider,
        "translate",
        new=AsyncMock(side_effect=RuntimeError("Should not be called")),
    ):
        loc2, meta2 = localize_rag_question(canonical_en=canonical, target_language="bn", candidate_id="dizziness")

    assert loc1 == loc2
    assert meta1 == meta2


def _setup_full_chest_pain_interview(client, monkeypatch, language="en"):
    """Helper to register session, consent, chest pain flow and answer all deterministic questions with matching language."""
    from app.services import rag_integration

    def mock_get_rag_suggestions(session_id, db_session_factory=None, top_k=6, min_similarity=0.1):
        return [
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
            {
                "candidate_id": "sweating",
                "question": "Have you experienced heavy sweating or cold sweats along with the chest pain?",
                "reason": "Sweating is an important autonomic sign in acute chest pain assessment.",
                "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
                "origin": "rag",
                "target_field": "hpi.associated_details",
                "concept": "SWEATING",
                "similarity_score": 0.75,
            },
        ]

    monkeypatch.setattr(rag_integration, "get_rag_suggestions", mock_get_rag_suggestions)

    session_id, _ = create(client, language)
    consent(client, session_id)
    resp = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": "chest_pain"})
    assert resp.status_code == 200
    state = resp.json()

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

    for _ in range(60):
        if not state.get("question"):
            break
        qid = state["question"]["question_id"]
        if qid.startswith("rag_followup"):
            break

        val, stat = qa_map.get(
            qid,
            (False, "answered") if state["question"]["type"] == "boolean" else (None, "skipped"),
        )
        raw = str(val) if val is not None else ("Skipped" if stat == "skipped" else "Unknown")
        body = {
            "request_id": str(uuid4()),
            "expected_revision": state["revision"],
            "question_id": qid,
            "status": stat,
            "value": val,
            "raw_value": raw,
            "source": "typed",
            "language": language,
        }
        res = client.post(f"/api/sessions/{session_id}/interview/answers", json=body)
        assert res.status_code == 200, res.text
        state = res.json()

    return session_id, state


def test_bengali_rag_question_presentation_and_tts(client, monkeypatch):
    """Bengali session displays translated question text and synthesizes Bengali speech."""
    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="bn")

    # We should now be at the first RAG follow-up question
    q = st.get("question")
    assert q is not None
    assert q["question_id"].startswith("rag_followup.")
    assert q["type"] == "short_text"

    # In Bengali session, bn text must be non-empty and present
    assert q["text"]["bn"] != ""
    assert q["text"]["en"] != ""  # Canonical English preserved

    # Provenance check: RAGSuggestion preserves canonical English
    assert len(st["rag_suggestions"]) > 0
    sug = st["rag_suggestions"][0]
    assert sug["display_language"] == "bn"
    assert sug["translated_question"] == q["text"]["bn"]
    assert sug["candidate_id"] in ("dyspnea", "sweating", "nausea", "dizziness")

    # Speech synthesis check: TTS synthesizes the exact Bengali text
    tts_resp = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": q["question_id"]},
    )
    assert tts_resp.status_code == 200
    tts_data = tts_resp.json()
    assert tts_data["status"] == "success"
    assert tts_data["language"] == "bn"
    assert tts_data["text"] == q["text"]["bn"]
    assert len(tts_data["audio_base64"]) > 0


def test_hindi_rag_question_presentation_and_tts(client, monkeypatch):
    """Hindi session displays translated question text and synthesizes Hindi speech."""
    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="hi")

    q = st.get("question")
    assert q is not None
    assert q["question_id"].startswith("rag_followup.")

    # In Hindi session, hi text must be non-empty and present
    assert q["text"]["hi"] != ""
    assert q["text"]["en"] != ""

    sug = st["rag_suggestions"][0]
    assert sug["display_language"] == "hi"
    assert sug["translated_question"] == q["text"]["hi"]

    tts_resp = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": q["question_id"]},
    )
    assert tts_resp.status_code == 200
    tts_data = tts_resp.json()
    assert tts_data["status"] == "success"
    assert tts_data["language"] == "hi"
    assert tts_data["text"] == q["text"]["hi"]


def test_english_rag_question_presentation_and_tts(client, monkeypatch):
    """English session directly presents canonical English and synthesizes English speech without translation."""
    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="en")

    q = st.get("question")
    assert q is not None
    assert q["question_id"].startswith("rag_followup.")
    assert q["text"]["en"] != ""

    sug = st["rag_suggestions"][0]
    assert sug["display_language"] == "en"
    assert sug["translation_provider"] == "none"
    assert sug["translation_fallback_used"] is False

    tts_resp = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": q["question_id"]},
    )
    assert tts_resp.status_code == 200
    tts_data = tts_resp.json()
    assert tts_data["status"] == "success"
    assert tts_data["language"] == "en"
    assert tts_data["text"] == q["text"]["en"]


def test_multilingual_rag_answer_submission_and_normalization(client, monkeypatch):
    """Submitting an answer in Bengali to a RAG question persists and advances RAG budget."""
    import uuid

    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="bn")
    q = st.get("question")
    first_rag_id = q["question_id"]

    # Submit Bengali answer
    ans_res = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "question_id": first_rag_id,
            "value": "হাঁটার সময় হালকা শ্বাসকষ্ট হয়",
            "raw_value": "হাঁটার সময় হালকা শ্বাসকষ্ট হয়",
            "language": "bn",
            "source": "typed",
            "status": "answered",
            "expected_revision": st["revision"],
            "request_id": str(uuid.uuid4()),
        },
    )
    assert ans_res.status_code == 200, ans_res.text
    next_st = ans_res.json()

    # RAG candidate 1 answered, next question is candidate 2 or complete
    if next_st.get("question"):
        assert next_st["question"]["question_id"] != first_rag_id
        assert next_st["question"]["question_id"].startswith("rag_followup.")

    # Verify fact appears in active_answers and history
    answers_list = client.get(f"/api/sessions/{session_id}/answers").json()
    rag_answers = [a for a in answers_list if a["question_id"] == first_rag_id]
    assert len(rag_answers) == 1
    assert rag_answers[0]["language"] == "bn"


def test_tts_failure_does_not_break_interview(client, monkeypatch):
    """If TTS synthesis fails, synthesize returns unavailable and interview remains intact and answerable."""
    import uuid

    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="bn")
    q = st["question"]

    from app.services.speech_provider import MockSpeechProvider

    with patch.object(
        MockSpeechProvider,
        "synthesize",
        new=AsyncMock(side_effect=RuntimeError("TTS engine failure")),
    ):
        tts_resp = client.post(
            f"/api/sessions/{session_id}/interview/speech/synthesize",
            json={"question_id": q["question_id"]},
        )
        assert tts_resp.status_code == 200
        tts_data = tts_resp.json()
        assert tts_data["status"] == "unavailable"
        assert tts_data["audio_base64"] is None

    # Patient can still answer normally
    ans_res = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "question_id": q["question_id"],
            "value": "হাঁ",
            "raw_value": "হাঁ",
            "language": "bn",
            "source": "touch",
            "status": "answered",
            "expected_revision": st["revision"],
            "request_id": str(uuid.uuid4()),
        },
    )
    assert ans_res.status_code == 200


def test_template_fallback_passes_through_translation(client, monkeypatch):
    """When NVIDIA wording fails, the deterministic template fallback is translated into session language."""
    from app.services.rag_wording_provider import TemplateWordingProvider, WordingResult

    # Force wording provider to report fallback used
    def mock_word_candidate(self, candidate, clinical_context, supporting_chunks):
        template = candidate["question"].strip()
        return WordingResult(
            question=template,
            provider="template",
            model=None,
            fallback_used=True,
            fallback_reason="forced_fallback_test",
            latency_ms=1,
            template_question=template,
        )

    monkeypatch.setattr(TemplateWordingProvider, "word_candidate", mock_word_candidate)

    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="bn")
    q = st["question"]
    assert q["question_id"].startswith("rag_followup.")

    # Even with wording fallback, Bengali translation occurs
    assert q["text"]["bn"] != ""
    assert q["text"]["en"] != ""

    sug = st["rag_suggestions"][0]
    assert sug["generation_fallback_used"] is True
    assert sug["display_language"] == "bn"
    assert sug["translated_question"] == q["text"]["bn"]


def test_validated_english_wording_translated_not_template(client, monkeypatch):
    """When NVIDIA wording succeeds, the generated English is translated, NOT the template."""
    from app.services.rag_wording_provider import TemplateWordingProvider, WordingResult

    custom_validated_english = "Have you felt breathless during the chest pain?"

    def mock_word_candidate(self, candidate, clinical_context, supporting_chunks):
        return WordingResult(
            question=custom_validated_english,
            provider="mock_nvidia",
            model="test-model",
            fallback_used=False,
            fallback_reason=None,
            latency_ms=42,
            template_question=candidate["question"].strip(),
        )

    monkeypatch.setattr(TemplateWordingProvider, "word_candidate", mock_word_candidate)

    session_id, st = _setup_full_chest_pain_interview(client, monkeypatch, language="bn")
    q = st["question"]

    # Canonical English must be the custom validated wording
    assert q["text"]["en"] == custom_validated_english

    sug = st["rag_suggestions"][0]
    assert sug["question"] == custom_validated_english
    assert sug["template_question"] != custom_validated_english
    assert sug["generation_fallback_used"] is False
    assert sug["display_language"] == "bn"

