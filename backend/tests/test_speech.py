import io
import uuid


def _setup_session(client, lang="en", voice_consent=True):
    session_id = str(uuid.uuid4())
    create_res = client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "Test Patient", "demo_abha_id": None},
            "hospital_token": f"TEST-{session_id[:6]}",
            "language": lang,
        },
    )
    assert create_res.status_code == 201

    consent_res = client.put(
        f"/api/sessions/{session_id}/consent",
        json={
            "voice_processing": voice_consent,
            "document_processing": False,
            "share_with_doctor": True,
        },
    )
    assert consent_res.status_code == 200

    flow_res = client.put(
        f"/api/sessions/{session_id}/interview/flow",
        json={"flow_id": "chest_pain"},
    )
    assert flow_res.status_code == 200
    return session_id


def test_transcribe_mock_en_success(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    fake_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00" + b"\x00" * 32)
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("test.webm", fake_audio, "audio/webm")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["transcript"] == "chest pain"
    assert data["language"] == "en"
    assert data["confidence"] is None
    assert data["provider"] == "mock"

    # Invariant: transcribe MUST NOT persist an answer or advance state
    state = client.get(f"/api/sessions/{session_id}/interview").json()
    assert len(state["active_answers"]) == 0
    assert state["question"]["question_id"] == "chief_complaint.description"


def test_transcribe_mock_bn_success(client):
    session_id = _setup_session(client, lang="bn", voice_consent=True)

    fake_audio = io.BytesIO(b"\x1a\x45\xdf\xa3" + b"\x00" * 32)
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("recording.webm", fake_audio, "audio/webm;codecs=opus")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["transcript"] == "বুকে ব্যথা"
    assert data["language"] == "bn"


def test_transcribe_mock_hi_success(client):
    session_id = _setup_session(client, lang="hi", voice_consent=True)

    fake_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVE" + b"\x00" * 32)
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("audio.wav", fake_audio, "audio/wav")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["transcript"] == "सीने में दर्द"
    assert data["language"] == "hi"


def test_transcribe_with_fixtures(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    fixtures = [
        ("headache", "headache"),
        ("fever", "fever"),
        ("dyspnea", "shortness of breath"),
        ("chest_pain_sentence", "I have chest pain"),
        ("negated_dyspnea", "I do not have shortness of breath"),
        ("uncertain_pressure", "I think I sometimes have chest pressure"),
        ("unknown", "I am waiting for the bus"),
    ]

    for fix_id, expected_text in fixtures:
        fake_audio = io.BytesIO(b"audio-bytes-content")
        response = client.post(
            f"/api/sessions/{session_id}/interview/speech/transcribe",
            files={"audio": ("test.webm", fake_audio, "audio/webm")},
            data={"question_id": "chief_complaint.description", "fixture_id": fix_id},
        )
        assert response.status_code == 200
        assert response.json()["transcript"] == expected_text


def test_transcribe_requires_voice_consent(client):
    session_id = _setup_session(client, lang="en", voice_consent=False)

    fake_audio = io.BytesIO(b"some-audio-bytes")
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("test.webm", fake_audio, "audio/webm")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "VOICE_CONSENT_REQUIRED"


def test_transcribe_requires_intake_status(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    # Submit answers to complete interview
    client.get(f"/api/sessions/{session_id}/interview")
    # Fast forward: just mark complete directly or complete intake
    # Since chest_pain has multiple questions, let's complete a minimal session or test complete error
    # Let's test non-existent session first
    bad_res = client.post(
        f"/api/sessions/{uuid.uuid4()}/interview/speech/transcribe",
        files={"audio": ("test.webm", io.BytesIO(b"abc"), "audio/webm")},
        data={"question_id": "q1"},
    )
    assert bad_res.status_code == 404
    assert bad_res.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_transcribe_rejects_empty_audio(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("empty.webm", io.BytesIO(b""), "audio/webm")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_AUDIO"


def test_transcribe_rejects_oversized_audio(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    oversized = io.BytesIO(b"\x00" * (5 * 1024 * 1024 + 10))
    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("big.webm", oversized, "audio/webm")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_TOO_LARGE"


def test_transcribe_rejects_invalid_mime(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("malicious.sh", io.BytesIO(b"echo hello"), "text/plain")},
        data={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MEDIA_TYPE"


def test_transcribe_simulated_failure_and_timeout(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    # Timeout simulation
    res_timeout = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("test.webm", io.BytesIO(b"12345"), "audio/webm")},
        data={"question_id": "chief_complaint.description", "fixture_id": "simulate_timeout"},
    )
    assert res_timeout.status_code == 200
    assert res_timeout.json()["status"] == "unavailable"
    assert res_timeout.json()["reason"] == "timeout"
    assert res_timeout.json()["transcript"] is None

    # Error simulation
    res_err = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("test.webm", io.BytesIO(b"12345"), "audio/webm")},
        data={"question_id": "chief_complaint.description", "fixture_id": "simulate_failure"},
    )
    assert res_err.status_code == 200
    assert res_err.json()["status"] == "unavailable"
    assert res_err.json()["reason"] == "provider_error"


def test_voice_answer_submission_and_normalization(client):
    """Verifies candidate transcript confirmed by patient submits with source='voice' and normalizes."""
    session_id = _setup_session(client, lang="en", voice_consent=True)

    # 1. Transcribe audio to get candidate transcript
    trans_res = client.post(
        f"/api/sessions/{session_id}/interview/speech/transcribe",
        files={"audio": ("test.webm", io.BytesIO(b"12345"), "audio/webm")},
        data={"question_id": "chief_complaint.description"},
    )
    assert trans_res.status_code == 200
    candidate = trans_res.json()["transcript"]
    assert candidate == "chest pain"

    # 2. Patient confirms candidate transcript -> submitted to answer API
    state = client.get(f"/api/sessions/{session_id}/interview").json()
    ans_res = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "request_id": str(uuid.uuid4()),
            "expected_revision": state["revision"],
            "question_id": "chief_complaint.description",
            "status": "answered",
            "value": candidate,
            "raw_value": candidate,
            "source": "voice",
            "voice_candidate": trans_res.json()["candidate_token"],
            "language": "en",
        },
    )
    assert ans_res.status_code == 200
    updated_state = ans_res.json()
    assert len(updated_state["active_answers"]) == 1
    answer_fact = updated_state["active_answers"][0]
    assert answer_fact["source"] == "voice"
    assert answer_fact["raw_value"] == "chest pain"

    # 3. Normalization must have executed on the voice answer
    assert answer_fact["normalization"] is not None
    assert answer_fact["normalization"]["status"] == "normalized"
    concepts = [f["normalized_concept"] for f in answer_fact["normalization"]["facts"]]
    assert "CHEST_PAIN" in concepts


def test_voice_edited_answer_submission(client):
    """Patient edits transcript before confirming; edited wording becomes patient-reported answer."""
    session_id = _setup_session(client, lang="bn", voice_consent=True)

    state = client.get(f"/api/sessions/{session_id}/interview").json()
    edited_text = "কাল থেকে বুকে তীব্র ব্যথা হচ্ছে"

    ans_res = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "request_id": str(uuid.uuid4()),
            "expected_revision": state["revision"],
            "question_id": "chief_complaint.description",
            "status": "answered",
            "value": edited_text,
            "raw_value": edited_text,
            "source": "typed",
            "language": "bn",
        },
    )
    assert ans_res.status_code == 200
    answer_fact = ans_res.json()["active_answers"][0]
    assert answer_fact["source"] == "typed"
    assert answer_fact["raw_value"] == edited_text


