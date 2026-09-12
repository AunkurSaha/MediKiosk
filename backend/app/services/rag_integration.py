"""RAG integration service for generating, deduplicating, and selecting follow-up questions."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import List, Optional, Set, Tuple

from sqlalchemy import select

from app import models
from app.core.config import MAX_RAG_FOLLOWUPS_PER_INTERVIEW
from app.core.errors import ProviderFailure, ProviderUnavailable
from app.database import SessionLocal
from app.schemas.adaptive import RAGSuggestion
from app.schemas.flow import Localized, Question
from app.services import normalization
from app.services.rag import (
    KnowledgeRetrievalService,
    RAGGenerationService,
    _session_scope,
)
from app.services.rag_clinical_mapping import (
    SPECIFIC_DETERMINISTIC_FIELDS,
    get_profile,
)

logger = logging.getLogger(__name__)


def get_rag_suggestions(
    session_id: str,
    db_session_factory=SessionLocal,
    top_k: int = 6,
    min_similarity: Optional[float] = None,
) -> List[dict]:
    """Generate RAG-based follow-up question suggestions for a session."""
    try:
        with _session_scope(db_session_factory) as db:
            normalized = normalization.for_answers(db, session_id)
        if not normalized:
            return []

        query_parts = []
        for _, value in normalized.items():
            if value and getattr(value, "original_text", None):
                query_parts.append(f"{value.canonical_field}: {value.original_text}")
        query_text = ". ".join(query_parts) if query_parts else ""
        if not query_text:
            return []

        retrieval_service = KnowledgeRetrievalService(db_session_factory)
        retrieved = asyncio.run(
            retrieval_service.retrieve(
                query_text=query_text,
                topic=None,
                language="en",
                top_k=top_k,
                min_similarity=min_similarity,
            )
        )

        generation_service = RAGGenerationService()
        suggestions = generation_service.suggest_questions(
            structured_facts=normalized,
            retrieved_chunks=retrieved,
        )
        return suggestions
    except (ProviderUnavailable, ProviderFailure):
        return []
    except Exception:
        return []


def get_used_rag_records(db, session_id: str) -> List[dict]:
    """Retrieve all previously answered RAG questions for this session from InterviewAnswer."""
    rows = db.scalars(
        select(models.InterviewAnswer)
        .where(models.InterviewAnswer.session_id == session_id)
        .order_by(models.InterviewAnswer.created_at, models.InterviewAnswer.id)
    ).all()
    records = []
    for r in rows:
        if r.question_id.startswith("rag_followup"):
            cid = r.question_id.removeprefix("rag_followup.")
            records.append({
                "question_id": r.question_id,
                "candidate_id": cid,
                "field": r.field,
                "raw_value": r.raw_value or "",
            })
    return records


def get_known_clinical_context(db, session_id: str) -> dict:
    """Extract known clinical fields, concepts, used candidate IDs, and answer texts for deduplication."""
    rows = db.scalars(
        select(models.InterviewAnswer)
        .where(models.InterviewAnswer.session_id == session_id)
    ).all()

    answered_fields = {r.field for r in rows}
    answered_qids = {r.question_id for r in rows}
    raw_answer_texts = [r.raw_value.lower() for r in rows if r.raw_value]

    used_records = get_used_rag_records(db, session_id)
    used_candidate_ids = {rec["candidate_id"] for rec in used_records}

    known_present_concepts: Set[str] = set()
    known_absent_concepts: Set[str] = set()
    known_concepts: Set[str] = set()

    # 1. Extract normalized concepts from normalization service
    try:
        norm_map = normalization.for_answers(db, session_id)
        for norm in norm_map.values():
            if norm and getattr(norm, "status", None) == "normalized":
                for f in norm.facts:
                    concept_name = f.normalized_concept.upper()
                    if getattr(f, "polarity", "present") == "absent":
                        known_absent_concepts.add(concept_name)
                        known_concepts.add(concept_name)
                    else:
                        known_present_concepts.add(concept_name)
                        known_concepts.add(concept_name)
    except Exception:
        pass

    # 2. Extract concepts directly from structured interview answers
    for r in rows:
        q_or_f = (r.field or "") + " " + (r.question_id or "")
        val_lower = (r.raw_value or "").lower()

        # Exacerbating / provocation -> exertional worsening
        if "hpi.exacerbating" in q_or_f or "hpi.provocation" in q_or_f:
            known_concepts.add("EXERTION")
            known_concepts.add("EXERTIONAL_WORSENING")
            if any(term in val_lower for term in ["walking", "exertion", "stairs", "exercise", "physical", "effort"]):
                known_present_concepts.add("EXERTION")
                known_present_concepts.add("EXERTIONAL_WORSENING")
            elif any(term in val_lower for term in ["none", "nothing", "no", "never", "rest"]):
                known_absent_concepts.add("EXERTION")
                known_absent_concepts.add("EXERTIONAL_WORSENING")

        # Pain character
        if "hpi.character" in q_or_f:
            if "pressure" in val_lower:
                known_present_concepts.add("PRESSURE_LIKE_PAIN")
                known_concepts.add("PRESSURE_LIKE_PAIN")
            elif "sharp" in val_lower:
                known_present_concepts.add("SHARP_PAIN")
                known_concepts.add("SHARP_PAIN")
            elif "burn" in val_lower:
                known_present_concepts.add("BURNING_PAIN")
                known_concepts.add("BURNING_PAIN")

        # Radiation
        if "hpi.radiation" in q_or_f:
            if val_lower in ("false", "no", "none", "denies") or val_lower.startswith("false"):
                known_absent_concepts.add("RADIATION")
                known_concepts.add("RADIATION")
            elif val_lower in ("true", "yes") or "arm" in val_lower or "jaw" in val_lower or "back" in val_lower:
                known_present_concepts.add("RADIATION")
                known_concepts.add("RADIATION")

    # 3. Direct raw keyword and regex fallbacks across all answer texts (present vs denied)
    denial_re = re.compile(r"\b(no|not|denies|denied|without|never|none)\b", re.IGNORECASE)
    for txt in raw_answer_texts:
        # Dyspnea
        if any(term in txt for term in ["shortness of breath", "breathless", "difficulty breathing", "dyspnea"]):
            if denial_re.search(txt):
                known_absent_concepts.add("DYSPNEA")
                known_concepts.add("DYSPNEA")
            else:
                known_present_concepts.add("DYSPNEA")
                known_concepts.add("DYSPNEA")

        # Sweating / Diaphoresis
        if any(term in txt for term in ["sweat", "diaphoresis"]):
            if denial_re.search(txt):
                known_absent_concepts.add("SWEATING")
                known_concepts.add("SWEATING")
            else:
                known_present_concepts.add("SWEATING")
                known_concepts.add("SWEATING")

        # Nausea / Vomiting
        if any(term in txt for term in ["nausea", "vomit"]):
            if denial_re.search(txt):
                known_absent_concepts.add("NAUSEA")
                known_absent_concepts.add("VOMITING")
                known_concepts.add("NAUSEA")
                known_concepts.add("VOMITING")
            else:
                known_present_concepts.add("NAUSEA")
                known_present_concepts.add("VOMITING")
                known_concepts.add("NAUSEA")
                known_concepts.add("VOMITING")

        # Dizziness / Palpitations
        if any(term in txt for term in ["dizz", "lighthead", "palpitation", "syncope"]):
            if denial_re.search(txt):
                known_absent_concepts.add("DIZZINESS")
                known_concepts.add("DIZZINESS")
            else:
                known_present_concepts.add("DIZZINESS")
                known_concepts.add("DIZZINESS")

        # Cough / Fever
        if "cough" in txt:
            known_concepts.add("COUGH")
            if denial_re.search(txt):
                known_absent_concepts.add("COUGH")
            else:
                known_present_concepts.add("COUGH")
        if "fever" in txt:
            known_concepts.add("FEVER")
            if denial_re.search(txt):
                known_absent_concepts.add("FEVER")
            else:
                known_present_concepts.add("FEVER")

    return {
        "answered_fields": answered_fields,
        "answered_qids": answered_qids,
        "raw_answer_texts": raw_answer_texts,
        "used_candidate_ids": used_candidate_ids,
        "known_concepts": known_concepts,
        "known_present_concepts": known_present_concepts,
        "known_absent_concepts": known_absent_concepts,
        "used_records": used_records,
    }


def is_candidate_redundant(
    candidate: dict,
    context: dict,
) -> Tuple[bool, str]:
    """Determine if a RAG question candidate is invalid, redundant, or already addressed.

    Returns:
        (is_redundant, reason)
    """
    text = (candidate.get("question") or "").strip()
    # Reject blank / empty / whitespace-only question text
    if not text:
        return True, "empty_question_text"

    # Reject ungrounded candidate
    chunk_ids = candidate.get("source_chunk_ids") or []
    if not chunk_ids:
        return True, "ungrounded_candidate"

    cid = (candidate.get("candidate_id") or "").strip().lower()
    used_candidate_ids = context["used_candidate_ids"]
    if cid and cid in used_candidate_ids:
        return True, f"candidate_id_{cid}_already_asked"

    profile = get_profile(cid)
    canonical_target_field = (
        profile.canonical_target_field
        if profile
        else (candidate.get("target_field") or "")
    ).strip().lower()

    equivalent_fields = set(
        profile.equivalent_fields if profile else candidate.get("equivalent_fields", [])
    )
    target_concepts = set(
        profile.target_concepts if profile else candidate.get("target_concepts", [])
    )
    if cand_concept := candidate.get("concept"):
        target_concepts.add(cand_concept.upper())

    answered_fields = context["answered_fields"]
    known_concepts = context["known_concepts"]
    known_present_concepts = context["known_present_concepts"]
    known_absent_concepts = context["known_absent_concepts"]
    raw_texts = context["raw_answer_texts"]
    text_lower = text.lower()

    # 1. Target field deduplication against specific deterministic fields
    if (
        canonical_target_field in SPECIFIC_DETERMINISTIC_FIELDS
        and canonical_target_field in answered_fields
    ):
        return True, f"target_field_{canonical_target_field}_already_answered"

    # 2. Equivalent deterministic field deduplication
    for eq_f in equivalent_fields:
        if eq_f in answered_fields:
            return True, f"equivalent_field_{eq_f}_already_answered"

    # 3. Clinical concept deduplication (both positive and negative facts)
    for c in target_concepts:
        if c in known_present_concepts:
            return True, f"concept_{c}_already_known_present"
        if c in known_absent_concepts:
            return True, f"concept_{c}_already_known_absent"
        if c in known_concepts:
            return True, f"concept_{c}_already_known"

    # 4. Semantic keyword and text fallback checks
    # Exertion / Provocation
    if (
        cid == "exertion"
        or canonical_target_field in ("hpi.exacerbating", "hpi.provocation")
        or any(k in text_lower for k in ["exertion", "walking", "physical activity"])
    ):
        if "hpi.exacerbating" in answered_fields or "hpi.provocation" in answered_fields:
            return True, "exertion_already_answered"
        if "EXERTION" in known_concepts or "EXERTIONAL_WORSENING" in known_concepts:
            return True, "exertion_already_known"

    # Pain character / quality
    if (
        cid == "pain_character"
        or canonical_target_field == "hpi.character"
        or any(k in text_lower for k in ["describe the pain", "pain feel like", "sharp, burning", "quality and pattern of pain"])
    ):
        if "hpi.character" in answered_fields or any(
            c in known_concepts for c in ["PRESSURE_LIKE_PAIN", "SHARP_PAIN", "BURNING_PAIN"]
        ):
            return True, "pain_character_already_collected"

    # Pain radiation
    if (
        cid == "pain_radiation"
        or canonical_target_field == "hpi.radiation"
        or any(k in text_lower for k in ["spread", "radiat"])
    ):
        if "hpi.radiation" in answered_fields or "hpi.radiation_site" in answered_fields or "RADIATION" in known_concepts:
            return True, "pain_radiation_already_collected"

    # Pain site
    if canonical_target_field == "hpi.site" or "where exactly is the pain" in text_lower:
        if "hpi.site" in answered_fields:
            return True, "pain_site_already_collected"

    # Pain onset
    if canonical_target_field == "hpi.onset" or "when did the chest pain start" in text_lower:
        if "hpi.onset" in answered_fields:
            return True, "pain_onset_already_collected"

    # Pain severity
    if canonical_target_field == "hpi.severity" or "scale of 0-10" in text_lower:
        if "hpi.severity" in answered_fields:
            return True, "pain_severity_already_collected"

    # Pain timing
    if canonical_target_field == "hpi.timing" or "constant or intermittent" in text_lower:
        if "hpi.timing" in answered_fields:
            return True, "pain_timing_already_collected"

    # Pain relieving
    if canonical_target_field == "hpi.relieving" or "makes the pain better" in text_lower:
        if "hpi.relieving" in answered_fields:
            return True, "pain_relieving_already_collected"

    # Dyspnea
    if (
        cid == "dyspnea"
        or "DYSPNEA" in target_concepts
        or any(k in text_lower for k in ["shortness of breath", "breathless", "difficulty breathing", "dyspnea"])
    ):
        if "DYSPNEA" in known_concepts:
            return True, "dyspnea_already_known"
        if any("shortness of breath" in t or "breathless" in t or "difficulty breathing" in t or "dyspnea" in t for t in raw_texts):
            return True, "dyspnea_already_reported"

    # Sweating
    if (
        cid == "sweating"
        or "SWEATING" in target_concepts
        or any(k in text_lower for k in ["sweating", "diaphoresis", "sweat"])
    ):
        if "SWEATING" in known_concepts or "DIAPHORESIS" in known_concepts:
            return True, "sweating_already_known"
        if any("sweat" in t or "diaphoresis" in t for t in raw_texts):
            return True, "sweating_already_reported"

    # Nausea
    if (
        cid == "nausea"
        or "NAUSEA" in target_concepts
        or any(k in text_lower for k in ["nausea", "vomit"])
    ):
        if "NAUSEA" in known_concepts or "VOMITING" in known_concepts:
            return True, "nausea_already_known"
        if any("nausea" in t or "vomit" in t for t in raw_texts):
            return True, "nausea_already_reported"

    # Dizziness
    if (
        cid == "dizziness"
        or "DIZZINESS" in target_concepts
        or any(k in text_lower for k in ["dizz", "lighthead", "palpitation", "syncope"])
    ):
        if "DIZZINESS" in known_concepts or "SYNCOPE" in known_concepts:
            return True, "dizziness_already_known"
        if any("dizz" in t or "lighthead" in t or "palpitation" in t or "syncope" in t for t in raw_texts):
            return True, "dizziness_already_reported"

    # Cough / Fever
    if (
        cid == "cough_fever"
        or ("COUGH" in target_concepts and "FEVER" in target_concepts)
        or ("cough" in text_lower and "fever" in text_lower)
    ):
        if "COUGH" in known_concepts and "FEVER" in known_concepts:
            return True, "cough_fever_already_known"

    return False, "valid"


def select_next_rag_question(
    session_id: str,
    db,
    flow,
    current_res,
) -> Optional[Tuple[Question, RAGSuggestion]]:
    """Rank, validate, and select the next grounded RAG follow-up question.

    Respects RAG follow-up budget, clinical field deduplication, grounding,
    and returns None if budget is exhausted or no valid candidates remain.
    """
    context = get_known_clinical_context(db, session_id)
    used_records = context["used_records"]

    # Budget enforcement
    if len(used_records) >= MAX_RAG_FOLLOWUPS_PER_INTERVIEW:
        return None

    # Retrieve candidate suggestions
    candidates = get_rag_suggestions(session_id, db_session_factory=lambda: db, top_k=6)
    if not candidates:
        return None

    for cand in candidates:
        is_red, reason = is_candidate_redundant(cand, context)
        cid = cand.get("candidate_id") or "q1"
        clean_cid = re.sub(r"[^a-z0-9_.]", "_", cid.lower())
        profile = get_profile(clean_cid)

        target_field = (
            profile.canonical_target_field
            if profile
            else (cand.get("target_field") or "hpi.associated_details")
        )
        storage_field = (
            profile.storage_field
            if profile
            else (cand.get("storage_field") or "hpi.associated_details")
        )

        if is_red:
            logger.info(
                "RAG candidate rejected: id=%s, target_field=%s, reason=%s",
                clean_cid,
                target_field,
                reason,
            )
            continue

        logger.info(
            "RAG candidate accepted: id=%s, target_field=%s",
            clean_cid,
            target_field,
        )

        # Candidate passed all checks!
        question_id = f"rag_followup.{clean_cid}"
        clean_storage_field = re.sub(r"[^a-z0-9_.]", "_", storage_field.lower())
        clean_target_field = re.sub(r"[^a-z0-9_.]", "_", target_field.lower())
        question_text = cand["question"].strip()

        # Build schema-compliant Question and RAGSuggestion
        rag_question = Question(
            question_id=question_id,
            field=clean_storage_field,
            type="short_text",
            required=False,
            allow_unknown=True,
            text=Localized(en=question_text, bn=question_text, hi=question_text),
            options=[],
            depends_on=[],
            when=[],
        )

        rag_suggestion = RAGSuggestion(
            question=question_text,
            reason=cand.get("reason", "Follow-up question suggested by clinical guidance."),
            source_chunk_ids=cand.get("source_chunk_ids", []),
            origin="rag",
            candidate_id=clean_cid,
            target_field=clean_target_field,
            similarity_score=cand.get("similarity_score"),
            source_title=cand.get("source_title"),
            source_section=cand.get("source_section"),
        )

        return rag_question, rag_suggestion

    return None