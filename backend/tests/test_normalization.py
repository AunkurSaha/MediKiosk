import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.schemas.normalization import ProviderInput
from app.services import normalization as service
from app.services import normalization_provider as providers
from app.services.flow_registry import registry
from app.services.normalization_policy import eligible
from tests.test_adaptive import navigate, payload, selected, submit, until
from tests.test_workflow import DOCTOR


def source(text="chest pain", language="en", field="chief_complaint.description"):
    return SimpleNamespace(
        id="source-answer",
        question_id=field,
        field=field,
        raw_value=text,
        language=language,
        session_id="session",
    )


def normalized(answer=None, provider=None, **kwargs):
    return service.normalize(
        answer or source(), flow=registry()["fever"], provider=provider, **kwargs
    )


def valid_output():
    return {
        "schema_version": "1.0",
        "canonical_field": "chief_complaint.description",
        "language": "en",
        "status": "normalized",
        "facts": [
            {
                "concept": "CHEST_PAIN",
                "evidence": "chest pain",
                "certainty": "certain",
                "confidence": None,
            }
        ],
    }


def fake(output=None, error=None):
    return SimpleNamespace(
        name="test-provider",
        version="test-1",
        normalize=AsyncMock(
            return_value=valid_output() if output is None else output, side_effect=error
        ),
    )


@pytest.mark.parametrize(
    "fixture", providers.vocabulary()[0]["fixtures"], ids=lambda f: f["language"] + ":" + f["text"]
)
def test_explicit_multilingual_fixtures(fixture):
    answer = source(fixture["text"], fixture["language"])
    result = normalized(answer)
    assert result.status == fixture["status"]
    assert result.original_text == answer.raw_value
    assert result.original_language == answer.language
    assert [f.normalized_concept for f in result.facts] == [f["concept"] for f in fixture["facts"]]
    assert all(f.confidence is None for f in result.facts)
    assert result.provider == "mock" and result.provider_version == "1.0.0"
    assert result.created_at and result.source_answer_id == answer.id
    assert all(f.verification_status != "clinician_verified" for f in result.facts)


def test_mock_repeated_calls_deterministic_and_whitespace_preserved():
    request = ProviderInput(
        text="  CHEST   pain  ",
        language="en",
        canonical_field="chief_complaint.description",
        context={},
    )
    provider = providers.MockClinicalNormalizationProvider()
    outputs = [asyncio.run(provider.normalize(request)) for _ in range(5)]
    assert all(value == outputs[0] for value in outputs)
    result = normalized(source(request.text))
    assert result.original_text == request.text and result.facts[0].evidence == request.text


@pytest.mark.parametrize(
    "phrase,lang",
    [
        ("no chest pain", "en"),
        ("my father has chest pain", "en"),
        ("বুকের মধ্যে অদ্ভুত চাপ লাগছে", "bn"),
        ("सीने में दर्द नहीं है", "hi"),
        ("MYOCARDIAL_INFARCTION", "en"),
        ("take aspirin", "en"),
        ("chest pain and fever", "en"),
    ],
)
def test_unknown_negation_context_and_diagnosis_are_not_guessed(phrase, lang):
    result = normalized(source(phrase, lang))
    assert result.status == "unrecognized" and result.facts == []
    assert result.original_text == phrase


@pytest.mark.parametrize(
    "fault",
    [
        "extra",
        "field",
        "language",
        "schema",
        "diagnosis",
        "confidence",
        "nan",
        "certainty",
        "verification",
        "evidence",
        "empty",
        "duplicate",
        "wrong_status",
        "string",
        "provider_metadata",
    ],
)
def test_untrusted_provider_results_fail_closed(fault):
    data = valid_output()
    f = data["facts"][0]
    if fault == "extra":
        data["treatment"] = "invented advice"
    elif fault == "field":
        data["canonical_field"] = "allergies.details"
    elif fault == "language":
        data["language"] = "bn"
    elif fault == "schema":
        data["schema_version"] = "future"
    elif fault == "diagnosis":
        f["concept"] = "MYOCARDIAL_INFARCTION"
    elif fault == "confidence":
        f["confidence"] = 2.0
    elif fault == "nan":
        f["confidence"] = float("nan")
    elif fault == "certainty":
        f["certainty"] = "unknown"
    elif fault == "verification":
        f["verification_status"] = "clinician_verified"
    elif fault == "evidence":
        f["evidence"] = "words absent from source"
    elif fault == "empty":
        data["facts"] = []
    elif fault == "duplicate":
        data["facts"].append(copy.deepcopy(f))
    elif fault == "wrong_status":
        data["status"] = "unrecognized"
    elif fault == "string":
        data = "unstructured response"
    else:
        data["provider"] = "pretend clinician"
    result = normalized(provider=fake(data))
    assert result.status == "unavailable" and result.reason == "invalid_result"
    assert result.facts == [] and result.original_text == "chest pain"


