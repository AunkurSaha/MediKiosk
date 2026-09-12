"""Deterministic validation and safety screening for generated RAG question wording.

Ensures that LLM-generated wording adheres strictly to:
1. Strict JSON schema {"question": "..."}
2. Single-question constraint (no multiple questions or compound symptom inquiries)
3. Strict diagnosis/prescription/treatment guards
4. Clinical target alignment against the approved candidate's profile
5. Length, formatting, and AI provenance guards
"""

from __future__ import annotations

import json
import logging
import re
from typing import Tuple

from app.services.rag_clinical_mapping import get_profile

logger = logging.getLogger(__name__)

# Disallowed diagnostic assertions and suggestions
DIAGNOSIS_PATTERNS = [
    r"\bheart\s+attack\b",
    r"\bmyocardial\s+infarction\b",
    r"\bangina\b",
    r"\bcoronary\b",
    r"\bcardiac\s+arrest\b",
    r"\bpulmonary\s+embolism\b",
    r"\bpneumonia\b",
    r"\baortic\s+dissection\b",
    r"\bcostochondritis\b",
    r"\bpericarditis\b",
    r"\bgastroesophageal\b",
    r"\bgerd\b",
    r"\bacid\s+reflux\b",
    r"\bstroke\b",
    r"\byou\s+(?:are|might\s+be|could\s+be|may\s+be|probably\s+are)\s+having\b",
    r"\byou\s+have\b",
    r"\bdiagnos(?:is|ed|ing|tic)\b",
    r"\bcondition\s+is\b",
]

# Disallowed treatments, remedies, and emergency directives
TREATMENT_PATTERNS = [
    r"\btake\s+(?:an?\s+)?(?:aspirin|medicine|medication|pill|tablet|nitroglycerin|disprin|sorbitrate)\b",
    r"\bprescrib(?:e|ed|ing|tion)\b",
    r"\bcall\s+(?:an?\s+)?(?:ambulance|911|108|112|doctor)\b",
    r"\bgo\s+to\s+(?:the\s+)?(?:er|emergency|hospital|urgent\s+care)\b",
    r"\bseek\s+immediate\b",
    r"\bswallow\b",
    r"\bchew\b",
    r"\brest\s+immediately\b",
    r"\bmedical\s+advice\b",
    r"\btreatment\b",
]

# Disallowed references to internal AI mechanisms or retrieved knowledge
AI_PROVENANCE_PATTERNS = [
    r"\baccording\s+to\b",
    r"\bclinical\s+guideline\b",
    r"\bretrieved\b",
    r"\bknowledge\s+base\b",
    r"\bchunk\b",
    r"\bdataset\b",
    r"\blanguage\s+model\b",
    r"\bllm\b",
    r"\bai\b",
]

COMPILED_DIAGNOSIS_RES = [re.compile(p, re.IGNORECASE) for p in DIAGNOSIS_PATTERNS]
COMPILED_TREATMENT_RES = [re.compile(p, re.IGNORECASE) for p in TREATMENT_PATTERNS]
COMPILED_AI_RES = [re.compile(p, re.IGNORECASE) for p in AI_PROVENANCE_PATTERNS]

