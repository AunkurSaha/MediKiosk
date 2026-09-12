import asyncio
import base64
import logging
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.errors import WorkflowError
from app.schemas.speech import SpeechSynthesisResult, TranscriptionResult
from app.services import intake
from app.services.speech_provider import get_speech_provider

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB
SPEECH_TIMEOUT_SECONDS = 15.0

ALLOWED_MIME_PREFIXES = (
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/mpeg",
    "audio/m4a",
    "audio/aac",
    "audio/flac",
)


def _validate_media_type(content_type: str | None) -> str:
    if not content_type:
        raise WorkflowError("INVALID_MEDIA_TYPE", "Content-Type header is required for audio.", 422)

    normalized = content_type.strip().lower()
    base_mime = normalized.split(";")[0].strip()

    if not any(base_mime == allowed for allowed in ALLOWED_MIME_PREFIXES):
        raise WorkflowError(
            "INVALID_MEDIA_TYPE",
            f"Unsupported audio format '{content_type}'. Supported formats: WebM, WAV, OGG, MP4/M4A, MP3.",
            422,
        )
    return normalized


async def transcribe_audio(
    db: Session,
    session_id: str,
    audio_file: UploadFile,
    question_id: str,
    fixture_id: str | None = None,
    user: models.User | None = None,
) -> TranscriptionResult:
    """Validate voice consent, bounds, and audio format, then transcribe via SpeechProvider.

    Privacy Invariant: Multipart audio may spool to temporary disk; the route closes it on every outcome. No permanent audio retention.
    Interview Invariant: Transcribe produces only a candidate transcript. It NEVER persists an answer.
    """
    session = db.get(models.Session, session_id)
    if not session:
        raise WorkflowError("SESSION_NOT_FOUND", "Session not found.", 404)
    intake.verify_session_access(db, session, user)

    if session.status != "intake":
        raise WorkflowError(
            "SESSION_LOCKED", "Voice input is only allowed during active intake.", 409
        )

    consent = db.scalar(select(models.Consent).where(models.Consent.session_id == session_id))
    if not consent or not consent.share_with_doctor:
        raise WorkflowError("CONSENT_REQUIRED", "Doctor sharing consent is required.", 403)

    if not consent.voice_processing:
        raise WorkflowError(
            "VOICE_CONSENT_REQUIRED",
            "Voice processing consent is required to use the microphone.",
            403,
        )

    from app.services import adaptive

    flow, run = adaptive.require_run(db, session_id)
    curr_state = adaptive.state(db, session_id, user=user)
    question = curr_state.question
    if question is None or question.question_id != question_id or question.type != "short_text":
        raise WorkflowError(
            "QUESTION_NOT_CURRENT", "Voice input requires the current free-text question.", 409
        )
    revision = curr_state.revision
    media_type = _validate_media_type(audio_file.content_type)

    # Stream bounded bytes into memory with size check
    audio_bytes = bytearray()
    chunk_size = 64 * 1024
    while True:
        chunk = await audio_file.read(chunk_size)
        if not chunk:
            break
        audio_bytes.extend(chunk)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise WorkflowError(
                "AUDIO_TOO_LARGE",
                f"Audio exceeds maximum size limit ({MAX_AUDIO_BYTES // (1024 * 1024)}MB).",
                422,
            )

    if len(audio_bytes) == 0:
        raise WorkflowError("EMPTY_AUDIO", "Audio file is empty.", 422)

    provider = get_speech_provider()
    metadata: dict[str, Any] = {"question_id": question_id}
    if fixture_id:
        metadata["fixture_id"] = fixture_id

    try:
        result = await asyncio.wait_for(
            provider.transcribe(
                audio=bytes(audio_bytes),
                language=session.language,
                media_type=media_type,
                metadata=metadata,
            ),
            timeout=SPEECH_TIMEOUT_SECONDS,
        )
        result = TranscriptionResult.model_validate(result.model_dump())
        if (
            result.language != session.language
            or (result.status == "success" and (not result.transcript or result.reason))
            or (result.status == "unavailable" and result.transcript is not None)
        ):
            raise ValueError("Invalid provider result")
        result.provider = provider.name
        result.model = result.model or provider.version
        result.confidence = None  # Neither shipped adapter exposes calibrated confidence.
        result.candidate_token = None
        if result.status == "success":
            from app.services.voice_candidates import issue

            result.candidate_token = issue(session_id, question_id, revision, result)
        return result
    except Exception as e:
        logger.warning(f"Speech transcription error: {type(e).__name__}")
        return TranscriptionResult(
            status="unavailable",
            transcript=None,
            language=session.language,  # type: ignore[arg-type]
            confidence=None,
            provider=getattr(provider, "name", "unknown"),
            model=getattr(provider, "version", None),
            reason="provider_error",
        )


