"""Signed, short-lived ASR candidates. No audio or unconfirmed text is stored.

Restart invalidates unconfirmed candidates; confirmed provenance is in the audit
transaction with the source answer. The existing interview revision prevents reuse.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from app.core.errors import WorkflowError
from app.services import intake

_key = secrets.token_bytes(32)


def issue(session_id, question_id, revision, result):
    body = {
        "id": secrets.token_hex(16),
        "session": session_id,
        "question": question_id,
        "revision": revision,
        "language": result.language,
        "text": result.transcript,
        "provider": result.provider,
        "model": result.model,
        "expires": time.time() + 600,
    }
    data = base64.urlsafe_b64encode(json.dumps(body, ensure_ascii=False).encode()).decode()
    return data + "." + hmac.new(_key, data.encode(), hashlib.sha256).hexdigest()


def verify(db, session_id, payload, question):
    consent = intake.consent_for(db, session_id)
    if not consent or not consent.voice_processing:
        raise WorkflowError("VOICE_CONSENT_REQUIRED", "Voice processing consent is required.", 403)
    try:
        data, signature = (payload.voice_candidate or "").split(".")
        if not hmac.compare_digest(
            signature, hmac.new(_key, data.encode(), hashlib.sha256).hexdigest()
        ):
            raise ValueError()
        body = json.loads(base64.urlsafe_b64decode(data))
        if not (
            body["expires"] > time.time()
            and body["session"] == session_id
            and body["question"] == question.question_id
            and question.type == "short_text"
            and body["revision"] == payload.expected_revision
            and body["language"] == payload.language
            and body["text"] == payload.value == payload.raw_value
            and payload.status == "answered"
        ):
            raise ValueError()
        return body
    except (ValueError, KeyError, TypeError):
        raise WorkflowError(
            "INVALID_VOICE_CANDIDATE",
            "Confirm a current ASR candidate, or submit edited text as typed.",
            422,
        ) from None