# Keywords belonging to specific clinical symptom domains for cross-contamination detection
CANDIDATE_CROSS_DOMAINS = {
    "pain_onset": {
        "allowed_keywords": ["when", "start", "started", "begin", "began", "how long", "onset"],
        "disallowed_other_symptoms": ["sweat", "nausea", "dizz", "fever"],
    },
    "pain_site": {
        "allowed_keywords": ["where", "location", "located", "part of your chest", "site"],
        "disallowed_other_symptoms": ["sweat", "nausea", "dizz", "fever"],
    },
    "dyspnea": {
        "allowed_keywords": ["short of breath", "shortness of breath", "breathless", "breathing", "breath", "dyspnea", "winded", "air"],
        "disallowed_other_symptoms": ["sweat", "diaphoresis", "nausea", "vomit", "radiat", "left arm", "jaw", "neck", "dizz", "lighthead", "fever"],
    },
    "sweating": {
        "allowed_keywords": ["sweat", "sweating", "sweaty", "diaphoresis", "clammy", "cold sweat"],
        "disallowed_other_symptoms": ["short of breath", "breathless", "breathing", "dyspnea", "nausea", "vomit", "radiat", "left arm", "jaw", "neck", "dizz", "fever"],
    },
    "nausea": {
        "allowed_keywords": ["nausea", "nauseous", "nauseated", "vomit", "vomiting", "sick to your stomach"],
        "disallowed_other_symptoms": ["short of breath", "breathless", "dyspnea", "sweat", "diaphoresis", "radiat", "left arm", "jaw", "neck", "dizz", "fever"],
    },
    "dizziness": {
        "allowed_keywords": ["dizzy", "dizziness", "lightheaded", "lightheadedness", "faint", "fainting", "syncope", "palpitation", "racing heartbeat", "racing heart"],
        "disallowed_other_symptoms": ["short of breath", "breathless", "dyspnea", "sweat", "diaphoresis", "nausea", "vomit", "radiat", "fever"],
    },
    "cough_fever": {
        "allowed_keywords": ["cough", "coughing", "fever", "feverish", "chills", "temperature"],
        "disallowed_other_symptoms": ["sweat", "diaphoresis", "nausea", "vomit", "radiat", "dizz"],
    },
    "pain_character": {
        "allowed_keywords": ["describe the pain", "pain feel like", "character", "quality", "pressure", "sharp", "burning", "squeezing", "crushing", "aching"],
        "disallowed_other_symptoms": ["short of breath", "sweat", "nausea", "vomit", "dizz", "fever"],
    },
    "pain_radiation": {
        "allowed_keywords": ["radiate", "radiating", "spread", "spreading", "move", "moving", "arm", "jaw", "neck", "back", "shoulder"],
        "disallowed_other_symptoms": ["short of breath", "sweat", "nausea", "vomit", "dizz", "fever"],
    },
    "pain_radiation_site": {
        "allowed_keywords": ["where", "spread", "spreading", "radiate", "radiating"],
        "disallowed_other_symptoms": ["short of breath", "sweat", "nausea", "dizz", "fever"],
    },
    "associated_symptoms": {
        "allowed_keywords": ["other symptom", "along with", "associated", "anything else"],
        "disallowed_other_symptoms": [],
    },
    "pain_timing": {
        "allowed_keywords": ["constant", "come and go", "comes and goes", "timing", "pattern"],
        "disallowed_other_symptoms": ["sweat", "nausea", "dizz", "fever"],
    },
    "pain_relieving": {
        "allowed_keywords": ["better", "relieve", "relieves", "go away", "ease"],
        "disallowed_other_symptoms": ["sweat", "nausea", "dizz", "fever"],
    },
    "pain_severity": {
        "allowed_keywords": ["severe", "severity", "scale", "0 to 10", "intense"],
        "disallowed_other_symptoms": ["sweat", "nausea", "dizz", "fever"],
    },
    "exertion": {
        "allowed_keywords": ["exertion", "walking", "physical activity", "exercise", "stairs", "effort", "worse with", "worsen"],
        "disallowed_other_symptoms": ["short of breath", "sweat", "nausea", "vomit", "dizz", "fever"],
    },
}


def strict_json_parse(text: str) -> dict:
    """Parse JSON string strictly, rejecting duplicate keys and nonstandard numeric constants."""
    def pairs_hook(items):
        value = {}
        for k, v in items:
            if k in value:
                raise ValueError(f"Duplicate JSON key: {k}")
            value[k] = v
        return value

    def invalid_constant(_):
        raise ValueError("Nonstandard JSON constant")

    return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=invalid_constant)


