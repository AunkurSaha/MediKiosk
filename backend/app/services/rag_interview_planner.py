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
from app.services.rag_wording_provider import GroqWordingSettings, NvidiaWordingSettings
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
    texts = [text.strip()[:200] for text in context.get("raw_answer_texts", []) if text.strip()]
    return "; ".join(texts[:6]) or "No additional clinical facts collected yet"


def _build_query(flow, context: dict, candidates: list[dict]) -> str:
    missing = ", ".join(f"{c['target_domain']} ({c['target_field']})" for c in candidates)
    answered = ", ".join(sorted(context.get("answered_fields", set()))) or "none"
    return (
        f"Chief complaint: {flow.label.en}. Known patient-reported facts: {_safe_facts(context)}. "
        f"Answered fields: {answered}. Missing clinical coverage domains: {missing}. "
        "Select the next most relevant history question."
    )


def _extract_patient_symptom_context(context: dict | None) -> dict[str, str]:
    if not context:
        return {}
    texts = " ".join(context.get("raw_answer_texts", [])).lower()
    info: dict[str, str] = {}

    # Character
    for term in ["crushing", "squeezing", "sharp", "burning", "tight", "heaviness", "throbbing", "aching", "pressure"]:
        if term in texts:
            info["character"] = term
            break

    # Location
    if "behind" in texts and "breastbone" in texts:
        info["location"] = "behind your breastbone"
    elif "left" in texts and ("chest" in texts or "side" in texts):
        info["location"] = "the left side of your chest"
    elif "center" in texts or "middle" in texts:
        info["location"] = "the center of your chest"
    elif "knee" in texts:
        info["location"] = "your knee"
    elif "head" in texts or "temple" in texts:
        info["location"] = "your head"

    # Exertion / trigger
    if "stairs" in texts:
        info["trigger"] = "climbing stairs"
    elif "walking" in texts:
        info["trigger"] = "walking"
    elif "breathe" in texts or "breathing" in texts:
        info["trigger"] = "taking a breath"
    elif "exercise" in texts or "running" in texts:
        info["trigger"] = "physical exercise"

    # Radiation
    if "arm" in texts:
        info["radiation"] = "your left arm"
    elif "jaw" in texts:
        info["radiation"] = "your jaw"
    elif "back" in texts:
        info["radiation"] = "your back"

    # Autonomic / associated
    if "sweat" in texts:
        info["autonomic"] = "sweating"
    elif "nausea" in texts:
        info["autonomic"] = "nausea"
    elif "breath" in texts and "short" in texts:
        info["autonomic"] = "shortness of breath"
    elif "light" in texts:
        info["autonomic"] = "sensitivity to light"

    return info


