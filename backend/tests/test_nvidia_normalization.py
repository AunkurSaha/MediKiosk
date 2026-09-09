"""Offline contract/adversarial tests. No live API or real credentials."""

import asyncio
import copy
import json

import httpx2 as httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app import models
from app.schemas.normalization import Normalization, ProviderInput
from app.services import normalization_provider as providers
from app.services.nvidia_normalization import NvidiaClinicalNormalizationProvider, NvidiaSettings
from tests.test_adaptive import navigate, payload, selected, submit, until
from tests.test_normalization import normalized, source, valid_output
from tests.test_workflow import DOCTOR

SYNTHETIC_KEY = "synthetic-contract-key"


def output(text="chest pain", polarity="present", certainty="certain", concept="CHEST_PAIN"):
    result = valid_output()
    result["schema_version"] = "1.1"
    result["facts"][0].update(
        evidence=text, polarity=polarity, certainty=certainty, concept=concept
    )
    return result


def envelope(result=None, **choice_overrides):
    choice = {"finish_reason": "stop", "message": {"content": json.dumps(result or output())}}
    choice.update(choice_overrides)
    return {
        "choices": [choice],
        "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
    }


def adapter(handler=None):
    return NvidiaClinicalNormalizationProvider(
        NvidiaSettings(api_key=SecretStr(SYNTHETIC_KEY), timeout=0.2),
        transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json=envelope()))),
    )