def validate_generated_wording(
    raw_content: str,
    candidate_id: str,
    template_question: str,
) -> Tuple[bool, str, str]:
    """Validate LLM-generated wording against deterministic clinical and structural rules.

    Args:
        raw_content: The raw string completion returned by the model.
        candidate_id: The approved clinical candidate ID (e.g., 'dyspnea').
        template_question: The deterministic fallback template question.

    Returns:
        (is_valid: bool, reason: str, question_to_use: str)
        If valid: returns (True, "valid", cleaned_question)
        If invalid: returns (False, failure_reason, template_question)
    """
    clean_cid = (candidate_id or "").strip().lower()

    if not raw_content or not isinstance(raw_content, str) or not raw_content.strip():
        return False, "empty_model_response", template_question

    raw_stripped = raw_content.strip()

    # Reject markdown code fences or backticks
    if "```" in raw_stripped:
        return False, "contains_markdown_code_fences", template_question

    # Parse strict JSON
    try:
        data = strict_json_parse(raw_stripped)
    except Exception as exc:
        return False, f"invalid_json: {exc}", template_question

    if not isinstance(data, dict):
        return False, "json_root_not_object", template_question

    # Must contain "question" key
    if "question" not in data:
        return False, "missing_question_field", template_question

    question_val = data.get("question")
    if not isinstance(question_val, str) or not question_val.strip():
        return False, "blank_question_value", template_question

    question_text = question_val.strip()

    # Length constraints: concise kiosk wording
    if len(question_text) < 5:
        return False, "question_too_short", template_question

    if len(question_text) > 250:
        return False, "question_too_long", template_question

    # Single-question enforcement
    qmark_count = question_text.count("?")
    if qmark_count > 1:
        return False, "multiple_questions_detected", template_question

    # Check for compound sentence asking multiple questions:
    # e.g., "Are you short of breath and are you sweating?"
    if re.search(r"\band\s+(?:are|do|have|is|can|did)\s+you\b", question_text, re.IGNORECASE):
        return False, "compound_multi_question_detected", template_question

    # Check for diagnosis claims/suggestions
    for pat in COMPILED_DIAGNOSIS_RES:
        if pat.search(question_text):
            return False, "diagnosis_language_detected", template_question

    # Check for treatment/medication instructions
    for pat in COMPILED_TREATMENT_RES:
        if pat.search(question_text):
            return False, "treatment_language_detected", template_question

    # Check for AI provenance/guideline mentions
    for pat in COMPILED_AI_RES:
        if pat.search(question_text):
            return False, "ai_provenance_language_detected", template_question

    # Clinical target validation
    q_lower = question_text.lower()
    domain_rules = CANDIDATE_CROSS_DOMAINS.get(clean_cid)

    if domain_rules:
        # 1. Must contain at least one allowed keyword matching the target concept
        has_allowed = any(kw in q_lower for kw in domain_rules["allowed_keywords"])
        if not has_allowed:
            # Fall back check: check against candidate clinical profile semantic keywords
            profile = get_profile(clean_cid)
            if profile and any(k.lower() in q_lower for k in profile.semantic_keywords):
                has_allowed = True

        if not has_allowed:
            return False, f"target_concept_mismatch_for_{clean_cid}", template_question

        # 2. Must NOT contain keywords belonging to other clinical domains (cross-contamination)
        for disallowed in domain_rules["disallowed_other_symptoms"]:
            # Word boundary search for disallowed keywords
            pattern = r"\b" + re.escape(disallowed) + r"\b"
            if re.search(pattern, q_lower):
                return False, f"cross_target_contamination_{disallowed}_in_{clean_cid}", template_question
    else:
        # Generic profile check if not in CANDIDATE_CROSS_DOMAINS
        profile = get_profile(clean_cid)
        if profile:
            has_kw = any(kw.lower() in q_lower for kw in profile.semantic_keywords)
            if not has_kw and profile.target_concepts:
                has_concept = any(c.lower() in q_lower for c in profile.target_concepts)
                if not has_concept:
                    return False, f"target_concept_mismatch_for_{clean_cid}", template_question

    # Ensure clean punctuation: single question mark at end if none
    if not question_text.endswith("?") and not question_text.endswith("."):
        question_text += "?"

    return True, "valid", question_text
