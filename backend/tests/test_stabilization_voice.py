import uuid
from unittest.mock import AsyncMock

import pytest

from tests.test_adaptive import selected


def voice_payload(state, **extra):
    return {
        "request_id": str(uuid.uuid4()),
        "expected_revision": state["revision"],
        "question_id": state["question"]["question_id"],
        "status": "answered",
        "value": "chest pain",
        "raw_value": "chest pain",
        "source": "voice",
        "language": "en",
        **extra,
    }


def test_voice_submission_requires_consent_and_candidate(client):
    sid, state = selected(client)
    url = f"/api/sessions/{sid}/interview/answers"
    assert client.post(url, json=voice_payload(state)).status_code == 403
    client.put(
        f"/api/sessions/{sid}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": False},
    )
    assert client.post(url, json=voice_payload(state)).status_code == 422
    assert not client.get(f"/api/sessions/{sid}/interview").json()["active_answers"]


def test_transcription_checks_current_question_before_provider_and_closes_audio(
    client, monkeypatch
):
    from app.services import speech

    sid, state = selected(client)
    client.put(
        f"/api/sessions/{sid}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": False},
    )
    spy = AsyncMock()
    monkeypatch.setattr(speech, "get_speech_provider", lambda: spy)
    response = client.post(
        f"/api/sessions/{sid}/interview/speech/transcribe",
        files={"audio": ("sample.webm", b"sample", "audio/webm")},
        data={"question_id": "not-current"},
    )
    assert response.status_code == 409
    spy.transcribe.assert_not_called()


def test_confirmed_candidate_is_bound_to_text_session_and_source(client):
    sid, state = selected(client)
    client.put(
        f"/api/sessions/{sid}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": False},
    )
    response = client.post(
        f"/api/sessions/{sid}/interview/speech/transcribe",
        files={"audio": ("sample.webm", b"sample", "audio/webm")},
        data={"question_id": state["question"]["question_id"]},
    )
    assert response.status_code == 200
    candidate = response.json()
    token = candidate["candidate_token"]
    payload = voice_payload(
        state,
        value=candidate["transcript"],
        raw_value=candidate["transcript"],
        voice_candidate=token,
    )
    url = f"/api/sessions/{sid}/interview/answers"
    assert (
        client.post(url, json={**payload, "raw_value": "forged", "value": "forged"}).status_code
        == 422
    )
    result = client.post(url, json=payload)
    assert result.status_code == 200
    assert result.json()["active_answers"][0]["source"] == "voice"
    assert client.post(url, json=payload).status_code == 200


@pytest.mark.parametrize("consented", [False, True])
def test_spooled_multipart_audio_is_closed_on_success_and_rejection(client, monkeypatch, consented):
    from app.services import speech

    sid, state = selected(client)
    client.put(
        f"/api/sessions/{sid}/consent",
        json={
            "share_with_doctor": True,
            "voice_processing": consented,
            "document_processing": False,
        },
    )
    uploads = []
    original = speech.transcribe_audio

    async def observe(**kwargs):
        uploads.append(kwargs["audio_file"].file)
        assert kwargs["audio_file"].file._rolled
        return await original(**kwargs)

    monkeypatch.setattr(speech, "transcribe_audio", observe)
    response = client.post(
        f"/api/sessions/{sid}/interview/speech/transcribe",
        files={"audio": ("large.webm", b"x" * (2 * 1024 * 1024), "audio/webm")},
        data={"question_id": state["question"]["question_id"]},
    )
    assert response.status_code == (200 if consented else 403)
    assert uploads and all(upload.closed for upload in uploads)


def test_transcription_deadline_cancels_provider_and_keeps_interview_unchanged(client, monkeypatch):
    import asyncio

    from app.services import speech

    sid, state = selected(client)
    client.put(
        f"/api/sessions/{sid}/consent",
        json={"share_with_doctor": True, "voice_processing": True, "document_processing": False},
    )
    cancelled = []

    class SlowProvider:
        name = "synthetic"
        version = "test"

        async def transcribe(self, **kwargs):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(speech, "get_speech_provider", SlowProvider)
    monkeypatch.setattr(speech, "SPEECH_TIMEOUT_SECONDS", 0.01)
    response = client.post(
        f"/api/sessions/{sid}/interview/speech/transcribe",
        files={"audio": ("sample.webm", b"synthetic", "audio/webm")},
        data={"question_id": state["question"]["question_id"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["candidate_token"] is None
    assert cancelled
    after = client.get(f"/api/sessions/{sid}/interview").json()
    assert after["revision"] == state["revision"]
    assert not after["active_answers"]


def test_candidate_cannot_cross_sessions_or_survive_revision_change(client):
    sid, state = selected(client)
    other, other_state = selected(client)
    for target in [sid, other]:
        client.put(
            f"/api/sessions/{target}/consent",
            json={
                "share_with_doctor": True,
                "voice_processing": True,
                "document_processing": False,
            },
        )
    candidate = client.post(
        f"/api/sessions/{sid}/interview/speech/transcribe",
        files={"audio": ("sample.webm", b"sample", "audio/webm")},
        data={"question_id": state["question"]["question_id"]},
    ).json()
    data = dict(
        value=candidate["transcript"],
        raw_value=candidate["transcript"],
        voice_candidate=candidate["candidate_token"],
    )
    assert (
        client.post(
            f"/api/sessions/{other}/interview/answers", json=voice_payload(other_state, **data)
        ).status_code
        == 422
    )
    url = f"/api/sessions/{sid}/interview/answers"
    typed = voice_payload(
        state, value="typed alternative", raw_value="typed alternative", source="typed"
    )
    saved = client.post(url, json=typed).json()
    revised = client.put(
        f"/api/sessions/{sid}/interview/cursor",
        json={
            "question_id": state["question"]["question_id"],
            "expected_revision": saved["revision"],
        },
    ).json()
    assert client.post(url, json=voice_payload(revised, **data)).status_code == 422