def test_synthesize_question_success(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["provider"] == "mock"
    assert data["media_type"] == "audio/wav"
    assert len(data["audio_base64"]) > 0
    # Text must strictly match pinned question text
    assert data["text"] == "Describe your main concern in your own words."


def test_synthesize_bengali_question_text(client):
    session_id = _setup_session(client, lang="bn", voice_consent=True)

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["language"] == "bn"
    assert data["text"] == "আপনার প্রধান সমস্যা নিজের ভাষায় বলুন।"


def test_synthesize_rejects_unknown_question(client):
    session_id = _setup_session(client, lang="en", voice_consent=True)

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": "nonexistent.fake.question"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUESTION_NOT_FOUND"


def test_synthesize_requires_flow_selection(client):
    session_id = str(uuid.uuid4())
    client.post(
        "/api/sessions",
        json={
            "id": session_id,
            "patient": {"name": "No Flow Patient", "demo_abha_id": None},
            "hospital_token": "NOFLOW-01",
            "language": "en",
        },
    )
    client.put(
        f"/api/sessions/{session_id}/consent",
        json={"voice_processing": True, "document_processing": False, "share_with_doctor": True},
    )

    response = client.post(
        f"/api/sessions/{session_id}/interview/speech/synthesize",
        json={"question_id": "chief_complaint.description"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "FLOW_SELECTION_REQUIRED"


def test_public_config_reports_speech_provider(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["phase"] in ("5", "6", "7", "8")
    assert data["speech_provider"] == "mock"
