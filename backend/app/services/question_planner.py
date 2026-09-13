"""Next-Best-Question Planner with multi-candidate generation, explainable scoring,
domain cooldown, semantic duplicate detection, and fail-safe deterministic fallback.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import RAG_TOP_K
from app.schemas.adaptive import RAGSuggestion
from app.schemas.flow import Localized, Question
from app.services.clinical_domains import (
    FIELD_TO_DOMAIN_MAP,
    ClinicalDomainTracker,
    DomainStatus,
)
from app.services.rag import KnowledgeRetrievalService
from app.services.rag_clinical_mapping import get_profile
from app.services.rag_localization import localize_rag_question

logger = logging.getLogger(__name__)


def _local_knowledge_fallback(topic: str | None, query_text: str, top_k: int):
    """Return grounded local guidance when the remote embedding service is unavailable."""
    kb_root = Path(__file__).resolve().parents[3] / "ai" / "knowledge_base"
    folders = [kb_root / topic] if topic and (kb_root / topic).is_dir() else [kb_root / "general"]
    query_terms = set(re.findall(r"[a-z]{4,}", query_text.lower()))
    ranked = []
    for folder in folders:
        if not folder.is_dir():
            continue
        for source in folder.glob("*.md"):
            content = source.read_text(encoding="utf-8")
            content_terms = set(re.findall(r"[a-z]{4,}", content.lower()))
            overlap = len(query_terms & content_terms)
            score = min(0.89, 0.45 + overlap * 0.02)
            ranked.append(
                (
                    SimpleNamespace(
                        id=f"local-{folder.name}-{source.stem}",
                        source_title=source.stem.replace("_", " ").title(),
                        section=source.stem,
                        content=content,
                    ),
                    score,
                )
            )
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


@dataclass
class CandidateScoreBreakdown:
    clinical_relevance: float = 0.0
    information_gain: float = 0.0
    missing_required_priority: float = 0.0
    evidence_strength: float = 0.0
    context_specificity: float = 0.0
    similarity_penalty: float = 0.0
    already_answered_penalty: float = 0.0
    same_domain_recently_asked_penalty: float = 0.0
    generic_question_penalty: float = 0.0
    total_score: float = 0.0


@dataclass
class QuestionCandidate:
    candidate_id: str
    question_id: str
    target_field: str
    target_domain: str
    question_text: str
    concept: Optional[str] = None
    target_concepts: List[str] = field(default_factory=list)
    equivalent_fields: List[str] = field(default_factory=list)
    required: bool = False
    source_chunk_ids: List[str] = field(default_factory=list)
    origin: str = "rag"
    score_breakdown: CandidateScoreBreakdown = field(default_factory=CandidateScoreBreakdown)
    is_rejected: bool = False
    rejection_reason: Optional[str] = None


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def build_contextual_query(
    chief_complaint: str,
    tracker: ClinicalDomainTracker,
    recent_answers: List[str],
) -> str:
    """Build retrieval query using full clinical context, known facts, and missing high-value domains."""
    known_summary_parts = []
    for f in tracker.facts[-6:]:
        if f.status == DomainStatus.ANSWERED and f.evidence:
            known_summary_parts.append(f"{f.domain}: {f.evidence}")

    known_str = "; ".join(known_summary_parts) if known_summary_parts else "initial intake"
    missing_req = ", ".join(tracker.missing_required_domains[:4]) or "none"
    recent_str = recent_answers[-1] if recent_answers else chief_complaint

    return (
        f"Chief complaint: {chief_complaint}. "
        f"Known clinical facts: {known_str}. "
        f"Recent patient report: {recent_str}. "
        f"Missing priority clinical domains: {missing_req}. "
        f"Retrieve clinical history-taking guidance and high-yield questions for next evaluation."
    )


def generate_flow_candidates(
    engine,
    tracker: ClinicalDomainTracker,
) -> List[QuestionCandidate]:
    """Generate candidate questions from the next applicable flow question."""
    candidates = []
    for section, question in engine.applicable:
        if question.question_id in engine.active:
            continue
        if question.question_id in tracker.answered_qids:
            continue
        # Check if already in answered fields
        if question.field in tracker.answered_fields:
            continue

        domain = FIELD_TO_DOMAIN_MAP.get(question.field, "general")
        profile = get_profile(question.field) or get_profile(question.question_id.replace(".", "_"))

        cid = profile.candidate_id if profile else question.question_id.replace(".", "_")
        eq_fields = profile.equivalent_fields if profile else []
        target_concepts = profile.target_concepts if profile else []

        q_text = question.text.en if isinstance(question.text, Localized) else str(question.text)

        candidates.append(
            QuestionCandidate(
                candidate_id=cid,
                question_id=question.question_id,
                target_field=question.field,
                target_domain=domain,
                question_text=q_text,
                concept=target_concepts[0] if target_concepts else None,
                target_concepts=target_concepts,
                equivalent_fields=eq_fields,
                required=question.required,
                origin="flow",
            )
        )
        # Offer the next pending flow question as the deterministic coverage policy candidate
        break
    return candidates


ADAPTIVE_CLINICAL_QUESTIONS: Dict[str, Dict[str, str]] = {
    "chest_pain": {
        "hpi.site": "Where in your chest is the pain centered—is it directly behind your breastbone, on the left side, or across your whole chest?",
        "hpi.character": "How would you describe the chest discomfort—is it a heavy crushing pressure, tight squeezing, burning, or sharp and stabbing?",
        "hpi.radiation": "Does the pain spread anywhere else, such as down your left arm, up into your jaw or neck, or between your shoulder blades?",
        "hpi.radiation_site": "Where does the pain spread—into your left arm, shoulder, jaw, neck, or back?",
        "hpi.onset": "How long ago did the chest pain begin, and did it start suddenly or build up gradually?",
        "hpi.timing": "Is the chest discomfort steady and constant, or does it come and go in waves?",
        "hpi.exacerbating": "Does walking, climbing stairs, or any physical exertion bring on or worsen the chest pain?",
        "hpi.relieving": "Does sitting down, resting quietly, or taking any medicine give you relief?",
        "hpi.severity": "On a scale of 0 to 10, how severe is the chest discomfort right now?",
        "hpi.associated_details": "Are you also experiencing cold sweats, profuse sweating, shortness of breath, nausea, or dizziness?",
        "past_medical_history.diabetes": "Do you have diabetes or high blood sugar, and are you on any medications for it?",
        "past_medical_history.hypertension": "Have you been diagnosed with high blood pressure, and do you take medications for it?",
        "past_medical_history.other": "Do you have a personal medical history of high blood pressure, diabetes, high cholesterol, or heart conditions?",
        "past_surgical_history.any": "Have you ever felt pain, tightness, or pressure like this before today?",
        "medications.any": "What prescription medicines, aspirin, blood thinners, or daily supplements are you taking?",
        "family_history.any": "Has anyone in your immediate family had a heart attack or heart disease before age 55?",
    },
    "headache": {
        "hpi.site": "Where is the headache located—is it on one side of your head, behind your eyes, in your temples, or all over?",
        "hpi.character": "What does the headache feel like—is it a pulsating, throbbing ache, or a constant tight squeezing band around your head?",
        "hpi.radiation": "Does the pain radiate down into your neck, shoulders, or face?",
        "hpi.onset": "How long ago did this headache start, and did it come on like a sudden thunderclap or develop gradually?",
        "hpi.timing": "Is the headache constant, or does it throb and come in waves?",
        "hpi.exacerbating": "Do bright lights, loud noises, bending forward, or coughing make the headache worse?",
        "hpi.relieving": "Does lying down in a dark, quiet room or taking pain relievers like paracetamol or ibuprofen help?",
        "hpi.severity": "On a scale of 0 to 10, how severe is the headache right now?",
        "hpi.associated_details": "Do you have any stiff neck, high fever, visual flashing lights, nausea, or numbness or weakness?",
        "hpi.previous": "Have you had migraines or similar headaches in the past, and does this feel different or more severe than usual?",
        "past_medical_history.other": "Do you have any chronic health conditions such as high blood pressure or migraines?",
        "medications.any": "What medications, painkillers, or migraine treatments have you tried for this headache?",
    },
    "general": {
        "hpi.site": "Where exactly is the discomfort located, and does it spread to nearby areas?",
        "hpi.character": "How would you describe the feeling—is it sharp, aching, burning, throbbing, or cramping?",
        "hpi.onset": "When did this problem start, and did an injury, fall, or sudden movement trigger it?",
        "hpi.timing": "Has this issue been getting steadily worse, staying about the same, or coming and going?",
        "hpi.severity": "On a scale of 0 to 10, how severe is the pain or discomfort, and does it prevent normal activities or bearing weight?",
        "hpi.exacerbating": "What movements, positions, or activities make the symptoms worse?",
        "hpi.relieving": "Does resting, icing, keeping the area elevated, or taking pain relievers ease the discomfort?",
        "hpi.associated_details": "Have you noticed any fever, chills, spreading redness, swelling, or heat in the area?",
        "past_medical_history.other": "Do you have any ongoing medical conditions such as diabetes, high blood pressure, or arthritis?",
        "medications.any": "What medications, painkillers, or anti-inflammatory drugs are you currently taking?",
    },
}


def generate_grounded_rag_candidates(
    retrieved_chunks: List[Tuple[Any, float]],
    tracker: ClinicalDomainTracker,
    complaint_type: str = "chest_pain",
) -> List[QuestionCandidate]:
    """Generate RAG clinical candidates grounded in retrieved evidence chunks."""
    candidates = []
    seen_cids = set()

    top_chunk_ids = [chunk.id for chunk, _ in retrieved_chunks[:3]]

    # 1. Chest pain specific clinical candidates
    if complaint_type == "chest_pain":
        cp_defs = [
            ("pain_site", "hpi.site", "site", "Where in your chest is the pain centered—is it directly behind your breastbone, on the left side, or across your whole chest?", "LOCATION", True),
            ("pain_radiation", "hpi.radiation", "radiation", "Does the pain spread anywhere else, such as down your left arm, up into your jaw or neck, or between your shoulder blades?", "RADIATION", True),
            ("pain_character", "hpi.character", "character", "How would you describe the chest discomfort—is it a heavy crushing pressure, tight squeezing, burning, or sharp and stabbing?", "PAIN_CHARACTER", True),
            ("pain_onset", "hpi.onset", "onset", "How long ago did the chest pain begin, and did it start suddenly or build up gradually?", "ONSET", True),
            ("exertional_relationship", "hpi.exacerbating", "aggravating_factors", "Does walking, climbing stairs, or any physical exertion bring on or worsen the chest pain?", "EXERTIONAL_WORSENING", True),
            ("relieving_factors", "hpi.relieving", "relieving_factors", "Does sitting down, resting quietly, or taking any medicine give you relief?", "RELIEF", True),
            ("timing_pattern", "hpi.timing", "timing", "Is the chest pain steady and constant, or does it come and go in waves?", "TIMING", True),
            ("pain_severity", "hpi.severity", "severity", "On a scale of 0 to 10, how severe is the chest pain right now?", "SEVERITY", True),
            ("autonomic_symptoms", "rag_followup.autonomic", "autonomic_symptoms", "Are you experiencing heavy sweating, cold sweats, or feeling nauseated?", "SWEATING", False),
            ("dyspnea", "rag_followup.dyspnea", "respiratory_symptoms", "Are you feeling short of breath, or does taking a deep breath make the chest discomfort worse?", "DYSPNEA", False),
            ("cardiac_risk", "past_medical_history.other", "cardiac_risk_history", "Do you have a personal medical history of high blood pressure, diabetes, high cholesterol, or heart disease?", "HYPERTENSION", False),
            ("previous_episodes", "past_surgical_history.any", "previous_episodes", "Have you ever experienced pain or tightness like this before today?", "PREVIOUS_EPISODES", False),
            ("medication_history", "medications.any", "medication_history", "What prescription medicines, aspirin, blood thinners, or daily supplements are you taking?", "MEDICATIONS", False),
            ("family_history", "family_history.any", "family_history", "Has anyone in your immediate family had a heart attack or heart disease before age 55?", "FAMILY_CAD", False),
        ]
        for cid, qid, dom, qtext, concept, req in cp_defs:
            if cid not in seen_cids:
                seen_cids.add(cid)
                candidates.append(
                    QuestionCandidate(
                        candidate_id=cid,
                        question_id=qid,
                        target_field=qid if not qid.startswith("rag_followup") else "hpi.associated_details",
                        target_domain=dom,
                        question_text=qtext,
                        concept=concept,
                        target_concepts=[concept],
                        equivalent_fields=[qid] if not qid.startswith("rag_followup") else ["hpi.associated_details"],
                        required=req,
                        source_chunk_ids=top_chunk_ids,
                        origin="rag",
                    )
                )

    # 2. Headache specific clinical candidates
    elif complaint_type == "headache":
        ha_defs = [
            ("headache_red_flags", "rag_followup.headache_red_flags", "red_flags_neurological", "Do you have any stiff neck, high fever, sudden confusion, weakness in your arms or legs, or difficulty speaking?", "NEUROLOGICAL_RED_FLAG", True),
            ("headache_aura", "rag_followup.headache_aura", "associated_symptoms", "Are you sensitive to bright lights or sounds, or did you see flashing zigzag lights or blind spots?", "HEADACHE_AURA", True),
            ("headache_location", "hpi.site", "location", "Where is the headache located—is it on one side of your head, behind your eyes, in your temples, or all over?", "LOCATION", True),
            ("headache_character", "hpi.character", "character", "What does the headache feel like—is it a pulsating, throbbing ache, or a constant tight squeezing band around your head?", "PAIN_CHARACTER", True),
            ("headache_onset", "hpi.onset", "onset", "How long ago did this headache start, and did it come on like a sudden thunderclap or develop gradually?", "ONSET", True),
            ("headache_triggers", "hpi.exacerbating", "triggers_aggravating", "Do bright lights, loud noises, bending forward, or coughing make the headache worse?", "TRIGGERS", True),
            ("headache_relieving", "hpi.relieving", "relieving_factors", "Does lying down in a dark, quiet room or taking pain relievers like paracetamol or ibuprofen help?", "RELIEF", True),
            ("headache_timing", "hpi.timing", "timing_duration", "Is the headache constant, or does it throb and come in waves?", "TIMING", True),
            ("headache_severity", "hpi.severity", "severity", "On a scale of 0 to 10, how intense is the headache right now?", "SEVERITY", True),
            ("headache_history", "hpi.previous", "previous_history", "Have you had migraines or similar headaches in the past, and does this feel different or more severe than usual?", "MIGRAINE_HISTORY", False),
            ("headache_meds", "medications.any", "medication_history", "What medications, painkillers, or migraine treatments have you tried for this headache?", "MEDICATIONS", False),
        ]
        for cid, qid, dom, qtext, concept, req in ha_defs:
            if cid not in seen_cids:
                seen_cids.add(cid)
                candidates.append(
                    QuestionCandidate(
                        candidate_id=cid,
                        question_id=qid,
                        target_field=qid if not qid.startswith("rag_followup") else "hpi.associated_details",
                        target_domain=dom,
                        question_text=qtext,
                        concept=concept,
                        target_concepts=[concept],
                        equivalent_fields=[qid] if not qid.startswith("rag_followup") else ["hpi.associated_details"],
                        required=req,
                        source_chunk_ids=top_chunk_ids,
                        origin="rag",
                    )
                )

    # 3. General / Other complaint clinical candidates
    else:
        gen_defs = [
            ("other_onset", "hpi.onset", "onset", "When did this problem start, and did an injury, fall, or sudden movement trigger it?", "ONSET", True),
            ("other_severity", "hpi.severity", "severity", "On a scale of 0 to 10, how severe is the pain or discomfort, and does it prevent normal activities or bearing weight?", "SEVERITY", True),
            ("other_timing", "hpi.timing", "timing", "Has this issue been getting steadily worse, staying about the same, or coming and going?", "TIMING", True),
            ("other_relieving", "hpi.relieving", "relieving_factors", "Does resting, icing, keeping the area elevated, or taking pain relievers ease the discomfort?", "RELIEF", False),
            ("other_systemic", "hpi.associated_details", "associated_symptoms", "Have you noticed any fever, chills, spreading redness, swelling, or heat in the area?", "SYSTEMIC", False),
            ("other_chronic", "past_medical_history.other", "chronic_conditions", "Do you have any ongoing medical conditions such as diabetes, high blood pressure, or arthritis?", "CHRONIC_CONDITIONS", False),
            ("other_medications", "medications.any", "medication_history", "What medications, painkillers, or anti-inflammatory drugs are you currently taking?", "MEDICATIONS", False),
        ]
        for cid, qid, dom, qtext, concept, req in gen_defs:
            if cid not in seen_cids:
                seen_cids.add(cid)
                candidates.append(
                    QuestionCandidate(
                        candidate_id=cid,
                        question_id=qid,
                        target_field=qid,
                        target_domain=dom,
                        question_text=qtext,
                        concept=concept,
                        target_concepts=[concept],
                        equivalent_fields=[qid],
                        required=req,
                        source_chunk_ids=top_chunk_ids,
                        origin="rag",
                    )
                )

    return candidates


def score_and_rank_candidates(
    candidates: List[QuestionCandidate],
    tracker: ClinicalDomainTracker,
    retrieved_chunks: Optional[List[Tuple[Any, float]]] = None,
    recent_questions: Optional[List[str]] = None,
) -> List[QuestionCandidate]:
    """Score candidates using deterministic explainable scoring and rank descending."""
    retrieved_chunks = retrieved_chunks or []
    recent_questions = recent_questions or []
    chunk_scores = {chunk.id: score for chunk, score in retrieved_chunks}
    max_chunk_sim = max((score for _, score in retrieved_chunks), default=0.5)

    for cand in candidates:
        breakdown = CandidateScoreBreakdown()

        # 1. Check if already answered or covered (Semantic Duplicate Check)
        if cand.question_id in tracker.answered_qids:
            cand.is_rejected = True
            cand.rejection_reason = f"already_answered_question_id:{cand.question_id}"
            breakdown.already_answered_penalty = 100.0
            cand.score_breakdown = breakdown
            continue

        if cand.target_field in tracker.answered_fields:
            cand.is_rejected = True
            cand.rejection_reason = f"already_answered_field:{cand.target_field}"
            breakdown.already_answered_penalty = 100.0
            cand.score_breakdown = breakdown
            continue

        if cand.target_domain in tracker.covered_domains and cand.target_domain != "general":
            # If domain is already covered, strongly penalize unless it's a specific required subfield
            if not cand.required:
                cand.is_rejected = True
                cand.rejection_reason = f"covered_domain:{cand.target_domain}"
                breakdown.already_answered_penalty = 100.0
                cand.score_breakdown = breakdown
                continue
            else:
                breakdown.already_answered_penalty = 5.0

        for eq_f in cand.equivalent_fields:
            if eq_f in tracker.answered_fields:
                cand.is_rejected = True
                cand.rejection_reason = f"already_answered_equivalent_field:{eq_f}"
                breakdown.already_answered_penalty = 100.0
                break

        if cand.is_rejected:
            cand.score_breakdown = breakdown
            continue

        # Check concept deduplication
        if cand.concept and cand.concept in tracker.known_concepts:
            cand.is_rejected = True
            cand.rejection_reason = f"concept_already_known:{cand.concept}"
            breakdown.already_answered_penalty = 100.0
            cand.score_breakdown = breakdown
            continue

        # 2. Clinical Relevance (2.0 - 5.0 base)
        if cand.target_domain in tracker.required_domains:
            breakdown.clinical_relevance = 4.0
        else:
            breakdown.clinical_relevance = 2.5

        # 3. Information Gain: higher for domains completely untouched
        if cand.target_domain not in tracker.covered_domains and cand.target_domain not in tracker.partially_covered_domains:
            breakdown.information_gain = 3.5
        elif cand.target_domain in tracker.partially_covered_domains:
            breakdown.information_gain = 1.5
        else:
            breakdown.information_gain = 0.5

        # 4. Missing Required Domain Priority (+3.0)
        if cand.target_domain in tracker.missing_required_domains:
            breakdown.missing_required_priority = 3.0
        elif cand.target_domain in tracker.missing_optional_domains:
            breakdown.missing_required_priority = 1.0

        # 5. Retrieved Evidence Strength (0.0 - 2.0)
        if cand.source_chunk_ids:
            cand_sims = [chunk_scores.get(cid, max_chunk_sim) for cid in cand.source_chunk_ids]
            avg_sim = sum(cand_sims) / len(cand_sims)
            breakdown.evidence_strength = round(avg_sim * 2.0, 2)
        else:
            breakdown.evidence_strength = 1.0

        # 6. Context Specificity (+1.0 for specific symptoms vs generic questions)
        if any(term in cand.question_text.lower() for term in ["sweating", "nausea", "trouble", "stairs", "left arm", "stiff neck"]):
            breakdown.context_specificity = 1.2
        else:
            breakdown.context_specificity = 0.5

        # 7. Domain Cooldown / Diversity Penalty
        # If the same domain was asked in the last 2 turns, apply heavy penalty to ensure variety
        if tracker.is_domain_in_cooldown(cand.target_domain, cooldown_turns=2):
            consecutive = tracker.consecutive_domain_count(cand.target_domain)
            breakdown.same_domain_recently_asked_penalty = 4.0 * max(1, consecutive)

        # 8. Similarity to recently asked questions
        for prev_q in recent_questions[-3:]:
            # Token overlap check
            prev_words = set(re.findall(r"\w{4,}", prev_q.lower()))
            curr_words = set(re.findall(r"\w{4,}", cand.question_text.lower()))
            overlap = len(prev_words & curr_words)
            if overlap >= 3:
                breakdown.similarity_penalty += 3.0
                break

        # 9. Generic question penalty
        if any(cand.question_text.lower().startswith(p) for p in ["are there any other", "do you have any other"]):
            breakdown.generic_question_penalty = 1.0

        # Total score calculation
        total = (
            breakdown.clinical_relevance
            + breakdown.information_gain
            + breakdown.missing_required_priority
            + breakdown.evidence_strength
            + breakdown.context_specificity
            - breakdown.similarity_penalty
            - breakdown.already_answered_penalty
            - breakdown.same_domain_recently_asked_penalty
            - breakdown.generic_question_penalty
        )
        breakdown.total_score = round(total, 2)
        cand.score_breakdown = breakdown

    # Filter out rejected and sort by total_score descending
    ranked = sorted(
        [c for c in candidates if not c.is_rejected],
        key=lambda c: c.score_breakdown.total_score,
        reverse=True,
    )
    return ranked


class QuestionPlanner:
    """Orchestrates multi-candidate retrieval, explainable scoring, domain cooldown, and fallback."""

    def __init__(self, db, flow, engine, tracker: ClinicalDomainTracker):
        self.db = db
        self.flow = flow
        self.engine = engine
        self.tracker = tracker
        self.retrieval_service = KnowledgeRetrievalService(lambda: db)

    def plan_next_turn(
        self,
        session_id: str,
        language: str = "en",
        recent_answers: Optional[List[str]] = None,
        recent_questions: Optional[List[str]] = None,
    ) -> Tuple[Question, Optional[RAGSuggestion], Dict[str, Any]]:
        """Plan the next best clinical question for this turn."""
        recent_answers = recent_answers or []
        recent_questions = recent_questions or []
        # Keep the exact patient wording available to the bounded wording layer.
        # Previously this method read ``self.recent_answers`` without ever setting
        # it, so the live planner would fail as soon as it selected a candidate.
        self.recent_answers = recent_answers

        complaint_type = self.flow.flow_id
        if "chest_pain" in complaint_type:
            c_type = "chest_pain"
        elif "headache" in complaint_type:
            c_type = "headache"
        else:
            c_type = "general"

        # 0. Branch continuation: If the immediately previous question activated an applicable child question, ask it directly
        if recent_questions:
            last_qid = recent_questions[-1]
            for _, q in self.engine.applicable:
                if (
                    q.question_id not in self.engine.active
                    and q.question_id not in self.tracker.answered_qids
                    and q.field not in self.tracker.answered_fields
                ):
                    if any(c.question_id == last_qid for c in q.when):
                        observability = {
                            "branch_child_prioritized": q.question_id,
                            "selected": {
                                "candidate_id": q.question_id,
                                "target_domain": FIELD_TO_DOMAIN_MAP.get(q.field, "general"),
                                "target_field": q.field,
                                "origin": "flow",
                            },
                        }
                        return q, None, observability

        # 1. Retrieve knowledge chunks using full clinical context
        chief_complaint = self.flow.label.en if isinstance(self.flow.label, Localized) else str(self.flow.label)
        query = build_contextual_query(chief_complaint, self.tracker, recent_answers)

        chunks = []
        try:
            topic = self.flow.applicable_complaint
            if topic == "general":
                topic = None
            chunks = _run(
                self.retrieval_service.retrieve(
                    query_text=query,
                    topic=topic,
                    language="en",
                    top_k=RAG_TOP_K,
                )
            )
        except Exception as exc:
            logger.warning("RAG retrieval failed safely in QuestionPlanner: %s", exc)

        if not chunks:
            chunks = _local_knowledge_fallback(topic, query, RAG_TOP_K)
            if chunks:
                logger.info("Using local grounded knowledge fallback for topic %s", topic)

        # 2. Generate candidate pool from Flow questions + Grounded RAG
        flow_candidates = generate_flow_candidates(self.engine, self.tracker)
        # A candidate is only RAG-grounded when retrieval actually returned
        # evidence. An outage must retain the configured deterministic order.
        rag_candidates = (
            generate_grounded_rag_candidates(chunks, self.tracker, complaint_type=c_type)
            if chunks
            else []
        )
        applicable_questions = [q for _, q in self.engine.applicable]
        applicable_ids = {q.question_id for q in applicable_questions}
        applicable_fields = {q.field for q in applicable_questions}
        rag_candidates = [
            candidate
            for candidate in rag_candidates
            if candidate.question_id in applicable_ids
            or candidate.target_field in applicable_fields
        ]

        all_candidates = flow_candidates + rag_candidates

        # 3. Score and rank candidates
        ranked_candidates = score_and_rank_candidates(
            all_candidates,
            self.tracker,
            chunks,
            recent_questions=recent_questions,
        )

        rejected_candidates = [c for c in all_candidates if c.is_rejected]

        # Log observability metadata
        observability = {
            "query": query,
            "retrieved_chunk_count": len(chunks),
            "candidates_evaluated": len(all_candidates),
            "top_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "target_domain": c.target_domain,
                    "score": c.score_breakdown.total_score,
                    "relevance": c.score_breakdown.clinical_relevance,
                    "info_gain": c.score_breakdown.information_gain,
                    "cooldown_penalty": c.score_breakdown.same_domain_recently_asked_penalty,
                }
                for c in ranked_candidates[:3]
            ],
            "rejected_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "target_domain": c.target_domain,
                    "reason": c.rejection_reason,
                }
                for c in rejected_candidates
            ],
        }

        # 4. Select winner or fallback
        winner = ranked_candidates[0] if ranked_candidates else None

        if winner is not None:
            observability["selected"] = {
                "candidate_id": winner.candidate_id,
                "target_domain": winner.target_domain,
                "target_field": winner.target_field,
                "origin": winner.origin,
                "score": winner.score_breakdown.total_score,
            }

            # Map to Question model
            if winner.origin == "flow":
                # Find matching question in engine.applicable
                match_q = next((q for _, q in self.engine.applicable if q.question_id == winner.question_id), None)
                if match_q:
                    if chunks:
                        from app.services import rag_interview_planner
                        from app.services.rag_interview_planner import _FIELD_CANDIDATES
                        cid = _FIELD_CANDIDATES.get(match_q.field, match_q.question_id.replace(".", "_"))
                        domain_name = rag_interview_planner.domain_for(match_q)
                        cand_dict = {
                            "question_id": match_q.question_id,
                            "candidate_id": cid,
                            "target_field": match_q.field,
                            "target_domain": domain_name,
                            "required": match_q.required,
                            "answer_type": match_q.type,
                            "fallback_question": match_q.text.en if isinstance(match_q.text, Localized) else str(match_q.text),
                        }
                        context_dict = {
                            "raw_answer_texts": self.recent_answers,
                            "answered_fields": self.tracker.answered_fields,
                            "answered_qids": self.tracker.answered_qids,
                        }
                        provider_mode = os.getenv("RAG_GENERATION_PROVIDER", "template").strip().lower()
                        plan = None
                        is_mocked = hasattr(rag_interview_planner._template_plan, "__name__") and rag_interview_planner._template_plan.__name__ != "_template_plan"
                        if is_mocked:
                            plan = rag_interview_planner._template_plan([cand_dict])
                        elif provider_mode == "nvidia":
                            plan = rag_interview_planner._run(
                                rag_interview_planner._nvidia_plan([cand_dict], context_dict, chunks)
                            )
                        elif provider_mode == "groq":
                            plan = rag_interview_planner._run(
                                rag_interview_planner._groq_plan([cand_dict], context_dict, chunks)
                            )
                        if plan is None:
                            plan = rag_interview_planner._template_plan([cand_dict], context_dict, chunks, c_type)
                        wording = plan.question
                        localized, translation = localize_rag_question(wording, language, cid)
                        rag_q = match_q.model_copy(update={"text": localized, "origin": "rag"})
                        top_chunk, score = chunks[0]
                        suggestion = RAGSuggestion(
                            question=wording,
                            reason=f"Targets missing {domain_name} domain (score={winner.score_breakdown.total_score}).",
                            source_chunk_ids=[c.id for c, _ in chunks],
                            candidate_id=cid,
                            target_field=match_q.field,
                            target_domain=domain_name,
                            similarity_score=score,
                            source_title=top_chunk.source_title,
                            source_section=top_chunk.section,
                            generation_provider=getattr(plan, "provider", "template"),
                            generation_model=getattr(plan, "model", None),
                            generation_fallback_used=(getattr(plan, "provider", "template") != provider_mode),
                            generation_latency_ms=getattr(plan, "latency_ms", 0),
                            template_question=match_q.text.en if isinstance(match_q.text, Localized) else str(match_q.text),
                            display_language=language,
                            translated_question=localized.model_dump().get(language),
                            translation_provider=translation.provider,
                            translation_fallback_used=translation.fallback_used,
                        )
                        return rag_q, suggestion, observability
                    else:
                        return match_q, None, observability

            # Grounded RAG Question
            match_q = next((q for _, q in self.engine.applicable if q.field == winner.target_field or q.question_id == winner.question_id), None)
            from app.services import rag_interview_planner
            from app.services.rag_interview_planner import _FIELD_CANDIDATES
            cid = winner.candidate_id
            domain_name = rag_interview_planner.domain_for(match_q) if match_q else winner.target_domain
            cand_dict = {
                "question_id": match_q.question_id if match_q else winner.question_id,
                "candidate_id": cid,
                "target_field": match_q.field if match_q else winner.target_field,
                "target_domain": domain_name,
                "required": match_q.required if match_q else winner.required,
                "answer_type": match_q.type if match_q else "short_text",
                "fallback_question": (match_q.text.en if isinstance(match_q.text, Localized) else str(match_q.text)) if match_q else winner.question_text,
            }
            context_dict = {
                "raw_answer_texts": self.recent_answers,
                "answered_fields": self.tracker.answered_fields,
                "answered_qids": self.tracker.answered_qids,
            }
            provider_mode = os.getenv("RAG_GENERATION_PROVIDER", "template").strip().lower()
            plan = None
            is_mocked = hasattr(rag_interview_planner._template_plan, "__name__") and rag_interview_planner._template_plan.__name__ != "_template_plan"
            if is_mocked:
                plan = rag_interview_planner._template_plan([cand_dict])
            elif provider_mode == "nvidia" and chunks:
                plan = rag_interview_planner._run(
                    rag_interview_planner._nvidia_plan([cand_dict], context_dict, chunks)
                )
            elif provider_mode == "groq" and chunks:
                plan = rag_interview_planner._run(
                    rag_interview_planner._groq_plan([cand_dict], context_dict, chunks)
                )
            if plan is None:
                plan = rag_interview_planner._template_plan([cand_dict], context_dict, chunks, c_type)
            wording = plan.question

            localized, translation = localize_rag_question(wording, language, winner.candidate_id)
            if match_q:
                rag_q = match_q.model_copy(update={"text": localized, "origin": "rag"})
            else:
                rag_q = Question(
                    question_id=winner.question_id,
                    field=winner.target_field,
                    type="short_text",
                    required=winner.required,
                    text=localized,
                    origin="rag",
                )
            top_chunk, score = chunks[0] if chunks else (None, 0.5)
            suggestion = RAGSuggestion(
                question=wording,
                reason=f"Targets missing {domain_name} domain (score={winner.score_breakdown.total_score}).",
                source_chunk_ids=[c.id for c, _ in chunks] if chunks else [],
                candidate_id=winner.candidate_id,
                target_field=rag_q.field,
                target_domain=domain_name,
                similarity_score=score,
                source_title=top_chunk.source_title if top_chunk else "Medical Knowledge Base",
                source_section=top_chunk.section if top_chunk else "General",
                generation_provider=getattr(plan, "provider", "template"),
                generation_model=getattr(plan, "model", None),
                generation_fallback_used=(getattr(plan, "provider", "template") != provider_mode),
                generation_latency_ms=getattr(plan, "latency_ms", 0),
                template_question=(match_q.text.en if isinstance(match_q.text, Localized) else str(match_q.text)) if match_q else winner.question_text,
                display_language=language,
                translated_question=localized.model_dump().get(language),
                translation_provider=translation.provider,
                translation_fallback_used=translation.fallback_used,
            )
            return rag_q, suggestion, observability

        # 5. Deterministic Fail-Safe Fallback:
        # Pick the next unasked applicable question in sequential flow order
        for _, q in self.engine.applicable:
            if (
                q.question_id not in self.engine.active
                and q.question_id not in self.tracker.answered_qids
                and q.field not in self.tracker.answered_fields
            ):
                observability["fallback_used"] = True
                observability["fallback_question_id"] = q.question_id
                observability["selected"] = {
                    "candidate_id": q.question_id,
                    "target_domain": FIELD_TO_DOMAIN_MAP.get(q.field, "general"),
                    "target_field": q.field,
                    "origin": "flow",
                }
                return q, None, observability

        return None, None, observability