def test_configuration_and_secret_serialization(monkeypatch):
    monkeypatch.delenv("CLINICAL_NORMALIZATION_PROVIDER", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert providers.configured_provider().name == "mock"
    monkeypatch.setenv("CLINICAL_NORMALIZATION_PROVIDER", "nvidia")
    assert normalized().reason == "missing_api_key"
    monkeypatch.setenv("NVIDIA_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("CLINICAL_NORMALIZATION_MODEL", "operator/selected-model")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://nim.synthetic.invalid/v1/")
    provider = providers.configured_provider()
    assert provider.model == "operator/selected-model"
    assert provider.settings.base_url == "https://nim.synthetic.invalid/v1"
    assert SYNTHETIC_KEY not in provider.settings.model_dump_json()
    assert "api_key" not in provider.settings.model_dump()
    assert SYNTHETIC_KEY not in repr(provider.settings)


def test_source_commit_precedes_provider_and_optional_commit_failure_preserves_answer(
    client, database, monkeypatch
):
    sid, state = selected(client)
    commits = []
    original_commit = database.commit

    def commit():
        commits.append(True)
        if len(commits) == 2:
            raise RuntimeError("synthetic enrichment commit failure")
        original_commit()

    def handler(request):
        assert len(commits) == 1
        return httpx.Response(200, json=envelope())

    monkeypatch.setattr(database, "commit", commit)
    monkeypatch.setattr(providers, "configured_provider", lambda: adapter(handler))
    state = submit(client, sid, state, "chest pain", "answered")
    assert state["active_answers"][0]["raw_value"] == "chest pain"
    assert state["question"]["question_id"] == "hpi.onset"
    assert state["active_answers"][0]["normalization"]["reason"] == "not_processed"


def test_completed_snapshot_is_not_enriched_in_post_commit_gap(client, database, monkeypatch):
    from app.services.flow_registry import registry
    from app.services.normalization import persist_committed

    sid, state = selected(client)
    state = submit(client, sid, state, "chest pain", "answered")
    answer = database.get(models.InterviewAnswer, state["active_answers"][0]["answer_id"])
    session = database.get(models.Session, sid)
    session.status = "confirmed"
    database.commit()

    def forbidden(request):
        raise AssertionError("Completed record must not call provider")

    monkeypatch.setattr(providers, "configured_provider", lambda: adapter(forbidden))
    flow = registry()["chest_pain"]
    before = copy.deepcopy(
        database.get(
            models.NormalizationResult, state["active_answers"][0]["normalization"]["id"]
        ).result_json
    )
    persist_committed(database, answer, flow.questions()[0][1], flow)
    assert database.get(models.NormalizationResult, before["id"]).result_json == before


@pytest.mark.parametrize(
    "key,value",
    [
        ("NVIDIA_BASE_URL", "http://unsafe.invalid/v1"),
        ("NVIDIA_BASE_URL", "https://secret@nim.invalid/v1"),
        ("NVIDIA_BASE_URL", "https://nim.invalid/v1?key=secret"),
        ("CLINICAL_NORMALIZATION_MODEL", ""),
        ("CLINICAL_NORMALIZATION_MAX_TOKENS", "16000"),
        ("CLINICAL_NORMALIZATION_MAX_TOKENS", "secret"),
        ("CLINICAL_NORMALIZATION_TIMEOUT_SECONDS", "infinity"),
        ("CLINICAL_NORMALIZATION_TIMEOUT_SECONDS", "secret"),
    ],
)
def test_bad_configuration_rejected_without_echo(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as exc:
        NvidiaSettings.from_environment()
    assert "secret" not in str(exc.value)


def test_minimal_request_settings_and_no_context_identifiers(caplog):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=envelope())

    provider = adapter(handler)
    request = ProviderInput(
        text="chest pain",
        language="en",
        canonical_field="chief_complaint.description",
        context={
            "patient_name": "DO_NOT_SEND",
            "session_id": "DO_NOT_SEND",
            "flow_id": "DO_NOT_SEND",
        },
    )
    asyncio.run(provider.normalize(request))
    sent = captured[0]
    body = json.loads(sent.content)
    assert str(sent.url) == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert sent.headers["authorization"] == "Bearer " + SYNTHETIC_KEY
    assert body["model"] == "google/gemma-4-31b-it"
    assert body["temperature"] == 0 and body["stream"] is False
    assert body["max_tokens"] == 768 and body["chat_template_kwargs"] == {"enable_thinking": False}
    assert json.loads(body["messages"][1]["content"]) == {
        "text": "chest pain",
        "language": "en",
        "canonical_field": "chief_complaint.description",
    }
    assert "DO_NOT_SEND" not in str(body) and SYNTHETIC_KEY not in str(body)
    assert SYNTHETIC_KEY not in caplog.text and "chest pain" not in caplog.text
    assert provider.token_usage.total_tokens == 140 and provider.latency_ms >= 0


@pytest.mark.parametrize(
    "polarity,certainty,expected",
    [
        ("present", "certain", True),
        ("absent", "certain", False),
        ("present", "uncertain", None),
        ("absent", "uncertain", None),
    ],
)
def test_polarity_certainty_value_and_provenance(polarity, certainty, expected):
    text = "I do not have chest pain." if polarity == "absent" else "I think I have chest pain."
    provider = adapter(
        lambda r: httpx.Response(200, json=envelope(output(text, polarity, certainty)))
    )
    result = normalized(source(text), provider)
    assert result.status == "normalized"
    fact = result.facts[0]
    assert fact.polarity == polarity and fact.certainty == certainty
    assert fact.normalized_value is expected and fact.confidence is None
    assert result.model == provider.model and result.prompt_version == "nvidia-1.0"
    assert result.provider == "nvidia" and result.schema_version == "1.1"
    if certainty == "uncertain":
        assert fact.verification_status == "needs_verification"


@pytest.mark.parametrize(
    "fault",
    [
        "diagnosis",
        "extra",
        "confidence",
        "polarity_missing",
        "polarity_invalid",
        "schema_old",
        "evidence",
        "duplicate",
        "field",
        "language",
        "certainty",
        "empty_facts",
    ],
)
def test_invalid_live_domain_output_rejected(fault):
    data = output()
    fact = data["facts"][0]
    if fault == "diagnosis":
        fact["concept"] = "PNEUMONIA"
    elif fault == "extra":
        data["treatment"] = "invented"
    elif fault == "confidence":
        fact["confidence"] = 0.92
    elif fault == "polarity_missing":
        del fact["polarity"]
    elif fault == "polarity_invalid":
        fact["polarity"] = "positive"
    elif fault == "schema_old":
        data["schema_version"] = "1.0"
    elif fault == "evidence":
        fact["evidence"] = "not in source"
    elif fault == "duplicate":
        data["facts"].append(copy.deepcopy(fact))
    elif fault == "field":
        data["canonical_field"] = "family_history.details"
    elif fault == "language":
        data["language"] = "bn"
    elif fault == "certainty":
        fact["certainty"] = "unknown"
    else:
        data["facts"] = []
    result = normalized(provider=adapter(lambda r: httpx.Response(200, json=envelope(data))))
    assert result.reason == "invalid_result" and not result.facts


@pytest.mark.parametrize(
    "content",
    [
        "",
        "plain prose",
        "```json\n{}\n```",
        '{"status":"unknown","status":"normalized"}',
        "NaN",
        "[]",
        "null",
        "{",
    ],
)
def test_malformed_or_empty_content_never_repaired(content):
    provider = adapter(lambda r: httpx.Response(200, json=envelope(message={"content": content})))
    assert normalized(provider=provider).reason == "invalid_result"


@pytest.mark.parametrize(
    "status,reason",
    [
        (401, "authentication_failed"),
        (403, "authentication_failed"),
        (429, "rate_limited"),
        (500, "server_error"),
        (503, "server_error"),
        (202, "provider_unavailable"),
        (302, "provider_unavailable"),
        (422, "provider_unavailable"),
    ],
)
def test_http_failure_no_retry_no_leak(client, database, monkeypatch, caplog, status, reason):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="private patient text " + SYNTHETIC_KEY,
            headers={"location": "https://never-follow.invalid", "retry-after": "3600"},
        )

    provider = adapter(handler)
    monkeypatch.setattr(providers, "configured_provider", lambda: provider)
    sid, state = selected(client)
    state = submit(client, sid, state, "chest pain", "answered")
    fact = state["active_answers"][0]
    assert fact["raw_value"] == "chest pain" and state["question"]["question_id"] == "hpi.onset"
    assert fact["normalization"]["reason"] == reason
    row = database.get(models.NormalizationResult, fact["normalization"]["id"])
    assert row.result_json["model"] == provider.model
    assert len(calls) == 1
    assert SYNTHETIC_KEY not in json.dumps(state) + caplog.text
    assert "private patient text" not in json.dumps(state) + caplog.text
    assert SYNTHETIC_KEY not in client.get("/api/config").text


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("network", "network_error"),
        ("transport_timeout", "timeout"),
        ("deadline", "timeout"),
        ("truncated", "truncated_response"),
        ("outer_json", "invalid_result"),
        ("huge", "invalid_result"),
        ("tool", "invalid_result"),
    ],
)
def test_transport_and_response_failures_persist(client, database, monkeypatch, kind, reason):
    async def handler(request):
        if kind == "network":
            raise httpx.ConnectError("private", request=request)
        if kind == "transport_timeout":
            raise httpx.ReadTimeout("private", request=request)
        if kind == "deadline":
            await asyncio.sleep(1)
        if kind == "outer_json":
            return httpx.Response(200, text="private non-JSON")
        if kind == "huge":
            return httpx.Response(200, content=b"x" * 65537)
        return httpx.Response(
            200, json=envelope(finish_reason="length" if kind == "truncated" else "tool_calls")
        )

    provider = adapter(handler)
    monkeypatch.setattr(providers, "configured_provider", lambda: provider)
    monkeypatch.setattr(providers, "timeout_seconds", lambda: 0.02)
    sid, state = selected(client)
    state = submit(client, sid, state, "chest pain", "answered")
    fact = state["active_answers"][0]
    assert fact["normalization"]["reason"] == reason
    assert database.get(models.InterviewAnswer, fact["answer_id"]).raw_value == "chest pain"
    assert database.get(models.NormalizationResult, fact["normalization"]["id"])


