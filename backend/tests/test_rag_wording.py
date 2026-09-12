"""Tests for RAG question wording provider, deterministic validation, and safety guardrails."""

import json
from unittest.mock import patch

import httpx2 as httpx
import pytest

from app.services.rag_wording_provider import (
    DisabledWordingProvider,
    NvidiaWordingProvider,
    NvidiaWordingSettings,
    TemplateWordingProvider,
    configured_wording_provider,
)
from app.services.rag_wording_validator import validate_generated_wording


class TestRAGWordingValidator:
    """Adversarial and boundary tests for the deterministic wording validator."""

    def test_adversarial_case_a_diagnosis_claim(self):
        # Case A: {"question": "You are probably having a heart attack. Are you short of breath?"}
        raw = '{"question": "You are probably having a heart attack. Are you short of breath?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "diagnosis" in reason
        assert result == fallback

    def test_adversarial_case_b_multiple_information_needs(self):
        # Case B: {"question": "Are you short of breath and are you sweating heavily?"}
        raw = '{"question": "Are you short of breath and are you sweating heavily?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "multi_question" in reason or "cross_target" in reason
        assert result == fallback

    def test_adversarial_case_c_treatment_instruction(self):
        # Case C: {"question": "Take aspirin immediately."}
        raw = '{"question": "Take aspirin immediately."}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "treatment" in reason
        assert result == fallback

    def test_adversarial_case_d_blank_question(self):
        # Case D: {"question": ""}
        raw = '{"question": ""}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "blank" in reason
        assert result == fallback

    def test_adversarial_case_e_non_json_prose(self):
        # Case E: non-JSON prose
        raw = "Here is a question you can ask the patient: Are you short of breath?"
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "invalid_json" in reason
        assert result == fallback

    def test_adversarial_case_f_wrong_clinical_target(self):
        # Case F: {"question": "Does the pain spread into your left arm?"} while approved candidate = dyspnea
        raw = '{"question": "Does the pain spread into your left arm?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "mismatch" in reason or "cross_target" in reason
        assert result == fallback

    def test_adversarial_case_g_valid_dyspnea_wording(self):
        # Case G: valid dyspnea wording
        raw = '{"question": "Have you felt short of breath along with the chest discomfort?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is True
        assert reason == "valid"
        assert result == "Have you felt short of breath along with the chest discomfort?"

    def test_adversarial_markdown_code_fences_rejected(self):
        raw = '```json\n{"question": "Are you feeling short of breath?"}\n```'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "markdown" in reason
        assert result == fallback

    def test_adversarial_multiple_question_marks_rejected(self):
        raw = '{"question": "Are you short of breath? Since when?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "multiple_questions" in reason
        assert result == fallback

    def test_adversarial_ai_provenance_rejected(self):
        raw = '{"question": "According to clinical guidelines, are you having trouble breathing?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "ai_provenance" in reason
        assert result == fallback

    def test_adversarial_question_too_long_rejected(self):
        long_q = "Are you having difficulty breathing " + ("very " * 50) + "badly?"
        raw = json.dumps({"question": long_q})
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "too_long" in reason
        assert result == fallback

    def test_adversarial_question_too_short_rejected(self):
        raw = '{"question": "Hi?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "too_short" in reason
        assert result == fallback

    def test_adversarial_missing_question_field_rejected(self):
        raw = '{"query": "Are you short of breath?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "missing_question_field" in reason
        assert result == fallback

    def test_adversarial_duplicate_json_keys_rejected(self):
        raw = '{"question": "Are you short of breath?", "question": "Are you sweating?"}'
        fallback = "Are you experiencing any shortness of breath or difficulty breathing?"
        is_valid, reason, result = validate_generated_wording(raw, "dyspnea", fallback)

        assert is_valid is False
        assert "invalid_json" in reason or "Duplicate" in reason
        assert result == fallback


