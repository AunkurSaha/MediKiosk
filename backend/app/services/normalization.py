"""Optional enrichment, isolated from patient-answer persistence and flow decisions."""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.schemas.normalization import (
    ComplaintCandidate,
    LiveProviderResult,
    Normalization,
    NormalizedFact,
    ProviderInput,
    ProviderResult,
)
from app.services import normalization_provider as providers
from app.services.normalization_policy import eligible

logger = logging.getLogger(__name__)


def unavailable(answer, reason="not_processed"):
    return Normalization(
        source_answer_id=answer.id,
        source_question_id=answer.question_id,
        canonical_field=answer.field,
        original_language=answer.language,
        original_text=answer.raw_value,
        status="unavailable",
        reason=reason,
    )


def normalize(answer, *, flow, provider=None, timeout=None):
    provider = provider or providers.configured_provider()
    result = unavailable(answer)
    result.provider, result.provider_version = provider.name, provider.version
    result.model = getattr(provider, "model", None)
    result.prompt_version = getattr(provider, "prompt_version", None)
    if provider.name == "nvidia":
        result.schema_version = "1.1"
    result.created_at = datetime.now(timezone.utc)
    request = ProviderInput(
        text=answer.raw_value,
        language=answer.language,
        canonical_field=answer.field,
        context={
            "flow_id": flow.flow_id,
            "flow_version": flow.version,
            "question_id": answer.question_id,
        },
    )
    try:
        output = asyncio.run(
            providers.invoke(provider, request, timeout or providers.timeout_seconds())
        )
    except TimeoutError:
        result.reason = "timeout"
        return result
    except providers.UnsupportedLanguage:
        result.reason = "unsupported_language"
        return result
    except providers.ProviderFailure as exc:
        result.reason = exc.reason
        return result
    except Exception:
        result.reason = "disabled" if provider.name == "disabled" else "provider_unavailable"
        return result
    finally:
        result.latency_ms = getattr(provider, "latency_ms", None)
        result.token_usage = getattr(provider, "token_usage", None)
    try:
        if not isinstance(output, dict):
            raise ValueError("Provider must return a JSON object")
        contract = LiveProviderResult if provider.name == "nvidia" else ProviderResult
        validated = contract.model_validate(output)
        if validated.canonical_field != answer.field or validated.language != answer.language:
            raise ValueError("Provider source metadata mismatch")
        if any(f.evidence not in answer.raw_value for f in validated.facts):
            raise ValueError("Provider evidence absent from original source")
        catalog = providers.concept_catalog()
        result.facts = [
            NormalizedFact(
                normalized_concept=f.concept,
                normalized_display=catalog[f.concept]["display"],
                normalized_value=normalized_value(f, catalog, validated.schema_version),
                polarity=f.polarity,
                evidence=f.evidence,
                confidence=f.confidence,
                certainty=f.certainty,
                verification_status="needs_verification"
                if f.certainty != "certain" or (f.confidence is not None and f.confidence < 0.8)
                else "machine_normalized",
            )
            for f in validated.facts
        ]
        result.status = validated.status
        result.schema_version = validated.schema_version
        result.reason = {
            "normalized": None,
            "unrecognized": "no_match",
            "unknown": "explicit_unknown",
        }[validated.status]
    except (ValidationError, ValueError, TypeError, KeyError):
        result.status, result.reason, result.facts = "unavailable", "invalid_result", []
    return result


def normalized_value(fact, catalog, schema_version):
    value = catalog[fact.concept]["value"]
    if schema_version == "1.1":
        if fact.certainty == "uncertain":
            return None
        if fact.polarity == "absent":
            return False if isinstance(value, bool) else None
    return value


def persist_committed(db, answer, question, flow, answer_status="answered"):
    """Called only after source/cursor/receipt commit; enrichment has its own transaction."""
    if not eligible(question):
        return
    try:
        # Serialize with completion/corrections. A completion winning the small commit gap
        # keeps its original snapshot; never enrich an already completed clinical record.
        session = db.scalar(
            select(models.Session)
            .where(models.Session.id == answer.session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if session is not None and session.status == "intake":
            persist(db, answer, question, flow, answer_status)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Normalization unavailable after source answer committed")


def persist(db, answer, question, flow, answer_status="answered"):
    if not eligible(question):
        return
    try:
        # A provider or enrichment INSERT failure must not poison the raw-answer transaction.
        with db.begin_nested():
            existing = db.scalar(
                select(models.NormalizationResult).where(
                    models.NormalizationResult.source_answer_id == answer.id
                )
            )
            if existing:
                return
            if answer_status != "answered":
                result = unavailable(answer, "explicit_unknown")
                result.status = "unknown"
                result.provider, result.provider_version = "none", "1.0"
                result.created_at = datetime.now(timezone.utc)
            else:
                result = normalize(answer, flow=flow)
            result.id = str(uuid4())
            normalization_row = models.NormalizationResult(
                id=result.id,
                session_id=answer.session_id,
                source_answer_id=answer.id,
                provider=result.provider,
                provider_version=result.provider_version,
                schema_version=result.schema_version,
                policy_version=result.policy_version,
                status=result.status,
                result_json=result.model_dump(mode="json"),
                created_at=result.created_at,
            )
            db.add(normalization_row)
            db.flush()
            from app.services import clinical_evidence

            clinical_evidence.project_normalization_evidence(db, normalization_row)
    except SQLAlchemyError:
        logger.warning("Normalization storage unavailable; source answer retained")


def for_answers(db, session_id):
    try:
        with db.begin_nested():
            rows = db.scalars(
                select(models.NormalizationResult).where(
                    models.NormalizationResult.session_id == session_id
                )
            ).all()
            return {r.source_answer_id: Normalization.model_validate(r.result_json) for r in rows}
    except (SQLAlchemyError, ValidationError):
        logger.warning("Normalization results unavailable; using patient-reported history")
        return {}


def enrich(answer, question, results):
    if not eligible(question):
        return None
    result = results.get(answer.id)
    if result and (
        result.source_answer_id,
        result.source_question_id,
        result.canonical_field,
        result.original_language,
        result.original_text,
    ) != (answer.id, answer.question_id, answer.field, answer.language, answer.raw_value):
        return unavailable(answer, "invalid_result")
    return result or unavailable(answer)


def complaint_candidates(result: Normalization):
    """Future explicit-confirmation boundary; never called by the current interview workflow."""
    if (
        not result.id
        or result.status != "normalized"
        or result.canonical_field not in ("chief_complaint.description", "chief_complaint")
    ):
        return []
    targets = {
        "CHEST_PAIN": "chest_pain",
        "ABDOMINAL_PAIN": "abdominal_pain",
        "HEADACHE": "headache",
        "FEVER": "fever",
        "COUGH": "cough_breathlessness",
        "DYSPNEA": "cough_breathlessness",
    }
    return [
        ComplaintCandidate(flow_id=flow_id, source_normalization_id=result.id)
        for flow_id in dict.fromkeys(
            targets[f.normalized_concept]
            for f in result.facts
            if f.normalized_concept in targets
            and f.polarity == "present"
            and f.certainty == "certain"
        )
    ]