def test_uncertainty_and_low_confidence_are_not_promoted():
    result = normalized(source("maybe chest pain"))
    assert result.facts[0].certainty == "uncertain"
    assert result.facts[0].verification_status == "needs_verification"
    data = valid_output()
    data["facts"][0]["confidence"] = 0.2
    assert normalized(provider=fake(data)).facts[0].verification_status == "needs_verification"


def test_timeout_unavailable_unsupported_and_no_exception_leak(caplog):
    async def slow(request):
        await asyncio.sleep(1)
        return valid_output()

    provider = fake()
    provider.normalize = slow
    assert normalized(provider=provider, timeout=0.01).reason == "timeout"
    result = normalized(provider=fake(error=RuntimeError("private patient/provider secret")))
    assert result.reason == "provider_unavailable"
    assert "private" not in result.model_dump_json() and "private" not in caplog.text
    assert normalized(source(language="fr")).reason == "unsupported_language"


def test_configuration_is_explicit_and_has_no_external_fallback(monkeypatch):
    monkeypatch.delenv("CLINICAL_NORMALIZATION_PROVIDER", raising=False)
    assert providers.configured_provider().name == "mock"
    monkeypatch.setenv("CLINICAL_NORMALIZATION_PROVIDER", "disabled")
    assert normalized().reason == "disabled"
    monkeypatch.setenv("CLINICAL_NORMALIZATION_PROVIDER", "external-vendor")
    with pytest.raises(ValueError, match="must be mock or disabled"):
        providers.validate_configuration()
    monkeypatch.setenv("CLINICAL_NORMALIZATION_PROVIDER", "mock")
    monkeypatch.setenv("CLINICAL_NORMALIZATION_TIMEOUT_SECONDS", "nan")
    with pytest.raises(ValueError):
        providers.validate_configuration()


def test_only_explicit_text_fields_are_eligible():
    for flow in registry().values():
        for _, q in flow.questions():
            if q.type != "short_text" or flow.namespace == "ayush_demo":
                assert not eligible(q)
    assert eligible(registry()["chest_pain"].questions()[0][1])


def test_typed_and_explicit_unknown_answers_bypass_provider(client, monkeypatch):
    provider = fake()
    monkeypatch.setattr(providers, "configured_provider", lambda: provider)
    session_id, state = selected(client)
    state = submit(client, session_id, state)
    assert state["active_answers"][0]["normalization"]["status"] == "unknown"
    state = submit(client, session_id, state, {"amount": 2, "unit": "days"}, "answered")
    assert state["active_answers"][-1]["normalization"] is None
    assert provider.normalize.await_count == 0


def test_source_edit_history_cache_and_flow_authority(client, database):
    session_id, state = selected(client, "fever", "bn")
    first_payload = payload(state, "বুকে ব্যথা", "answered", language="bn")
    url = f"/api/sessions/{session_id}/interview/answers"
    state = client.post(url, json=first_payload).json()
    old = state["active_answers"][0]["normalization"]
    assert state["flow_id"] == "fever" and state["question"]["question_id"] == "hpi.onset"
    assert old["facts"][0]["normalized_concept"] == "CHEST_PAIN"
    assert old["created_at"] and old["id"]
    assert client.post(url, json=first_payload).json() == state
    state = navigate(client, session_id, state, "chief_complaint.description")
    state = submit(client, session_id, state, "শ্বাসকষ্ট", "answered", language="bn")
    current = state["active_answers"][0]["normalization"]
    assert current["source_answer_id"] != old["source_answer_id"]
    assert current["facts"][0]["normalized_concept"] == "DYSPNEA"
    assert database.scalar(select(func.count()).select_from(models.NormalizationResult)) == 2
    assert database.get(models.NormalizationResult, old["id"]).result_json == old
    assert client.post(url, json=first_payload).json() == state
    assert client.get(f"/api/sessions/{session_id}/interview").json() == state
    for section in state["history"]["sections"]:
        for fact in section["facts"]:
            assert fact["answer_id"] != old["source_answer_id"]