class TestCandidateSpecificWording:
    """Verify validation on multiple approved candidates."""

    @pytest.mark.parametrize(
        "cid,valid_text,invalid_text",
        [
            (
                "dyspnea",
                "Have you noticed any difficulty breathing or shortness of breath?",
                "Are you sweating heavily?",
            ),
            (
                "sweating",
                "Have you experienced cold sweats or heavy sweating?",
                "Do you feel nauseous?",
            ),
            (
                "nausea",
                "Have you felt sick to your stomach or had nausea?",
                "Does the pain shoot down your arm?",
            ),
            (
                "dizziness",
                "Have you felt dizzy, lightheaded, or faint?",
                "Have you been coughing up phlegm?",
            ),
            (
                "cough_fever",
                "Have you had a cough or fever alongside the chest pain?",
                "Are you sweating profusely?",
            ),
            (
                "pain_character",
                "How would you describe the feeling of the chest pain, such as pressure or sharpness?",
                "Are you experiencing any shortness of breath?",
            ),
            (
                "pain_radiation",
                "Does the chest discomfort spread into your neck, jaw, or arm?",
                "Have you felt lightheaded or dizzy?",
            ),
            (
                "exertion",
                "Does the pain worsen when you walk or exert yourself?",
                "Have you noticed any fever or cough?",
            ),
        ],
    )
    def test_candidate_target_discrimination(self, cid, valid_text, invalid_text):
        fallback = f"Default question for {cid}"
        # Valid question for this target
        ok_valid, _, res_valid = validate_generated_wording(
            json.dumps({"question": valid_text}), cid, fallback
        )
        assert ok_valid is True
        assert res_valid.startswith(valid_text[:20])

        # Invalid question (belongs to different domain)
        bad_valid, _, res_bad = validate_generated_wording(
            json.dumps({"question": invalid_text}), cid, fallback
        )
        assert bad_valid is False
        assert res_bad == fallback


class TestWordingProviders:
    """Test wording providers abstraction and error handling."""

    def test_template_provider(self):
        provider = TemplateWordingProvider()
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.provider == "template"
        assert res.fallback_used is False
        assert res.question == candidate["question"]
        assert res.template_question == candidate["question"]

    def test_disabled_provider(self):
        provider = DisabledWordingProvider()
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.provider == "disabled"
        assert res.fallback_used is False
        assert res.question == candidate["question"]

    def test_configured_provider_factory(self):
        p_template = configured_wording_provider("template")
        assert isinstance(p_template, TemplateWordingProvider)

        p_disabled = configured_wording_provider("disabled")
        assert isinstance(p_disabled, DisabledWordingProvider)

        with patch.dict("os.environ", {"RAG_GENERATION_PROVIDER": "template"}):
            p_env = configured_wording_provider()
            assert isinstance(p_env, TemplateWordingProvider)

    def test_nvidia_provider_missing_api_key_fallbacks(self):
        settings = NvidiaWordingSettings(
            api_key="",
            model="meta/llama-3.2-11b-vision-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=1.0,
            temperature=0.1,
            max_tokens=100,
        )
        provider = NvidiaWordingProvider(settings=settings)
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.fallback_used is True
        assert res.fallback_reason == "missing_api_key"
        assert res.question == candidate["question"]

    def test_nvidia_provider_mocked_success(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '{"question": "Are you feeling short of breath?"}'
                            },
                        }
                    ]
                },
            )
        )
        settings = NvidiaWordingSettings(
            api_key="nvapi-test-key",
            model="meta/llama-3.2-11b-vision-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=1.0,
            temperature=0.1,
            max_tokens=100,
        )
        provider = NvidiaWordingProvider(settings=settings, transport=transport)
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.fallback_used is False
        assert res.question == "Are you feeling short of breath?"
        assert res.template_question == candidate["question"]
        assert res.provider == "nvidia"

    def test_nvidia_provider_mocked_server_error_fallback(self):
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, json={"error": "Internal Server Error"})
        )
        settings = NvidiaWordingSettings(
            api_key="nvapi-test-key",
            model="meta/llama-3.2-11b-vision-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=1.0,
            temperature=0.1,
            max_tokens=100,
        )
        provider = NvidiaWordingProvider(settings=settings, transport=transport)
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.fallback_used is True
        assert res.fallback_reason == "http_500"
        assert res.question == candidate["question"]

    def test_nvidia_provider_mocked_validation_failure_fallback(self):
        # LLM returns adversarial response with diagnosis language
        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "content": '{"question": "You are having a heart attack. Are you short of breath?"}'
                            },
                        }
                    ]
                },
            )
        )
        settings = NvidiaWordingSettings(
            api_key="nvapi-test-key",
            model="meta/llama-3.2-11b-vision-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=1.0,
            temperature=0.1,
            max_tokens=100,
        )
        provider = NvidiaWordingProvider(settings=settings, transport=transport)
        candidate = {
            "candidate_id": "dyspnea",
            "question": "Are you experiencing any shortness of breath or difficulty breathing?",
        }
        res = provider.word_candidate(candidate, {}, [])
        assert res.fallback_used is True
        assert "validation_failed" in (res.fallback_reason or "")
        assert res.question == candidate["question"]

    def test_security_settings_does_not_leak_key(self):
        settings = NvidiaWordingSettings(
            api_key="nvapi-super-secret-12345",
            model="meta/llama-3.2-11b-vision-instruct",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=1.0,
            temperature=0.1,
            max_tokens=100,
        )
        assert "nvapi-super-secret-12345" not in repr(settings)
        assert "nvapi-super-secret-12345" not in str(settings)