def test_live_source_edit_branch_reactivation_and_confirmed_immutability(
    client, database, monkeypatch
):
    def handler(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        result = output(data["text"])
        result["canonical_field"] = data["canonical_field"]
        return httpx.Response(200, json=envelope(result))

    monkeypatch.setattr(providers, "configured_provider", lambda: adapter(handler))
    sid, state = selected(client, "chest_pain")
    first_payload = payload(state, "chest pain", "answered")
    state = client.post(f"/api/sessions/{sid}/interview/answers", json=first_payload).json()
    old = state["active_answers"][0]["normalization"]
    state = navigate(client, sid, state, "chief_complaint.description")
    state = submit(client, sid, state, "I have chest pain", "answered")
    new = state["active_answers"][0]["normalization"]
    assert old["source_answer_id"] != new["source_answer_id"]
    assert database.get(models.NormalizationResult, old["id"]).result_json == old
    assert client.post(f"/api/sessions/{sid}/interview/answers", json=first_payload).json() == state
    state = until(client, sid, state, "hpi.radiation")
    state = submit(client, sid, state, True, "answered")
    state = submit(client, sid, state, "chest pain", "answered")
    branch = next(
        f["normalization"]
        for f in state["active_answers"]
        if f["question_id"] == "hpi.radiation_site"
    )
    state = navigate(client, sid, state, "hpi.radiation")
    state = submit(client, sid, state, False, "answered")
    assert branch["id"] not in str(state["history"])
    state = navigate(client, sid, state, "hpi.radiation")
    state = submit(client, sid, state, True, "answered")
    assert state["current_answer"]["normalization"] == branch
    while state["question"]:
        state = submit(client, sid, state)
    assert client.post(f"/api/sessions/{sid}/complete").status_code == 200
    url = f"/api/doctor/sessions/{sid}"
    before = client.get(url, headers=DOCTOR).json()
    assert (
        client.put(
            url + "/summary",
            headers=DOCTOR,
            json={"reviewed_text": "Synthetic review", "expected_version": 1},
        ).status_code
        == 200
    )
    assert (
        client.post(
            url + "/summary/confirm", headers=DOCTOR, json={"expected_version": 2}
        ).status_code
        == 200
    )
    after = client.get(url, headers=DOCTOR).json()
    assert before["history"] == after["history"]
    assert (
        before["summary"]["generated_structured_json"]
        == after["summary"]["generated_structured_json"]
    )
    assert (
        client.put(
            url + "/summary",
            headers=DOCTOR,
            json={"reviewed_text": "Change", "expected_version": 3},
        ).status_code
        == 409
    )


def test_legacy_snapshot_defaults_do_not_mutate_stored_json(client, database):
    sid, state = selected(client)
    state = submit(client, sid, state, "chest pain", "answered")
    norm = state["active_answers"][0]["normalization"]
    legacy = copy.deepcopy(norm)
    for key in ("model", "prompt_version", "latency_ms", "token_usage"):
        legacy.pop(key, None)
    legacy["facts"][0].pop("polarity")
    row = database.get(models.NormalizationResult, norm["id"])
    row.result_json = legacy
    database.commit()
    assert Normalization.model_validate(legacy).facts[0].polarity == "present"
    assert client.get(f"/api/sessions/{sid}/interview").status_code == 200
    database.expire_all()
    assert (
        database.scalar(
            select(models.NormalizationResult).where(models.NormalizationResult.id == norm["id"])
        ).result_json
        == legacy
    )


@pytest.mark.parametrize("status", ["unknown", "unrecognized"])
def test_empty_domain_states_and_negated_candidates(status):
    data = output()
    data.update(status=status, facts=[])
    assert (
        normalized(provider=adapter(lambda r: httpx.Response(200, json=envelope(data)))).status
        == status
    )
    from app.services.normalization import complaint_candidates

    result = normalized(
        provider=adapter(lambda r: httpx.Response(200, json=envelope(output(polarity="absent"))))
    )
    result.id = "synthetic-result"
    assert complaint_candidates(result) == []
