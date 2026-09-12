"""Centralized clinical ontology and information-need mapping for RAG candidates.

Provides canonical mappings between RAG candidates, clinical target fields,
storage persistence fields, equivalent deterministic flow fields, normalized
clinical concepts, and semantic keywords.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CandidateClinicalProfile(BaseModel):
    candidate_id: str
    canonical_target_field: str
    storage_field: str = "hpi.associated_details"
    target_concepts: List[str] = Field(default_factory=list)
    equivalent_fields: List[str] = Field(default_factory=list)
    semantic_keywords: List[str] = Field(default_factory=list)
    default_question: str
    default_reason: str
    default_knowledge_source: str


# Specific deterministic fields whose completion directly satisfies that clinical information need
SPECIFIC_DETERMINISTIC_FIELDS = frozenset({
    "chief_complaint.description",
    "hpi.site",
    "hpi.onset",
    "hpi.character",
    "hpi.radiation",
    "hpi.radiation_site",
    "hpi.timing",
    "hpi.exacerbating",
    "hpi.relieving",
    "hpi.severity",
})


# Canonical registry of clinical candidate profiles for chest pain
CHEST_PAIN_PROFILES: Dict[str, CandidateClinicalProfile] = {
    "pain_character": CandidateClinicalProfile(
        candidate_id="pain_character",
        canonical_target_field="hpi.character",
        storage_field="hpi.associated_details",
        target_concepts=["PRESSURE_LIKE_PAIN", "SHARP_PAIN", "BURNING_PAIN"],
        equivalent_fields=["hpi.character"],
        semantic_keywords=[
            "describe the pain",
            "pain feel like",
            "sharp, burning",
            "quality and pattern of pain",
            "pressure-like",
            "sharp",
            "burning",
            "crushing",
        ],
        default_question="Can you describe the pain in more detail?",
        default_reason="Understanding the quality and pattern of chest discomfort.",
        default_knowledge_source="chest_pain-history_taking-001",
    ),
    "pain_radiation": CandidateClinicalProfile(
        candidate_id="pain_radiation",
        canonical_target_field="hpi.radiation",
        storage_field="hpi.associated_details",
        target_concepts=["RADIATION"],
        equivalent_fields=["hpi.radiation", "hpi.radiation_site"],
        semantic_keywords=["spread", "radiat", "jaw", "neck", "back", "left arm", "arm"],
        default_question="Does the pain radiate to your jaw, neck, back, or left arm?",
        default_reason="Radiation pattern is an important diagnostic indicator in chest pain.",
        default_knowledge_source="chest_pain-history_taking-002",
    ),
    "exertion": CandidateClinicalProfile(
        candidate_id="exertion",
        canonical_target_field="hpi.exacerbating",
        storage_field="hpi.associated_details",
        target_concepts=["EXERTION", "EXERTIONAL_WORSENING"],
        equivalent_fields=["hpi.exacerbating", "hpi.provocation", "hpi.activity"],
        semantic_keywords=[
            "exertion",
            "walking",
            "physical activity",
            "stairs",
            "exercise",
            "effort",
            "worse with walking",
        ],
        default_question="Does the pain worsen with exertion, walking, or physical activity?",
        default_reason="Exertional worsening helps differentiate cardiac ischemic pain from other etiologies.",
        default_knowledge_source="chest_pain-history_taking-002",
    ),
    "dyspnea": CandidateClinicalProfile(
        candidate_id="dyspnea",
        canonical_target_field="hpi.associated_details",
        storage_field="hpi.associated_details",
        target_concepts=["DYSPNEA"],
        equivalent_fields=[],
        semantic_keywords=[
            "shortness of breath",
            "breathless",
            "difficulty breathing",
            "dyspnea",
            "breath",
        ],
        default_question="Are you experiencing any shortness of breath or difficulty breathing?",
        default_reason="Shortness of breath is an important associated symptom to evaluate in chest pain.",
        default_knowledge_source="chest_pain-associated_symptoms-001",
    ),
    "sweating": CandidateClinicalProfile(
        candidate_id="sweating",
        canonical_target_field="hpi.associated_details",
        storage_field="hpi.associated_details",
        target_concepts=["SWEATING", "DIAPHORESIS"],
        equivalent_fields=[],
        semantic_keywords=["diaphoresis", "sweating", "sweat", "cold sweat", "heavy sweat"],
        default_question="Have you experienced heavy sweating or cold sweats along with the chest pain?",
        default_reason="Sweating (diaphoresis) is an important autonomic sign in acute chest pain assessment.",
        default_knowledge_source="chest_pain-associated_symptoms-001",
    ),
    "nausea": CandidateClinicalProfile(
        candidate_id="nausea",
        canonical_target_field="hpi.associated_details",
        storage_field="hpi.associated_details",
        target_concepts=["NAUSEA", "VOMITING"],
        equivalent_fields=[],
        semantic_keywords=["nausea", "vomiting", "vomit", "sick to stomach"],
        default_question="Have you had any nausea or vomiting accompanying the chest discomfort?",
        default_reason="Nausea is a recognized associated autonomic symptom in cardiac chest pain presentations.",
        default_knowledge_source="chest_pain-associated_symptoms-001",
    ),
    "dizziness": CandidateClinicalProfile(
        candidate_id="dizziness",
        canonical_target_field="hpi.associated_details",
        storage_field="hpi.associated_details",
        target_concepts=["DIZZINESS", "SYNCOPE", "PALPITATIONS"],
        equivalent_fields=[],
        semantic_keywords=[
            "dizziness",
            "lightheadedness",
            "lightheaded",
            "palpitations",
            "syncope",
            "faint",
            "racing heartbeat",
        ],
        default_question="Have you felt dizzy, lightheaded, or noticed a racing heartbeat?",
        default_reason="Dizziness and palpitations help assess hemodynamic impact or arrhythmias.",
        default_knowledge_source="chest_pain-associated_symptoms-001",
    ),
    "cough_fever": CandidateClinicalProfile(
        candidate_id="cough_fever",
        canonical_target_field="hpi.associated_details",
        storage_field="hpi.associated_details",
        target_concepts=["COUGH", "FEVER"],
        equivalent_fields=[],
        semantic_keywords=["cough", "fever", "chills", "phlegm", "sputum"],
        default_question="Have you had a cough, fever, or abdominal pain alongside the chest discomfort?",
        default_reason="Cough and fever help evaluate non-cardiac pulmonary or infectious causes.",
        default_knowledge_source="chest_pain-associated_symptoms-002",
    ),
    "pain_site": CandidateClinicalProfile(
        candidate_id="pain_site",
        canonical_target_field="hpi.site",
        storage_field="hpi.site",
        target_concepts=["CHEST_PAIN"],
        equivalent_fields=["hpi.site"],
        semantic_keywords=["where exactly is the pain", "location of pain", "site of pain"],
        default_question="Where exactly in the chest is the pain located?",
        default_reason="Pain location helps localize potential etiologies.",
        default_knowledge_source="chest_pain-history_taking-001",
    ),
    "pain_onset": CandidateClinicalProfile(
        candidate_id="pain_onset",
        canonical_target_field="hpi.onset",
        storage_field="hpi.onset",
        target_concepts=[],
        equivalent_fields=["hpi.onset"],
        semantic_keywords=["when did the pain start", "how long ago", "onset of pain"],
        default_question="How long ago did the pain begin?",
        default_reason="Onset duration is essential for triage acuity.",
        default_knowledge_source="chest_pain-history_taking-001",
    ),
    "pain_timing": CandidateClinicalProfile(
        candidate_id="pain_timing",
        canonical_target_field="hpi.timing",
        storage_field="hpi.timing",
        target_concepts=[],
        equivalent_fields=["hpi.timing"],
        semantic_keywords=["constant or intermittent", "come and go", "comes and goes"],
        default_question="Is the pain constant or does it come and go?",
        default_reason="Temporal pattern helps distinguish ischemic from episodic pain.",
        default_knowledge_source="chest_pain-history_taking-001",
    ),
    "pain_relieving": CandidateClinicalProfile(
        candidate_id="pain_relieving",
        canonical_target_field="hpi.relieving",
        storage_field="hpi.relieving",
        target_concepts=[],
        equivalent_fields=["hpi.relieving"],
        semantic_keywords=["makes the pain better", "relieves the pain", "rest", "nitroglycerin"],
        default_question="What makes the pain better or go away, if anything?",
        default_reason="Relieving factors help assess response to rest or medications.",
        default_knowledge_source="chest_pain-history_taking-002",
    ),
    "pain_severity": CandidateClinicalProfile(
        candidate_id="pain_severity",
        canonical_target_field="hpi.severity",
        storage_field="hpi.severity",
        target_concepts=[],
        equivalent_fields=["hpi.severity"],
        semantic_keywords=["scale of 0-10", "severity of pain", "how severe"],
        default_question="How severe is the pain on a scale from 0 to 10?",
        default_reason="Severity assessment aids in tracking and risk stratification.",
        default_knowledge_source="chest_pain-history_taking-001",
    ),
}


def get_profile(candidate_id: str) -> Optional[CandidateClinicalProfile]:
    """Retrieve clinical profile by candidate_id."""
    if not candidate_id:
        return None
    return CHEST_PAIN_PROFILES.get(candidate_id.strip().lower())