def _adaptive_template_wording(
    selected: dict,
    context: dict | None = None,
    chunks: list[tuple[Any, float]] | None = None,
    complaint: str | None = None,
) -> str:
    fb = selected["fallback_question"]
    syms = _extract_patient_symptom_context(context)
    if not syms:
        return fb

    dom = selected.get("target_domain", "")
    comp = (complaint or "chest_pain").lower()

    if comp == "headache":
        if dom in ("site", "location"):
            if syms.get("character"):
                return f"Where in your head is the {syms['character']} pain centered—is it on one side, near your temples, behind your eyes, or across your whole head?"
            return "Where is the headache located—is it on one side of your head, near your temples, behind your eyes, or all over?"
        elif dom == "character":
            if syms.get("location"):
                return f"How would you describe the discomfort in {syms['location']}—is it a pulsating throbbing ache, constant tight pressure, or sharp and piercing?"
            return "How would you describe the headache—is it a pulsating throbbing ache, constant tight squeezing band, or sharp and stabbing?"
        elif dom in ("radiation", "radiation destination"):
            return "Does the headache pain radiate down into your neck, shoulders, or face?"
        elif dom == "onset":
            if syms.get("character"):
                return f"How long ago did this {syms['character']} headache start, and did it come on like a sudden thunderclap or develop gradually?"
            return "How long ago did this headache start, and did it begin suddenly or build up gradually?"
        elif dom in ("aggravating_factors", "triggers"):
            if syms.get("trigger"):
                return f"Does {syms['trigger']}, bright light, loud sound, or moving around make the headache worse?"
            return "Do bright lights, loud noises, bending forward, or coughing make the headache worse?"
        elif dom == "relieving_factors":
            return "Does lying down in a quiet dark room or taking any pain medicine help relieve the headache?"
        elif dom in ("associated_symptoms", "autonomic_symptoms"):
            if syms.get("autonomic"):
                return f"Along with {syms['autonomic']}, are you having any nausea, vomiting, vision changes, or sensitivity to light or sound?"
            return "Along with the headache, are you experiencing any nausea, vomiting, visual flashing lights, or sensitivity to light or sound?"
        elif dom == "severity":
            if syms.get("character"):
                return f"On a scale of 0 to 10, how severe is that {syms['character']} headache right now?"
            return "On a scale of 0 to 10, how severe is the headache right now?"
        elif dom in ("timing and pattern", "timing"):
            return "Is the headache steady and constant, or does it throb and come in waves?"

    elif comp == "abdominal_pain":
        if dom in ("site", "location"):
            return "Where in your abdomen or belly is the pain located—is it in the upper middle, lower right, lower left, or all over?"
        elif dom == "character":
            return "How would you describe the abdominal pain—is it cramping, sharp, a dull ache, or a burning sensation?"
        elif dom in ("radiation", "radiation destination"):
            return "Does the stomach pain spread anywhere else, such as to your back, shoulder, or groin?"
        elif dom == "onset":
            if syms.get("trigger"):
                return f"How long ago did the stomach discomfort begin after {syms['trigger']}, and did it start suddenly or gradually?"
            return "How long ago did this stomach pain start, and did it begin suddenly or build up gradually?"
        elif dom in ("aggravating_factors", "exertional_relationship"):
            return "Does eating food, moving around, coughing, or pressing on your belly make the pain worse?"
        elif dom == "relieving_factors":
            return "Does resting quietly, curling up, going to the bathroom, or taking medicine give you relief?"
        elif dom in ("associated_symptoms", "autonomic_symptoms"):
            return "Along with the abdominal pain, are you having any nausea, vomiting, diarrhea, constipation, or fever?"
        elif dom == "severity":
            return "On a scale of 0 to 10, how severe is the stomach pain right now?"
        elif dom in ("timing and pattern", "timing"):
            return "Is the abdominal discomfort constant, or does it come and go in cramping waves?"

    elif comp == "cough_breathlessness":
        if dom == "character":
            return "How would you describe your cough—is it dry and hacking, or are you bringing up mucus or phlegm?"
        elif dom in ("site", "location"):
            return "Where do you feel the breathlessness or discomfort—in your throat, deep in your chest, or across your lungs?"
        elif dom in ("aggravating_factors", "exertional_relationship"):
            if syms.get("trigger"):
                return f"Does {syms['trigger']}, walking, climbing stairs, or cold air make your breathing or cough worse?"
            return "Does walking, climbing stairs, lying flat, or cold air make your breathing or cough worse?"
        elif dom in ("associated_symptoms", "autonomic_symptoms"):
            return "Along with the cough and shortness of breath, are you having any fever, chest tightness, or wheezing?"
        elif dom == "onset":
            return "How long ago did this cough or breathing difficulty start, and did it begin suddenly or gradually?"
        elif dom == "relieving_factors":
            return "Does sitting upright, resting, or using an inhaler or warm liquids help relieve your breathing?"
        elif dom == "severity":
            return "On a scale of 0 to 10, how severe is your shortness of breath right now?"

    elif comp == "fever":
        if dom == "onset":
            return "How long have you had this fever, and did it come on suddenly with chills or build up gradually?"
        elif dom == "character":
            return "How would you describe the fever—is it a mild warmth, high burning fever, or does it come with severe shaking chills?"
        elif dom in ("associated_symptoms", "autonomic_symptoms"):
            return "Along with the fever, are you experiencing chills, body aches, sore throat, cough, or a rash?"
        elif dom == "severity":
            return "On a scale of 0 to 10, how severe is the fever and body discomfort right now?"

    else:
        # Chest pain (default) and general complaints
        if dom in ("site", "location"):
            if syms.get("character"):
                return f"Where in your chest is the {syms['character']} sensation centered—is it directly behind your breastbone, on the left side, or across your whole chest?"
            elif syms.get("trigger") == "taking a breath":
                return "Where in your chest is the pain located when you take a breath?"
            return "Where in your chest is the pain centered—is it directly behind your breastbone, on the left side, or across your whole chest?"

        elif dom == "character":
            if syms.get("location"):
                return f"How would you describe the sensation in {syms['location']}—is it a heavy crushing pressure, tight squeezing, burning, or sharp and stabbing?"
            return "How would you describe the chest discomfort—is it a heavy crushing pressure, tight squeezing, burning, or sharp and stabbing?"

        elif dom in ("radiation", "radiation destination"):
            if syms.get("character"):
                return f"Does that {syms['character']} discomfort spread anywhere else, such as down your left arm, up into your jaw or neck, or to your back?"
            elif syms.get("radiation"):
                return f"You mentioned the pain travels to {syms['radiation']}. Does it spread anywhere else, such as up into your jaw, neck, or back?"
            return "Does the pain spread anywhere else, such as down your left arm, up into your jaw or neck, or between your shoulder blades?"

        elif dom == "onset":
            if syms.get("trigger"):
                return f"How long ago did the discomfort begin while {syms['trigger']}, and did it start suddenly or gradually?"
            elif syms.get("character"):
                return f"How long ago did this {syms['character']} discomfort start, and did it come on suddenly or build up gradually?"
            return "How long ago did this problem start, and did it begin suddenly or gradually?"

        elif dom in ("aggravating_factors", "exertional_relationship"):
            if syms.get("trigger") == "taking a breath":
                return "Does taking a deep breath, coughing, or changing your body position make the pain worse?"
            elif syms.get("trigger"):
                return f"Does {syms['trigger']}, walking, or any physical effort make the chest discomfort worse?"
            return "Does walking, climbing stairs, or any physical exertion bring on or worsen the chest pain?"

        elif dom == "relieving_factors":
            if syms.get("trigger"):
                return "Since this started with physical effort, does resting quietly, sitting down, or taking any medicine give you relief?"
            return "Does sitting down, resting quietly, or taking any medicine give you relief?"

        elif dom == "severity":
            if syms.get("character"):
                return f"On a scale of 0 to 10, how severe is that {syms['character']} discomfort right now?"
            return "On a scale of 0 to 10, how severe is the pain right now?"

        elif dom in ("associated_symptoms", "autonomic_symptoms"):
            if syms.get("character"):
                return f"Along with the {syms['character']} chest pain, are you having any cold sweats, shortness of breath, nausea, or lightheadedness?"
            return "Are you also experiencing cold sweats, shortness of breath, nausea, or dizziness?"

        elif dom in ("timing and pattern", "timing"):
            return "Is the chest discomfort steady and constant, or does it come and go in waves?"

    return fb


