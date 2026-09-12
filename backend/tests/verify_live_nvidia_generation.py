"""Live verification script for NVIDIA LLM question wording and end-to-end adaptive RAG interview."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load real environment from backend/.env
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.services.rag_clinical_mapping import CHEST_PAIN_PROFILES  # noqa: E402
from app.services.rag_wording_provider import (  # noqa: E402
    NvidiaWordingProvider,
    NvidiaWordingSettings,
)


def run_live_smoke_tests():
    print("=" * 60)
    print("1. LIVE NVIDIA SMOKE TEST FOR APPROVED CLINICAL CANDIDATES")
    print("=" * 60)

    settings = NvidiaWordingSettings(
        api_key=os.getenv("NVIDIA_API_KEY", ""),
        model=os.getenv("RAG_GENERATION_MODEL", "meta/llama-3.2-11b-vision-instruct"),
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=20.0,
        temperature=0.1,
        max_tokens=100,
    )
    print("Provider: NVIDIA NIM")
    print(f"Model: {settings.model}")
    print(f"Base URL: {settings.base_url}")
    print(f"Timeout: {settings.timeout}s")
    print(f"Temperature: {settings.temperature}")
    print(f"Max Tokens: {settings.max_tokens}")

    provider = NvidiaWordingProvider(settings=settings)

    test_candidates = [
        ("dyspnea", "Shortness of breath is an important associated symptom in chest pain."),
        ("sweating", "Diaphoresis (sweating) is an important autonomic sign in acute chest pain."),
        ("nausea", "Nausea and vomiting are recognized associated autonomic symptoms."),
        ("dizziness", "Dizziness, lightheadedness, and palpitations help assess hemodynamic stability."),
        ("cough_fever", "Cough and fever help evaluate non-cardiac pulmonary or infectious causes."),
    ]

    clinical_context = {
        "raw_answer_texts": [
            "central pressure-like discomfort started 2 hours ago",
            "worse with walking",
            "no pain in left arm or jaw",
        ]
    }

    results = []
    for cid, chunk_text in test_candidates:
        profile = CHEST_PAIN_PROFILES[cid]
        cand = {
            "candidate_id": cid,
            "question": profile.default_question,
            "reason": profile.default_reason,
            "concept": profile.target_concepts[0] if profile.target_concepts else cid.upper(),
            "target_concepts": profile.target_concepts,
            "source_chunk_ids": [profile.default_knowledge_source],
            "chunk_content": chunk_text,
        }

        res = provider.word_candidate(
            candidate=cand,
            clinical_context=clinical_context,
            supporting_chunks=[{"content": chunk_text}],
        )

        print(f"\nCandidate: {cid}")
        print(f"  Approved need: {cand['concept']}", flush=True)
        print(f"  Fallback template: '{res.template_question}'", flush=True)
        print(f"  Generated wording: '{res.question}'", flush=True)
        print(f"  Fallback used: {res.fallback_used}", flush=True)
        print(f"  Fallback reason: {res.fallback_reason}", flush=True)
        print(f"  Latency: {res.latency_ms}ms", flush=True)

        # Verify safety rules
        assert not res.fallback_used, f"Expected live wording to succeed for {cid}, got {res.fallback_reason}"
        assert res.question != "", "Generated question must not be empty"
        assert res.question.count("?") <= 1, "Must be a single question"
        results.append((cid, res))

    print("\n[SUCCESS] All candidates successfully worded by NVIDIA with 0 fallbacks and strict safety validation!")
    return results


def run_failure_fallback_test():
    print("\n" + "=" * 60)
    print("2. GENERATION FAILURE FALLBACK TEST")
    print("=" * 60)

    # Provider with invalid model name to force a provider error
    bad_settings = NvidiaWordingSettings(
        api_key=os.getenv("NVIDIA_API_KEY", ""),
        model="non-existent-model-fail-test",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=3.0,
        temperature=0.1,
        max_tokens=50,
    )
    fail_provider = NvidiaWordingProvider(settings=bad_settings)
    cand = {
        "candidate_id": "dyspnea",
        "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        "reason": "Shortness of breath is an important associated symptom.",
        "source_chunk_ids": ["chest_pain-associated_symptoms-001"],
        "concept": "DYSPNEA",
    }
    res = fail_provider.word_candidate(cand, {}, [])
    print("Failure injection result:")
    print(f"  Fallback used: {res.fallback_used}")
    print(f"  Fallback reason: {res.fallback_reason}")
    print(f"  Final question used: '{res.question}'")
    print(f"  Template preserved: '{res.template_question}'")
    assert res.fallback_used is True
    assert res.question == cand["question"]
    print("[SUCCESS] Generation failure smoothly fell back to deterministic template question!")


def run_live_adaptive_interview_e2e():
    print("\n" + "=" * 60)
    print("3. REAL END-TO-END ADAPTIVE INTERVIEW (NVIDIA Embeddings + NVIDIA LLM Wording)")
    print("=" * 60)

    # Configure live providers for this end-to-end test
    os.environ["RAG_EMBEDDING_PROVIDER"] = "nvidia"
    os.environ["RAG_GENERATION_PROVIDER"] = "nvidia"
    os.environ["CLINICAL_NORMALIZATION_PROVIDER"] = "mock"

    from fastapi.testclient import TestClient

    from app.main import app
    from tests.test_adaptive_rag import complete_deterministic_chest_pain, selected, submit_answer

    client = TestClient(app)
    session_id, state = selected(client, "chest_pain")
    print(f"Session created: {session_id}, initial question: {state['question']['question_id']}", flush=True)

    # Complete all deterministic questions
    state = complete_deterministic_chest_pain(client, session_id, state)
    print(f"Deterministic questions answered. is_complete={state['is_complete']}", flush=True)

    # RAG Question 1: Dyspnea
    assert not state["is_complete"], "Should have RAG follow-up active!"
    q1 = state["question"]
    sug1 = state["rag_suggestions"][0] if state.get("rag_suggestions") else {}
    print("\nRAG Question 1:", flush=True)
    print(f"  Question ID: {q1['question_id']}", flush=True)
    print(f"  Field: {q1['field']}", flush=True)
    print(f"  Question Text: '{q1['text']['en']}'", flush=True)
    print(f"  Candidate ID: {sug1.get('candidate_id')}", flush=True)
    print(f"  Generation Provider: {sug1.get('generation_provider')}", flush=True)
    print(f"  Generation Model: {sug1.get('generation_model')}", flush=True)
    print(f"  Fallback Used: {sug1.get('generation_fallback_used')}", flush=True)
    print(f"  Template Question: '{sug1.get('template_question')}'", flush=True)
    print(f"  Latency: {sug1.get('generation_latency_ms')}ms", flush=True)
    print(f"  Source Chunks: {sug1.get('source_chunk_ids')}", flush=True)

    assert q1["question_id"] == "rag_followup.dyspnea"
    assert sug1.get("candidate_id") == "dyspnea"
    assert sug1.get("generation_provider") == "nvidia"
    assert sug1.get("generation_fallback_used") is False
    assert any(k in q1["text"]["en"].lower() for k in ["breath", "winded"])

    # Answer Dyspnea
    state = submit_answer(client, session_id, state, value="yes, feeling breathless", status="answered")

    # RAG Question 2: Sweating
    assert not state["is_complete"], "Should have second RAG follow-up active!"
    q2 = state["question"]
    sug2 = state["rag_suggestions"][0] if state.get("rag_suggestions") else {}
    print("\nRAG Question 2:", flush=True)
    print(f"  Question ID: {q2['question_id']}", flush=True)
    print(f"  Field: {q2['field']}", flush=True)
    print(f"  Question Text: '{q2['text']['en']}'", flush=True)
    print(f"  Candidate ID: {sug2.get('candidate_id')}", flush=True)
    print(f"  Generation Provider: {sug2.get('generation_provider')}", flush=True)
    print(f"  Generation Model: {sug2.get('generation_model')}", flush=True)
    print(f"  Fallback Used: {sug2.get('generation_fallback_used')}", flush=True)
    print(f"  Template Question: '{sug2.get('template_question')}'", flush=True)
    print(f"  Latency: {sug2.get('generation_latency_ms')}ms", flush=True)
    print(f"  Source Chunks: {sug2.get('source_chunk_ids')}", flush=True)

    assert q2["question_id"] == "rag_followup.sweating"
    assert sug2.get("candidate_id") == "sweating"
    assert sug2.get("generation_provider") == "nvidia"
    assert sug2.get("generation_fallback_used") is False
    assert any(k in q2["text"]["en"].lower() for k in ["sweat", "clammy"])

    # Answer Sweating
    state = submit_answer(client, session_id, state, value="no sweating", status="answered")

    # Interview should now be complete (Budget = 2 reached!)
    print("\nFinal Interview State:", flush=True)
    print(f"  is_complete: {state['is_complete']}", flush=True)
    print(f"  question: {state.get('question')}", flush=True)
    print(f"  total active answers: {len(state.get('active_answers', []))}", flush=True)

    assert state["is_complete"] is True
    assert state.get("question") is None
    print("\n[SUCCESS] Real end-to-end adaptive interview with live NVIDIA embeddings + live NVIDIA LLM wording completed flawlessly!", flush=True)


if __name__ == "__main__":
    run_live_smoke_tests()
    run_failure_fallback_test()
    run_live_adaptive_interview_e2e()