async def synthesize_question(
    db: Session,
    session_id: str,
    question_id: str,
    user: models.User | None = None,
) -> SpeechSynthesisResult:
    """Synthesize audio for the exact localized question text from the session's pinned flow snapshot.

    Privacy Invariant: Strictly synthesizes pinned static question text. Never sends patient answers or history to TTS.
    """
    session = db.get(models.Session, session_id)
    if not session:
        raise WorkflowError("SESSION_NOT_FOUND", "Session not found.", 404)
    intake.verify_session_access(db, session, user)

    consent = db.scalar(select(models.Consent).where(models.Consent.session_id == session_id))
    if not consent or not consent.share_with_doctor:
        raise WorkflowError("CONSENT_REQUIRED", "Consent is required.", 403)

    run = db.get(models.InterviewRun, session_id)
    if not run or not run.flow_snapshot:
        raise WorkflowError(
            "FLOW_SELECTION_REQUIRED", "Interview flow has not been selected yet.", 409
        )

    target_q = None
    for section in run.flow_snapshot.get("sections", []):
        for q in section.get("questions", []):
            if q.get("question_id") == question_id:
                target_q = q
                break
        if target_q:
            break

    if not target_q and question_id.startswith("rag_followup"):
        from app.services import adaptive
        from app.services.rag_integration import get_cached_rag_question

        curr_state = adaptive.state(db, session_id, user=user)
        if curr_state.question and curr_state.question.question_id == question_id:
            target_q = curr_state.question.model_dump()
        else:
            cached_q = get_cached_rag_question(session_id, question_id, session.language)
            if cached_q:
                target_q = cached_q.model_dump()

    if not target_q:
        raise WorkflowError(
            "QUESTION_NOT_FOUND", f"Question '{question_id}' not found in pinned flow.", 404
        )

    text_obj = target_q.get("text", {})
    localized_text = text_obj.get(session.language) or text_obj.get("en", "")
    if not localized_text:
        raise WorkflowError("QUESTION_TEXT_NOT_FOUND", "Localized question text not found.", 404)

    provider = get_speech_provider()
    try:
        result = await asyncio.wait_for(
            provider.synthesize(text=localized_text, language=session.language),
            timeout=SPEECH_TIMEOUT_SECONDS,
        )
        result = SpeechSynthesisResult.model_validate(result.model_dump())
        if result.language != session.language or result.text != localized_text:
            raise ValueError("Invalid synthesis source")
        if result.status == "success":
            if (
                result.media_type not in ("audio/wav", "audio/mpeg", "audio/mp3", "audio/ogg")
                or not result.audio_base64
                or len(result.audio_base64) > 8 * 1024 * 1024
            ):
                raise ValueError("Invalid synthesis audio")
            base64.b64decode(result.audio_base64, validate=True)
        elif result.audio_base64 is not None:
            raise ValueError("Invalid unavailable synthesis")
        return result
    except Exception as e:
        logger.warning(f"Speech synthesis error: {type(e).__name__}")
        return SpeechSynthesisResult(
            status="unavailable",
            audio_base64=None,
            media_type="audio/wav",
            text=localized_text,
            language=session.language,  # type: ignore[arg-type]
            provider=getattr(provider, "name", "unknown"),
            reason="provider_error",
        )