def _template_plan(
    candidates: list[dict],
    context: dict | None = None,
    chunks: list[tuple[Any, float]] | None = None,
    complaint: str | None = None,
) -> PlannedWording:
    selected = candidates[0]
    question_text = _adaptive_template_wording(selected, context, chunks, complaint)
    return PlannedWording(
        question_id=selected["question_id"],
        target_field=selected["target_field"],
        target_domain=selected["target_domain"],
        question=question_text,
        provider="template",
        model=None,
        latency_ms=0,
    )


async def _openai_compatible_plan(
    candidates: list[dict],
    context: dict,
    chunks: list[tuple[Any, float]],
    *,
    settings,
    provider_name: str,
) -> PlannedWording | None:
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
        "You are an expert clinical interviewer for MediKiosk. Choose only one item from "
        "missing_candidates, keep its question_id, target_field and target_domain unchanged, "
        "and word one patient-friendly clinical history question grounded in retrieved_sources. "
        "Adapt the wording naturally to the patient's reported symptoms using ONLY facts explicitly "
        "present in known_patient_reported_facts (for example, refer to their specific symptom description "
        "or location). Never invent or assume activities, triggers, or symptoms the patient did not state. "
        "Do not diagnose, infer a diagnosis, recommend treatment or medication, mention sources/AI, "
        "or combine multiple domains into compound questions. "
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
        logger.debug("%s wording response received", provider_name)
        data = strict_json_parse(raw.strip()) if isinstance(raw, str) else None
    except Exception as exc:
        logger.warning("RAG interview planning failed safely: %s", type(exc).__name__)
        return None
    if not isinstance(data, dict):
        logger.warning("%s response was not valid JSON", provider_name)
        return None
    if set(data) != {"question_id", "target_field", "target_domain", "question"}:
        logger.warning("%s response keys mismatch", provider_name)
        return None
    selected = next((c for c in candidates if c["question_id"] == data["question_id"]), None)
    if selected is None or data["target_field"] != selected["target_field"] or data[
        "target_domain"
    ] != selected["target_domain"]:
        logger.warning("%s candidate mismatch", provider_name)
        return None
    raw_question = json.dumps({"question": data["question"]}, ensure_ascii=False)
    valid, v_reason, wording = validate_generated_wording(
        raw_question,
        selected["candidate_id"],
        selected["fallback_question"],
        known_facts=_safe_facts(context),
    )
    if not valid:
        logger.warning("%s wording rejected by validator: reason=%s", provider_name, v_reason)
        return None
    return PlannedWording(
        question_id=selected["question_id"],
        target_field=selected["target_field"],
        target_domain=selected["target_domain"],
        question=wording,
        provider=provider_name,
        model=settings.model,
        latency_ms=round((perf_counter() - started) * 1000),
    )


async def _nvidia_plan(
    candidates: list[dict], context: dict, chunks: list[tuple[Any, float]]
) -> PlannedWording | None:
    return await _openai_compatible_plan(
        candidates,
        context,
        chunks,
        settings=NvidiaWordingSettings.from_environment(),
        provider_name="nvidia",
    )


async def _groq_plan(
    candidates: list[dict], context: dict, chunks: list[tuple[Any, float]]
) -> PlannedWording | None:
    return await _openai_compatible_plan(
        candidates,
        context,
        chunks,
        settings=GroqWordingSettings.from_environment(),
        provider_name="groq",
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

    topic = flow.applicable_complaint
    if topic == "general":
        topic = None
    try:
        chunks = _run(
            KnowledgeRetrievalService(lambda: db).retrieve(
                query_text=_build_query(flow, context, candidates),
                topic=topic,
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
    plan = None
    if provider == "nvidia":
        plan = _run(_nvidia_plan(candidates, context, chunks))
    elif provider == "groq":
        plan = _run(_groq_plan(candidates, context, chunks))
    if plan is None:
        plan = _template_plan(candidates, context, chunks, topic)

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