def test_inactive_normalization_is_historical_and_reactivation_reuses_snapshot(client, database):
    session_id, state = selected(client)
    state = until(client, session_id, state, "hpi.radiation")
    state = submit(client, session_id, state, True, "answered")
    state = submit(client, session_id, state, "chest pain", "answered")
    norm = next(f for f in state["active_answers"] if f["question_id"] == "hpi.radiation_site")[
        "normalization"
    ]
    state = navigate(client, session_id, state, "hpi.radiation")
    state = submit(client, session_id, state, False, "answered")
    assert "hpi.radiation_site" in state["inactive_question_ids"]
    assert norm["id"] not in str(state["history"])
    assert database.get(models.NormalizationResult, norm["id"])
    state = navigate(client, session_id, state, "hpi.radiation")
    state = submit(client, session_id, state, True, "answered")
    assert state["current_answer"]["normalization"] == norm


@pytest.mark.parametrize("failure", ["unavailable", "timeout", "malformed", "disabled"])
def test_provider_failures_are_persisted_and_interview_continues(
    client, database, monkeypatch, failure
):
    provider = fake(error=RuntimeError())
    if failure == "malformed":
        provider = fake({"bad": "data"})
    if failure == "disabled":
        provider = providers.DisabledProvider()
    if failure == "timeout":

        async def slow(request):
            await asyncio.sleep(1)

        provider.normalize = slow
        monkeypatch.setattr(providers, "timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(providers, "configured_provider", lambda: provider)
    session_id, state = selected(client)
    state = submit(client, session_id, state, "chest pain", "answered")
    assert state["question"]["question_id"] == "hpi.onset"
    fact = state["active_answers"][0]
    assert fact["raw_value"] == "chest pain" and fact["value"] == "chest pain"
    assert fact["normalization"]["status"] == "unavailable"
    assert database.scalar(select(func.count()).select_from(models.NormalizationResult)) == 1


@pytest.mark.parametrize("operation", ["insert", "select"])
def test_normalization_storage_failure_does_not_rollback_patient_answer(
    client, database, operation
):
    session_id, state = selected(client)
    engine = database.get_bind().engine

    def fail(connection, cursor, statement, parameters, context, many):
        if "normalization_results" in statement and statement.lower().startswith(operation):
            raise SQLAlchemyError("synthetic normalization storage failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        state = submit(client, session_id, state, "chest pain", "answered")
        assert state["active_answers"][0]["raw_value"] == "chest pain"
        assert state["active_answers"][0]["normalization"]["status"] == "unavailable"
        assert state["question"]["question_id"] == "hpi.onset"
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 1


def test_completion_snapshot_and_confirmation_never_promote_machine_facts(client, database):
    session_id, state = selected(client)
    state = submit(client, session_id, state, "chest pain", "answered")
    while state["question"]:
        state = submit(client, session_id, state)
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 200
    before = client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR).json()
    norm = before["history"]["sections"][0]["facts"][0]["normalization"]
    base = f"/api/doctor/sessions/{session_id}/summary"
    assert (
        client.put(
            base,
            headers=DOCTOR,
            json={"reviewed_text": "Reviewed source words", "expected_version": 1},
        ).status_code
        == 200
    )
    assert (
        client.post(base + "/confirm", headers=DOCTOR, json={"expected_version": 2}).status_code
        == 200
    )
    after = client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR).json()
    assert after["history"]["sections"][0]["facts"][0]["normalization"] == norm
    assert (
        after["summary"]["generated_structured_json"]
        == before["summary"]["generated_structured_json"]
    )
    assert norm["facts"][0]["verification_status"] == "machine_normalized"
    count = database.scalar(select(func.count()).select_from(models.NormalizationResult))
    client.get(f"/api/sessions/{session_id}/interview")
    assert database.scalar(select(func.count()).select_from(models.NormalizationResult)) == count


def test_candidates_require_confirmation_and_are_not_activated():
    result = normalized()
    result.id = "normalization-id"
    candidates = service.complaint_candidates(result)
    assert candidates[0].flow_id == "chest_pain" and candidates[0].requires_confirmation
    result.canonical_field = "family_history.details"
    assert service.complaint_candidates(result) == []
