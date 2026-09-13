"""Clinical domain definitions, multi-domain fact extraction, and coverage tracking.

Provides:
- Domain definitions per complaint family (chest_pain, headache, other/general).
- Multi-domain entity and concept extraction from patient answers.
- Domain status (UNANSWERED, PARTIAL, ANSWERED, UNKNOWN, DECLINED).
- Field-to-domain and domain-to-field bidirection mappings.
- Clinical domain tracker maintaining covered, partial, missing required/optional domains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


class DomainStatus(str, Enum):
    UNANSWERED = "UNANSWERED"
    PARTIAL = "PARTIAL"
    ANSWERED = "ANSWERED"
    UNKNOWN = "UNKNOWN"
    DECLINED = "DECLINED"


@dataclass
class DomainFact:
    domain: str
    status: DomainStatus
    evidence: str
    concept: Optional[str] = None
    polarity: str = "present"  # "present" | "absent"
    confidence: float = 1.0
    mapped_fields: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# Domain Definitions per Complaint Family
# ----------------------------------------------------------------------

CHEST_PAIN_DOMAINS = [
    "onset",
    "location",
    "character",
    "severity",
    "radiation",
    "timing",
    "progression",
    "aggravating_factors",
    "relieving_factors",
    "exertional_relationship",
    "respiratory_symptoms",
    "autonomic_symptoms",
    "gastrointestinal_symptoms",
    "previous_episodes",
    "cardiac_risk_history",
    "medication_history",
    "family_history",
]

CHEST_PAIN_REQUIRED_DOMAINS = {
    "onset",
    "location",
    "character",
    "severity",
    "radiation",
    "exertional_relationship",
    "autonomic_symptoms",
}

HEADACHE_DOMAINS = [
    "onset",
    "location",
    "character",
    "severity",
    "timing_duration",
    "triggers_aggravating",
    "relieving_factors",
    "red_flags_neurological",
    "associated_symptoms",
    "previous_history",
    "medication_history",
]

HEADACHE_REQUIRED_DOMAINS = {
    "onset",
    "location",
    "character",
    "severity",
    "red_flags_neurological",
    "associated_symptoms",
}

GENERAL_DOMAINS = [
    "onset_duration",
    "location_site",
    "character_quality",
    "severity_impact",
    "timing_progression",
    "aggravating_relieving",
    "associated_symptoms",
    "chronic_conditions",
    "medications_allergies",
]

GENERAL_REQUIRED_DOMAINS = {
    "onset_duration",
    "severity_impact",
    "timing_progression",
    "chronic_conditions",
}

# ----------------------------------------------------------------------
# Flow Field to Clinical Domain Mapping
# ----------------------------------------------------------------------

FIELD_TO_DOMAIN_MAP: Dict[str, str] = {
    "chief_complaint.description": "chief_complaint",
    "hpi.onset": "onset",
    "hpi.site": "location",
    "hpi.character": "character",
    "hpi.severity": "severity",
    "hpi.radiation": "radiation",
    "hpi.radiation_site": "radiation",
    "hpi.timing": "timing",
    "hpi.progression": "progression",
    "hpi.exacerbating": "aggravating_factors",
    "hpi.provocation": "exertional_relationship",
    "hpi.relieving": "relieving_factors",
    "hpi.associated_details": "autonomic_symptoms",
    "past_medical_history.diabetes": "cardiac_risk_history",
    "past_medical_history.hypertension": "cardiac_risk_history",
    "past_medical_history.cad": "cardiac_risk_history",
    "past_medical_history.other": "cardiac_risk_history",
    "past_medical_history.details": "cardiac_risk_history",
    "past_surgical_history.any": "previous_episodes",
    "past_surgical_history.details": "previous_episodes",
    "medications.any": "medication_history",
    "medications.details": "medication_history",
    "allergies.any": "allergies",
    "allergies.details": "allergies",
    "family_history.any": "family_history",
    "family_history.cad_early": "family_history",
    "personal_history.tobacco": "cardiac_risk_history",
    "personal_history.alcohol": "cardiac_risk_history",
    "personal_history.context": "cardiac_risk_history",
    "review_of_systems.other": "review_of_systems",

    # Headache flow fields
    "hpi.previous": "previous_history",
    "hpi.previous_details": "previous_history",
    "headache.onset": "onset",
    "headache.location": "location",
    "headache.character": "character",
    "headache.severity": "severity",
    "headache.duration": "timing_duration",
    "headache.triggers": "triggers_aggravating",
    "headache.relieving": "relieving_factors",
    "headache.red_flags": "red_flags_neurological",
    "headache.aura": "associated_symptoms",
    "headache.associated": "associated_symptoms",
    "headache.history": "previous_history",

    # Other / General complaint flow fields
    "other.complaint.description": "onset_duration",
    "other.complaint.onset": "onset_duration",
    "other.complaint.severity": "severity_impact",
    "other.complaint.timing": "timing_progression",
    "other.complaint.associated_details": "associated_symptoms",
    "other.complaint.past_medical_history.other": "chronic_conditions",
    "other.complaint.past_medical_history.details": "chronic_conditions",
    "other.complaint.medications.taking_any": "medications_allergies",
    "other.complaint.medications.details": "medications_allergies",
    "other.complaint.allergies.has_any": "medications_allergies",
    "other.complaint.review_of_systems.other_details": "associated_symptoms",
}

# Domain to matching flow fields
DOMAIN_TO_FIELDS_MAP: Dict[str, List[str]] = {}
for _f, _d in FIELD_TO_DOMAIN_MAP.items():
    DOMAIN_TO_FIELDS_MAP.setdefault(_d, []).append(_f)

DOMAIN_ALIASES: Dict[str, List[str]] = {
    "onset": ["onset_duration", "timing_duration"],
    "onset_duration": ["onset", "timing_duration"],
    "location": ["location_site", "site"],
    "site": ["location", "location_site"],
    "location_site": ["location", "site"],
    "character": ["character_quality"],
    "character_quality": ["character"],
    "severity": ["severity_impact"],
    "severity_impact": ["severity"],
    "timing": ["timing_progression", "timing_duration"],
    "timing_progression": ["timing"],
    "timing_duration": ["timing", "onset"],
    "aggravating_factors": ["exertional_relationship", "triggers_aggravating", "aggravating_relieving"],
    "exertional_relationship": ["aggravating_factors", "triggers_aggravating"],
    "triggers_aggravating": ["aggravating_factors", "exertional_relationship"],
    "aggravating_relieving": ["aggravating_factors", "relieving_factors"],
    "relieving_factors": ["aggravating_relieving"],
    "chronic_conditions": ["cardiac_risk_history"],
    "cardiac_risk_history": ["chronic_conditions"],
    "medication_history": ["medications_allergies"],
    "medications_allergies": ["medication_history"],
    "associated_symptoms": ["autonomic_symptoms", "respiratory_symptoms"],
    "autonomic_symptoms": ["associated_symptoms"],
    "respiratory_symptoms": ["associated_symptoms"],
}

# ----------------------------------------------------------------------
# Multi-Domain Linguistic Extraction Patterns
# ----------------------------------------------------------------------

DENIAL_PATTERN = re.compile(
    r"\b(no|not|denies|denied|without|never|none|negative|doesn'?t|don'?t|hasn'?t)\b",
    re.IGNORECASE,
)

DOMAIN_EXTRACTION_RULES = [
    # 1. Onset & Duration
    {
        "domain": "onset",
        "equivalent_domains": ["onset_duration", "timing_duration"],
        "regex": re.compile(
            r"\b(started|began|onset|sudden|suddenly|gradual|gradually|abrupt|abruptly|"
            r"(\d+|half|a|few|several)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months)\s+ago|"
            r"since\s+(\d+|yesterday|morning|last\s+night))\b",
            re.IGNORECASE,
        ),
        "concept": "ONSET",
        "fields": ["hpi.onset", "headache.onset", "other.complaint.onset"],
    },
    # 2. Aggravating / Exertional Context
    {
        "domain": "exertional_relationship",
        "equivalent_domains": ["aggravating_factors", "triggers_aggravating"],
        "regex": re.compile(
            r"\b(walk|walking|exertion|exercise|stair|stairs|running|climbing|physical\s+effort|"
            r"worse\s+with\s+walking|worse\s+on\s+exertion|effort)\b",
            re.IGNORECASE,
        ),
        "concept": "EXERTIONAL_WORSENING",
        "fields": ["hpi.exacerbating", "hpi.provocation"],
    },
    # 3. Radiation
    {
        "domain": "radiation",
        "equivalent_domains": [],
        "regex": re.compile(
            r"\b(spread|spreads|spreading|radiat|radiates|radiating|shoots|shooting|travels|traveling|"
            r"to\s+(my\s+)?(left\s+arm|right\s+arm|both\s+arms|arm|arms|jaw|neck|back|shoulder|teeth))\b",
            re.IGNORECASE,
        ),
        "concept": "RADIATION",
        "fields": ["hpi.radiation", "hpi.radiation_site"],
    },
    # 4. Location / Site
    {
        "domain": "location",
        "equivalent_domains": ["location_site"],
        "regex": re.compile(
            r"\b(middle\s+of\s+(my\s+)?chest|center\s+of\s+(my\s+)?chest|substernal|retrosternal|"
            r"left\s+chest|left\s+side\s+of\s+chest|right\s+chest|behind\s+(the\s+)?breastbone|"
            r"frontal|temporal|occipital|forehead|temple|behind\s+eye|one\s+side\s+of\s+head)\b",
            re.IGNORECASE,
        ),
        "concept": "LOCATION",
        "fields": ["hpi.site", "headache.location"],
    },
    # 5. Character / Quality
    {
        "domain": "character",
        "equivalent_domains": ["character_quality"],
        "regex": re.compile(
            r"\b(pressure|tight|tightness|squeezing|crushing|heaviness|heavy|elephant|sharp|"
            r"stabbing|burning|dull\s+ache|throbbing|pulsing|pounding|band-like)\b",
            re.IGNORECASE,
        ),
        "concept": "PAIN_CHARACTER",
        "fields": ["hpi.character", "headache.character"],
    },
    # 6. Autonomic symptoms: Sweating / Diaphoresis
    {
        "domain": "autonomic_symptoms",
        "equivalent_domains": ["associated_symptoms"],
        "regex": re.compile(
            r"\b(sweat|sweats|sweating|sweaty|diaphoresis|cold\s+sweat|clammy)\b",
            re.IGNORECASE,
        ),
        "concept": "SWEATING",
        "fields": ["hpi.associated_details"],
    },
    # 7. Autonomic symptoms: Nausea / Vomiting
    {
        "domain": "autonomic_symptoms",
        "equivalent_domains": ["associated_symptoms"],
        "regex": re.compile(
            r"\b(nausea|nauseated|nauseous|vomit|vomiting|threw\s+up|puke)\b",
            re.IGNORECASE,
        ),
        "concept": "NAUSEA",
        "fields": ["hpi.associated_details"],
    },
    # 8. Autonomic symptoms: Dizziness / Lightheadedness
    {
        "domain": "autonomic_symptoms",
        "equivalent_domains": ["associated_symptoms"],
        "regex": re.compile(
            r"\b(dizzy|dizziness|lightheaded|lightheadedness|faint|fainting|blackout|syncope|palpitations?)\b",
            re.IGNORECASE,
        ),
        "concept": "DIZZINESS",
        "fields": ["hpi.associated_details"],
    },
    # 9. Respiratory symptoms: Dyspnea / Shortness of breath
    {
        "domain": "respiratory_symptoms",
        "equivalent_domains": ["associated_symptoms"],
        "regex": re.compile(
            r"\b(shortness\s+of\s+breath|breathless|breathlessness|difficulty\s+breathing|"
            r"can'?t\s+breathe|gasping|wheez|wheezing|dyspnea)\b",
            re.IGNORECASE,
        ),
        "concept": "DYSPNEA",
        "fields": ["review_of_systems.other", "hpi.associated_details"],
    },
    # 10. Relieving factors
    {
        "domain": "relieving_factors",
        "equivalent_domains": ["aggravating_relieving"],
        "regex": re.compile(
            r"\b(rest|relieved\s+by\s+rest|better\s+with\s+rest|nitroglycerin|nitro|sitting\s+forward|"
            r"antacid|antacids|dark\s+room|lying\s+down)\b",
            re.IGNORECASE,
        ),
        "concept": "RELIEVING_FACTORS",
        "fields": ["hpi.relieving", "headache.relieving"],
    },
    # 11. Timing / Pattern
    {
        "domain": "timing",
        "equivalent_domains": ["timing_progression", "timing_duration"],
        "regex": re.compile(
            r"\b(constant|continuous|non-stop|never\s+stops|comes\s+and\s+goes|intermittent|"
            r"episodic|waves|comes\s+in\s+waves)\b",
            re.IGNORECASE,
        ),
        "concept": "TIMING",
        "fields": ["hpi.timing", "other.complaint.timing"],
    },
    # 12. Severity
    {
        "domain": "severity",
        "equivalent_domains": ["severity_impact"],
        "regex": re.compile(
            r"\b(\b([0-9]|10)\s*(out\s+of\s+10|/10)\b|severe|extremely\s+severe|mild|moderate|"
            r"worst\s+(pain|headache)\s+of\s+my\s+life|unbearable)\b",
            re.IGNORECASE,
        ),
        "concept": "SEVERITY",
        "fields": ["hpi.severity", "headache.severity", "other.complaint.severity"],
    },
    # 13. Comorbidities: Diabetes
    {
        "domain": "cardiac_risk_history",
        "equivalent_domains": ["chronic_conditions"],
        "regex": re.compile(
            r"\b(diabetes|diabetic|high\s+blood\s+sugar|hyperglycemia|sugar\s+patient|insulin)\b",
            re.IGNORECASE,
        ),
        "concept": "DIABETES",
        "fields": ["past_medical_history.diabetes", "past_medical_history.details"],
    },
    # 14. Comorbidities: Hypertension
    {
        "domain": "cardiac_risk_history",
        "equivalent_domains": ["chronic_conditions"],
        "regex": re.compile(
            r"\b(hypertension|high\s+blood\s+pressure|bp\s+patient|high\s+bp)\b",
            re.IGNORECASE,
        ),
        "concept": "HYPERTENSION",
        "fields": ["past_medical_history.hypertension", "past_medical_history.details"],
    },
    # 15. Comorbidities: Asthma / Respiratory
    {
        "domain": "respiratory_symptoms",
        "equivalent_domains": ["chronic_conditions"],
        "regex": re.compile(
            r"\b(asthma|asthmatic|copd|inhaler|puffer|bronchitis)\b",
            re.IGNORECASE,
        ),
        "concept": "ASTHMA",
        "fields": ["past_medical_history.details"],
    },
    # 16. GI / GERD
    {
        "domain": "gastrointestinal_symptoms",
        "equivalent_domains": ["chronic_conditions", "aggravating_relieving"],
        "regex": re.compile(
            r"\b(gerd|acid\s+reflux|heartburn|indigestion|acidity|sour\s+taste|after\s+eating)\b",
            re.IGNORECASE,
        ),
        "concept": "GERD",
        "fields": ["hpi.associated_details"],
    },
    # 17. Neurological red flags for headache
    {
        "domain": "red_flags_neurological",
        "equivalent_domains": ["associated_symptoms"],
        "regex": re.compile(
            r"\b(thunderclap|explosive|worst\s+headache|stiff\s+neck|neck\s+stiffness|"
            r"focal\s+weakness|numbness|confusion|loss\s+of\s+consciousness|seizure)\b",
            re.IGNORECASE,
        ),
        "concept": "NEUROLOGICAL_RED_FLAG",
        "fields": ["headache.red_flags"],
    },
    # 18. Photophobia / Aura for headache
    {
        "domain": "associated_symptoms",
        "equivalent_domains": [],
        "regex": re.compile(
            r"\b(photophobia|light\s+sensitivity|sensitive\s+to\s+light|noise\s+sensitivity|"
            r"sound\s+sensitivity|visual\s+aura|flashing\s+lights|zigzag\s+lines)\b",
            re.IGNORECASE,
        ),
        "concept": "HEADACHE_AURA",
        "fields": ["headache.aura", "headache.associated"],
    },
]


def extract_domains_and_facts(
    text: str,
    field_context: Optional[str] = None,
    complaint_type: str = "chest_pain",
) -> List[DomainFact]:
    """Extract all clinical domains and facts present in an answer text."""
    if not text or not text.strip():
        return []

    text_clean = text.strip()
    facts: List[DomainFact] = []
    seen_domains: Set[str] = set()

    for rule in DOMAIN_EXTRACTION_RULES:
        match = rule["regex"].search(text_clean)
        if match:
            matched_segment = match.group(0)
            start_idx = max(0, match.start() - 30)
            window = text_clean[start_idx : match.end()]
            polarity = "absent" if DENIAL_PATTERN.search(window) else "present"

            dom = rule["domain"]
            status = DomainStatus.ANSWERED
            if dom == "severity":
                if not re.search(r"\b([0-9]|10)\s*(out\s+of\s+10|/10)\b|worst\s+(pain|headache)\s+of\s+my\s+life", matched_segment, re.I):
                    status = DomainStatus.PARTIAL

            if dom not in seen_domains:
                seen_domains.add(dom)
                facts.append(
                    DomainFact(
                        domain=dom,
                        status=status,
                        evidence=matched_segment,
                        concept=rule["concept"],
                        polarity=polarity,
                        confidence=0.95,
                        mapped_fields=list(rule["fields"]),
                    )
                )

            for eq_dom in rule.get("equivalent_domains", []):
                if eq_dom not in seen_domains:
                    seen_domains.add(eq_dom)
                    facts.append(
                        DomainFact(
                            domain=eq_dom,
                            status=status,
                            evidence=matched_segment,
                            concept=rule["concept"],
                            polarity=polarity,
                            confidence=0.90,
                            mapped_fields=list(rule["fields"]),
                        )
                    )

    if field_context and field_context in FIELD_TO_DOMAIN_MAP:
        assigned_dom = FIELD_TO_DOMAIN_MAP[field_context]
        if assigned_dom not in seen_domains:
            status = DomainStatus.ANSWERED
            if any(k in text_clean.lower() for k in ["unknown", "not sure", "don't know", "unsure"]):
                status = DomainStatus.UNKNOWN
            elif any(k in text_clean.lower() for k in ["decline", "prefer not", "skip"]):
                status = DomainStatus.DECLINED

            facts.append(
                DomainFact(
                    domain=assigned_dom,
                    status=status,
                    evidence=text_clean[:100],
                    concept=None,
                    polarity="present",
                    confidence=1.0,
                    mapped_fields=[field_context],
                )
            )

    return facts


class ClinicalDomainTracker:
    """Tracks covered, partial, and missing domains across an interview."""

    def __init__(self, complaint_type: str = "chest_pain"):
        self.complaint_type = complaint_type
        if complaint_type == "chest_pain":
            self.all_domains = list(CHEST_PAIN_DOMAINS)
            self.required_domains = set(CHEST_PAIN_REQUIRED_DOMAINS)
        elif complaint_type == "headache":
            self.all_domains = list(HEADACHE_DOMAINS)
            self.required_domains = set(HEADACHE_REQUIRED_DOMAINS)
        else:
            self.all_domains = list(GENERAL_DOMAINS)
            self.required_domains = set(GENERAL_REQUIRED_DOMAINS)

        self.covered_domains: Set[str] = set()
        self.partially_covered_domains: Set[str] = set()
        self.answered_fields: Set[str] = set()
        self.answered_qids: Set[str] = set()
        self.known_concepts: Set[str] = set()
        self.facts: List[DomainFact] = []
        self.recent_domains: List[str] = []

    def record_answer(self, question_id: str, field_name: str, raw_value: str) -> List[DomainFact]:
        """Process an answer, update domain coverage, and return newly extracted facts."""
        self.answered_fields.add(field_name)
        self.answered_qids.add(question_id)

        target_dom = FIELD_TO_DOMAIN_MAP.get(field_name)
        if target_dom:
            self.recent_domains.append(target_dom)
            self.covered_domains.add(target_dom)

        extracted = extract_domains_and_facts(raw_value, field_context=field_name, complaint_type=self.complaint_type)
        for f in extracted:
            self.facts.append(f)
            if f.concept:
                self.known_concepts.add(f.concept)
            if f.status == DomainStatus.ANSWERED:
                self.covered_domains.add(f.domain)
                self.partially_covered_domains.discard(f.domain)
                for mapped_field in f.mapped_fields:
                    self.answered_fields.add(mapped_field)
            elif f.status == DomainStatus.PARTIAL:
                if f.domain not in self.covered_domains:
                    self.partially_covered_domains.add(f.domain)

        for d in list(self.covered_domains):
            for alias in DOMAIN_ALIASES.get(d, []):
                self.covered_domains.add(alias)
                self.partially_covered_domains.discard(alias)

        return extracted

    @property
    def missing_required_domains(self) -> List[str]:
        return [d for d in self.all_domains if d in self.required_domains and d not in self.covered_domains]

    @property
    def missing_optional_domains(self) -> List[str]:
        return [d for d in self.all_domains if d not in self.required_domains and d not in self.covered_domains]

    def is_domain_in_cooldown(self, domain: str, cooldown_turns: int = 2) -> bool:
        """Return True if the domain was asked within the last cooldown_turns."""
        if not self.recent_domains:
            return False
        recent = self.recent_domains[-cooldown_turns:]
        return domain in recent

    def consecutive_domain_count(self, domain: str) -> int:
        """Count how many times this domain was asked consecutively at the end."""
        count = 0
        for d in reversed(self.recent_domains):
            if d == domain:
                count += 1
            else:
                break
        return count
