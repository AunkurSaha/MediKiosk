"""Grounded per-turn interview planning over deterministic clinical coverage.

The flow remains the authority for fields, types, branching, required coverage,
and completion.  This module may select only an unanswered applicable flow
question and may change only its patient-facing wording.  Any failure returns
``None`` so the caller can use the configured deterministic question.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx2 as httpx

from app.core.config import RAG_GENERATION_MAX_TOKENS, RAG_TOP_K
from app.schemas.adaptive import RAGSuggestion
from app.schemas.flow import Question
from app.services.rag import KnowledgeRetrievalService
from app.services.rag_clinical_mapping import CHEST_PAIN_PROFILES
from app.services.rag_localization import localize_rag_question
from app.services.rag_wording_provider import NvidiaWordingSettings
from app.services.rag_wording_validator import strict_json_parse, validate_generated_wording

logger = logging.getLogger(__name__)

_PLAN_CACHE: dict[tuple[str, int, str], tuple[Question, RAGSuggestion]] = {}

_FIELD_CANDIDATES = {
    profile.canonical_target_field: profile.candidate_id
    for profile in CHEST_PAIN_PROFILES.values()
}
_FIELD_CANDIDATES["hpi.associated_details"] = "associated_symptoms"
_FIELD_CANDIDATES["hpi.radiation_site"] = "pain_radiation_site"

_DOMAIN_NAMES = {
    "hpi.onset": "onset",
    "hpi.site": "site",
    "hpi.character": "character",
    "hpi.radiation": "radiation",
    "hpi.radiation_site": "radiation destination",
    "hpi.associated_details": "associated symptoms",
    "hpi.timing": "timing and pattern",
    "hpi.exacerbating": "aggravating factors",
    "hpi.relieving": "relieving factors",
    "hpi.severity": "severity",
}

_DOMAIN_GROUNDING_TERMS = {
    "onset": ("onset", "start", "begin", "duration"),
    "site": ("site", "location", "where", "central", "chest"),
    "character": ("character", "quality", "pressure", "sharp", "burning"),
    "radiation": ("radiat", "spread", "arm", "jaw", "back"),
    "radiation destination": ("radiat", "spread", "arm", "jaw", "back"),
    "associated symptoms": ("associated", "symptom", "breath", "sweat", "nausea"),
    "timing and pattern": ("timing", "pattern", "constant", "intermittent"),
    "aggravating factors": ("aggravat", "worse", "exertion", "walking"),
    "relieving factors": ("reliev", "better", "rest"),
    "severity": ("severity", "scale", "severe", "intensity"),
}


@dataclass(frozen=True)
class PlannedWording:
    question_id: str
    target_field: str
    target_domain: str
    question: str
    provider: str
    model: str | None
    latency_ms: int


def clear_plan_cache(session_id: str | None = None) -> None:
    if session_id is None:
        _PLAN_CACHE.clear()
        return
    for key in [key for key in _PLAN_CACHE if key[0] == session_id]:
        _PLAN_CACHE.pop(key, None)


def domain_for(question: Question) -> str:
    return _DOMAIN_NAMES.get(question.field, question.field.replace("_", " ").replace(".", " / "))


def coverage_domains(engine) -> tuple[list[str], list[str], list[str]]:
    covered = [domain_for(q) for _, q in engine.applicable if q.question_id in engine.active]
    required = [
        domain_for(q)
        for _, q in engine.applicable
        if q.required and q.question_id not in engine.active
    ]
    optional = [
        domain_for(q)
        for _, q in engine.applicable
        if not q.required and q.question_id not in engine.active
    ]
    return list(dict.fromkeys(covered)), list(dict.fromkeys(required)), list(dict.fromkeys(optional))


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _candidate(question: Question) -> dict[str, Any]:
    return {
        "question_id": question.question_id,
        "candidate_id": _FIELD_CANDIDATES.get(
            question.field, question.question_id.replace(".", "_")
        ),
        "target_field": question.field,
        "target_domain": domain_for(question),
        "required": question.required,
        "answer_type": question.type,
        "fallback_question": question.text.en,
    }


def _is_grounded(candidate: dict, chunks: list[tuple[Any, float]]) -> bool:
    source_text = " ".join(chunk.content.lower() for chunk, _ in chunks)
    terms = _DOMAIN_GROUNDING_TERMS.get(candidate["target_domain"])
    if terms is None:
        terms = tuple(
            token.lower().strip("?,.")
            for token in candidate["fallback_question"].split()
            if len(token.strip("?,.")) >= 6
        )
    return any(term in source_text for term in terms)


def _is_redundant(candidate: dict, context: dict, covered_domains: set[str]) -> bool:
    if candidate["target_field"] in context.get("answered_fields", set()):
        return True
    if candidate["target_domain"] in covered_domains:
        return True
    if candidate["candidate_id"] in context.get("used_candidate_ids", set()):
        return True
    profile = CHEST_PAIN_PROFILES.get(candidate["candidate_id"])
    if profile is None:
        return False
    if set(profile.equivalent_fields) & set(context.get("answered_fields", set())):
        return True
    # Canonical flow fields still require their own typed value. Concepts extracted
    # from a broader free-text answer may prevent a synonymous optional follow-up,
    # but must not silently satisfy a required typed field.
    return False


def _safe_facts(context: dict) -> str:
    # Clinical answers only; never names, phone numbers, session IDs, or document text.
    texts = [text.strip()[:120] for text in context.get("raw_answer_texts", []) if text.strip()]
    return "; ".join(texts[:4]) or "No additional clinical facts collected yet"


def _build_query(flow, context: dict, candidates: list[dict]) -> str:
    missing = ", ".join(f"{c['target_domain']} ({c['target_field']})" for c in candidates)
    answered = ", ".join(sorted(context.get("answered_fields", set()))) or "none"
    return (
        f"Chief complaint: {flow.label.en}. Known patient-reported facts: {_safe_facts(context)}. "
        f"Answered fields: {answered}. Missing clinical coverage domains: {missing}. "
        "Select the next most relevant history question."
    )


def _template_plan(candidates: list[dict]) -> PlannedWording:
    selected = candidates[0]
    return PlannedWording(
        question_id=selected["question_id"],
        target_field=selected["target_field"],
        target_domain=selected["target_domain"],
        question=selected["fallback_question"],
        provider="template",
        model=None,
        latency_ms=0,
    )


async def _nvidia_plan(
    candidates: list[dict], context: dict, chunks: list[tuple[Any, float]]
) -> PlannedWording | None:
    settings = NvidiaWordingSettings.from_environment()
    if not settings.api_key.get_secret_value():
        return None
    sources = [
        {
            "chunk_id": chunk.id,
            "title": chunk.source_title,
            "section": chunk.section,
            "content": chunk.content[:280],
        }
        for chunk, _ in chunks
    ]
    system = (
        "You plan exactly one patient-friendly clinical history question. Choose only one item "
        "from missing_candidates, keep its question_id, target_field and target_domain unchanged, "
        "and word one short neutral question grounded in retrieved_sources. Do not diagnose, infer "
        "a diagnosis, recommend treatment or medication, mention sources/AI, or combine domains. "
        "Return strict JSON only with keys question_id,target_field,target_domain,question."
    )
    user = json.dumps(
        {
            "known_patient_reported_facts": _safe_facts(context),
            "answered_fields": sorted(context.get("answered_fields", set())),
            "previous_question_ids": sorted(context.get("answered_qids", set())),
            "covered_domains": sorted(
                domain_for_question
                for field in context.get("answered_fields", set())
                if (domain_for_question := _DOMAIN_NAMES.get(field))
            ),
            "missing_candidates": candidates,
            "retrieved_sources": sources,
        },
        ensure_ascii=False,
    )
    started = perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=settings.timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{settings.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": settings.temperature,
                    "max_tokens": max(RAG_GENERATION_MAX_TOKENS, 160),
                    "stream": False,
                },
            )
        if response.status_code != 200:
            logger.warning("RAG interview planning returned HTTP %s", response.status_code)
            return None
        choices = response.json().get("choices") or []
        raw = ((choices[0].get("message") or {}).get("content") if choices else None)
        data = strict_json_parse(raw.strip()) if isinstance(raw, str) else None
    except Exception as exc:
        logger.warning("RAG interview planning failed safely: %s", type(exc).__name__)
        return None
    if not isinstance(data, dict) or set(data) != {
        "question_id", "target_field", "target_domain", "question"
    }:
        return None
    selected = next((c for c in candidates if c["question_id"] == data["question_id"]), None)
    if selected is None or data["target_field"] != selected["target_field"] or data[
        "target_domain"
    ] != selected["target_domain"]:
        return None
    raw_question = json.dumps({"question": data["question"]}, ensure_ascii=False)
    valid, _, wording = validate_generated_wording(
        raw_question, selected["candidate_id"], selected["fallback_question"]
    )
    if not valid:
        return None
    return PlannedWording(
        question_id=selected["question_id"],
        target_field=selected["target_field"],
        target_domain=selected["target_domain"],
        question=wording,
        provider="nvidia",
        model=settings.model,
        latency_ms=round((perf_counter() - started) * 1000),
    )


def plan_next_question(session_id: str, revision: int, language: str, db, flow, engine, context):
    """Return one grounded RAG question or ``None`` for deterministic fallback."""
    cache_key = (session_id, revision, language)
    if cache_key in _PLAN_CACHE:
        return _PLAN_CACHE[cache_key]

    pending = [(section, q) for section, q in engine.applicable if q.question_id in engine.pending]
    if not pending or pending[0][1].question_id == "chief_complaint.description":
        return None

    # Keep selection inside the current clinical section so configured coverage order remains coherent.
    section_id = pending[0][0].section_id
    eligible = [q for section, q in pending if section.section_id == section_id][:4]
    candidates = [_candidate(q) for q in eligible]
    covered, _, _ = coverage_domains(engine)
    candidates = [
        candidate
        for candidate in candidates
        if not _is_redundant(candidate, context, set(covered))
    ]
    if not candidates:
        return None

    try:
        chunks = _run(
            KnowledgeRetrievalService(lambda: db).retrieve(
                query_text=_build_query(flow, context, candidates),
                topic=flow.applicable_complaint,
                language="en",
                top_k=RAG_TOP_K,
            )
        )
    except Exception as exc:
        logger.warning("RAG retrieval failed safely: %s", type(exc).__name__)
        return None
    if not chunks:
        return None

    candidates = [candidate for candidate in candidates if _is_grounded(candidate, chunks)]
    if not candidates:
        return None

    provider = os.getenv("RAG_GENERATION_PROVIDER", "template").strip().lower()
    plan = _template_plan(candidates) if provider == "template" else None
    if provider == "nvidia":
        plan = _run(_nvidia_plan(candidates, context, chunks))
    if plan is None:
        return None

    selected_question = next((q for q in eligible if q.question_id == plan.question_id), None)
    if selected_question is None or selected_question.field != plan.target_field:
        return None
    localized, translation = localize_rag_question(
        plan.question, language, _FIELD_CANDIDATES.get(plan.target_field)
    )
    rag_question = selected_question.model_copy(
        update={"text": localized, "origin": "rag"}
    )
    top_chunk, score = chunks[0]
    suggestion = RAGSuggestion(
        question=plan.question,
        reason=f"Targets the missing {plan.target_domain} coverage domain.",
        source_chunk_ids=[chunk.id for chunk, _ in chunks],
        candidate_id=_FIELD_CANDIDATES.get(
            plan.target_field, plan.question_id.replace(".", "_")
        ),
        target_field=plan.target_field,
        target_domain=plan.target_domain,
        similarity_score=score,
        source_title=top_chunk.source_title,
        source_section=top_chunk.section,
        generation_provider=plan.provider,
        generation_model=plan.model,
        generation_fallback_used=False,
        generation_latency_ms=plan.latency_ms,
        template_question=selected_question.text.en,
        display_language=language,
        translated_question=localized.model_dump().get(language),
        translation_provider=translation.provider,
        translation_fallback_used=translation.fallback_used,
    )
    _PLAN_CACHE[cache_key] = (rag_question, suggestion)
    return rag_question, suggestion
