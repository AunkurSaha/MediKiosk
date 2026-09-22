import copy
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import models
from app.schemas.adaptive import Fact, Submission
from app.schemas.flow import Flow
from app.services.flow_registry import load_flows, registry
from app.services.interview_engine import InterviewEngine
from tests.test_workflow import DOCTOR, answer, consent, create


def selected(client, flow_id="chest_pain", language="en"):
    session_id, _ = create(client, language)
    consent(client, session_id)
    response = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": flow_id})
    assert response.status_code == 200, response.text
    return session_id, response.json()


def payload(state, value=None, status="unknown", language="en", **overrides):
    body = {
        "request_id": str(uuid4()),
        "expected_revision": state["revision"],
        "question_id": state["question"]["question_id"],
        "status": status,
        "value": value,
        "raw_value": str(value) if value is not None else "Unknown",
        "source": "typed",
        "language": language,
    }
    body.update(overrides)
    return body


def submit(client, session_id, state, value=None, status="unknown", **overrides):
    response = client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json=payload(state, value, status, **overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()


def until(client, session_id, state, question_id):
    for _ in range(100):
        if state["question"]["question_id"] == question_id:
            return state
        state = submit(client, session_id, state)
    pytest.fail(f"Question {question_id} not reached")


def navigate(client, session_id, state, question_id):
    response = client.put(
        f"/api/sessions/{session_id}/interview/cursor",
        json={
            "question_id": question_id,
            "expected_revision": state["revision"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_registry_all_valid_and_ayush_separate():
    flows = load_flows()
    assert len(flows) == 8
    assert len([f for f in flows.values() if f.namespace == "standard"]) == 5
    assert len([f for f in flows.values() if f.namespace == "other"]) == 1
    ayush = flows["ayush_demo.history"]
    assert len(ayush.questions()) == 11
    assert all(s.section_id == "ayush_demo" for s, _ in ayush.questions())
    for flow in flows.values():
        for _, q in flow.questions():
            assert all(q.text.model_dump().values())
            assert "Eliminate" not in q.text.model_dump_json()


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed",
        "duplicate",
        "reference",
        "cycle",
        "dependency",
        "operator",
        "option",
        "translation",
        "section",
        "namespace",
        "bounds",
        "completion",
        "unknown_key",
    ],
)
def test_bad_configuration_fails_clearly(tmp_path, mutation):
    config = copy.deepcopy(registry()["chest_pain"].model_dump(mode="json"))
    questions = config["sections"][1]["questions"]
    conditional = next(q for q in questions if q["when"])
    if mutation == "malformed":
        (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    else:
        if mutation == "duplicate":
            questions.append(copy.deepcopy(questions[0]))
        elif mutation in ("reference", "cycle"):
            conditional["when"][0]["question_id"] = (
                "missing" if mutation == "reference" else conditional["question_id"]
            )
            conditional["depends_on"] = [conditional["when"][0]["question_id"]]
        elif mutation == "dependency":
            conditional["depends_on"] = []
        elif mutation == "operator":
            conditional["when"][0]["operator"] = "contains"
        elif mutation == "option":
            choice = next(q for q in questions if q["options"])
            choice["options"].append(copy.deepcopy(choice["options"][0]))
        elif mutation == "translation":
            del questions[0]["text"]["bn"]
        elif mutation == "section":
            questions[0]["field"] = "medications.bad"
        elif mutation == "namespace":
            config["namespace"] = "ayush_demo"
        elif mutation == "bounds":
            questions[0]["constraints"].update(minimum=5, maximum=1)
        elif mutation == "completion":
            config["completion"] = "anything"
        else:
            config["script"] = "eval()"
        (tmp_path / "broken.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid complaint flow broken.json"):
        load_flows(tmp_path)


def test_duplicate_flow_and_empty_registry_fail(tmp_path):
    with pytest.raises(ValueError, match="No complaint"):
        load_flows(tmp_path)
    text = registry()["fever"].model_dump_json()
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate flow ID"):
        load_flows(tmp_path)


@pytest.mark.parametrize(
    "flow_id",
    [
        "chest_pain",
        "abdominal_pain",
        "fever",
        "headache",
        "cough_breathlessness",
        "ayush_demo.history",
    ],
)
def test_all_flows_traverse_complete_review_confirm(client, flow_id):
    session_id, state = selected(client, flow_id)
    seen = []
    assert not state["is_complete"] and state["missing_required"]
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 422
    for _ in range(100):
        question = state["question"]
        if question is None:
            break
        seen.append(question["question_id"])
        if question["type"] == "boolean":
            state = submit(client, session_id, state, False, "answered")
        elif not question["required"]:
            state = submit(client, session_id, state, status="skipped", raw_value="Skipped")
        else:
            state = submit(client, session_id, state)
    assert state["is_complete"] and not state["missing_required"]
    assert len(seen) == len(set(seen))
    assert "past_medical_history.diabetes_duration" not in seen
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 200
    response = client.get(f"/api/doctor/sessions/{session_id}", headers=DOCTOR)
    data = response.json()
    assert data["history"]["flow_id"] == flow_id
    structured = json.loads(data["summary"]["generated_structured_json"])
    assert structured == data["history"]
    base = f"/api/doctor/sessions/{session_id}/summary"
    assert (
        client.put(
            base, headers=DOCTOR, json={"reviewed_text": "Synthetic review", "expected_version": 1}
        ).status_code
        == 200
    )
    assert (
        client.post(base + "/confirm", headers=DOCTOR, json={"expected_version": 2}).status_code
        == 200
    )
    assert (
        client.put(
            f"/api/sessions/{session_id}/interview/cursor",
            json={"question_id": seen[0], "expected_revision": state["revision"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/sessions/{session_id}/interview/answers",
            json=payload({**state, "question": {"question_id": seen[0]}}),
        ).status_code
        == 409
    )


def test_branch_edit_preserves_audit_excludes_inactive_restores_and_resumes(client, database):
    session_id, state = selected(client)
    parent = "past_medical_history.diabetes"
    child = "past_medical_history.diabetes_duration"
    state = until(client, session_id, state, parent)
    state = submit(client, session_id, state, True, "answered")
    assert state["question"]["question_id"] == child
    state = submit(
        client,
        session_id,
        state,
        {"amount": 3, "unit": "years"},
        "answered",
        raw_value="three years",
    )
    child_fact = next(a for a in state["active_answers"] if a["question_id"] == child)
    state = submit(client, session_id, state, "Synthetic diabetes care", "answered")
    state = navigate(client, session_id, state, parent)
    assert state["current_answer"]["value"] is True
    before = database.scalar(select(func.count()).select_from(models.InterviewAnswer))
    state = submit(client, session_id, state, False, "answered")
    assert child in state["inactive_question_ids"]
    assert "Synthetic diabetes care" not in json.dumps(state["history"])
    assert not any(a["question_id"] == child for a in state["active_answers"])
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == before + 1
    assert client.get(f"/api/sessions/{session_id}/interview").json() == state
    assert not any(
        a["question_id"] == child for a in client.get(f"/api/sessions/{session_id}/answers").json()
    )
    assert (
        client.put(
            f"/api/sessions/{session_id}/interview/cursor",
            json={"question_id": child, "expected_revision": state["revision"]},
        ).status_code
        == 422
    )
    state = navigate(client, session_id, state, parent)
    state = submit(client, session_id, state, True, "answered")
    assert state["question"]["question_id"] == child
    assert state["current_answer"]["answer_id"] == child_fact["answer_id"]
    assert state["current_answer"]["raw_value"] == "three years"
    assert state["current_answer"]["source"] == "typed"


def test_retry_receipt_delayed_retry_and_optimistic_conflict(client, database):
    session_id, state = selected(client)
    body = payload(state, "Original words", "answered")
    url = f"/api/sessions/{session_id}/interview/answers"
    first = client.post(url, json=body).json()
    assert client.post(url, json=body).json() == first
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 1
    state = navigate(client, session_id, first, body["question_id"])
    corrected = submit(client, session_id, state, "Corrected words", "answered")
    # A lost response from the first save may arrive after the correction.
    assert client.post(url, json=body).json() == corrected
    assert (
        client.get(f"/api/sessions/{session_id}").json()["answers"][0]["value"] == "Corrected words"
    )
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 2
    assert client.post(url, json={**body, "raw_value": "Other"}).status_code == 409
    assert (
        client.post(url, json={**body, "request_id": str(uuid4())}).json()["error"]["code"]
        == "INTERVIEW_CONFLICT"
    )


def test_consent_selection_and_legacy_endpoint_guards(client):
    session_id, _ = create(client)
    url = f"/api/sessions/{session_id}/interview"
    assert client.get(url).status_code == 403
    assert client.put(url + "/flow", json={"flow_id": "fever"}).status_code == 403
    consent(client, session_id)
    state = client.get(url).json()
    assert state["selection_required"] and len(state["flows"]) == 7
    assert client.put(url + "/flow", json={"flow_id": "legacy.intake"}).status_code == 422
    assert client.put(url + "/flow", json={"flow_id": "missing"}).status_code == 422
    assert (
        client.post(
            url + "/answers", json=payload({"revision": 0, "question": {"question_id": "anything"}})
        ).status_code
        == 422
    )
    assert client.put(url + "/flow", json={"flow_id": "fever"}).status_code == 200
    assert client.put(url + "/flow", json={"flow_id": "fever"}).status_code == 200
    assert client.put(url + "/flow", json={"flow_id": "headache"}).status_code == 409
    assert answer(client, session_id).status_code == 409


def test_legacy_resume_uses_server_config_and_preserves_original(client, database):
    session_id, _ = create(client)
    consent(client, session_id)
    answer(client, session_id, value="Phase 1 wording")
    state = client.get(f"/api/sessions/{session_id}/interview").json()
    assert state["flow_id"] == "legacy.intake"
    assert state["question"]["question_id"] == "onset_duration"
    while state["question"]:
        state = submit(client, session_id, state)
    assert client.post(f"/api/sessions/{session_id}/complete").status_code == 200
    assert database.scalar(select(func.count()).select_from(models.InterviewAnswer)) == 5
    assert (
        client.get(f"/api/sessions/{session_id}").json()["answers"][0]["raw_value"]
        == "Phase 1 wording"
    )


@pytest.mark.parametrize(
    "language,words",
    [("en", "  Original patient words  "), ("bn", "আমার নিজের কথা"), ("hi", "मेरे अपने शब्द")],
)
def test_language_raw_wording_and_pinned_version(client, database, language, words):
    session_id, state = selected(client, language=language)
    state = submit(client, session_id, state, words, "answered", language=language)
    assert state["active_answers"][0]["raw_value"] == words
    pinned = database.get(models.InterviewRun, session_id).flow_snapshot
    assert pinned["version"] == "1.0.0"
    assert state["question"]["text"][language]
    assert (
        client.post(
            f"/api/sessions/{session_id}/interview/answers",
            json=payload(state, language="hi" if language != "hi" else "bn"),
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "kind,value,valid",
    [
        ("boolean", True, True),
        ("boolean", "true", False),
        ("boolean", 1, False),
        ("short_text", "words", True),
        ("short_text", "", False),
        ("short_text", " " * 2, False),
        ("number", 38.5, True),
        ("number", -1, False),
        ("number", True, False),
        ("duration", {"amount": 2, "unit": "days"}, True),
        ("duration", {"amount": -1, "unit": "days"}, False),
        ("duration", {"amount": 2, "unit": "centuries"}, False),
        ("severity", 10, True),
        ("severity", 11, False),
        ("severity", 1.5, False),
        ("single_choice", "constant", True),
        ("single_choice", ["constant"], False),
        ("single_choice", "arbitrary", False),
        ("multiple_choice", ["cough", "headache"], True),
        ("multiple_choice", ["none", "cough"], False),
        ("multiple_choice", ["cough", "cough"], False),
        ("multiple_choice", [], False),
        ("multiple_choice", "cough", False),
    ],
)
def test_answer_types_and_constraints(kind, value, valid):
    from app.core.errors import WorkflowError
    from app.services.interview_engine import validate_answer

    question = next(
        q for flow in registry().values() for _, q in flow.questions() if q.type == kind
    )
    try:
        body = Submission.model_validate(
            {
                "request_id": str(uuid4()),
                "expected_revision": 0,
                "question_id": question.question_id,
                "value": value,
                "status": "answered",
                "raw_value": value if isinstance(value, str) and value else "reported",
                "source": "typed",
                "language": "en",
            }
        )
        validate_answer(question, body)
        assert valid
    except (ValidationError, WorkflowError):
        assert not valid


def test_unknown_optional_required_and_determinism(client):
    session_id, state = selected(client)
    url = f"/api/sessions/{session_id}/interview/answers"
    assert client.post(url, json=payload(state, status="skipped")).status_code == 422
    assert (
        client.post(url, json=payload(state, value="not null", status="unknown")).status_code == 422
    )
    state = submit(
        client, session_id, state, status="not_reported", raw_value="Prefer not to report"
    )
    state = until(client, session_id, state, "hpi.associated_details")
    assert not state["question"]["required"]
    state = submit(client, session_id, state, status="skipped", raw_value="Skipped optional")
    assert any(a["status"] == "skipped" for a in state["active_answers"])
    flow = registry()["chest_pain"]
    facts = {a["question_id"]: Fact.model_validate(a) for a in state["active_answers"]}
    evaluations = [InterviewEngine(flow, facts).state().model_dump_json() for _ in range(10)]
    assert len(set(evaluations)) == 1


def test_contains_condition_and_inactive_parent_do_not_activate_descendant():
    config = registry()["fever"].model_dump(mode="json")
    qs = config["sections"][1]["questions"]
    child = next(q for q in qs if q["question_id"] == "hpi.associated_details")
    child["depends_on"] = ["hpi.associated"]
    child["when"] = [{"question_id": "hpi.associated", "operator": "contains", "value": "cough"}]
    flow = Flow.model_validate(config)
    q = next(q for _, q in flow.questions() if q.question_id == "hpi.associated")
    fact = Fact(
        answer_id="a",
        question_id=q.question_id,
        field=q.field,
        label=q.text,
        status="answered",
        value=["cough"],
        raw_value="Cough",
        source="touch",
        language="en",
        recorded_at="2026-09-09T00:00:00Z",
    )
    assert "hpi.associated_details" in InterviewEngine(flow, {q.question_id: fact}).pending
    assert "hpi.associated_details" not in InterviewEngine(flow, {}).pending


def _fever_fact(question_id, value, raw_value="reported"):
    flow = registry()["fever"]
    question = next(q for _, q in flow.questions() if q.question_id == question_id)
    return Fact(
        answer_id=str(uuid4()),
        question_id=question_id,
        field=question.field,
        label=question.text,
        status="answered",
        value=value,
        raw_value=raw_value,
        source="touch",
        language="en",
        recorded_at="2026-09-22T00:00:00Z",
    )


def test_fever_routine_core_is_minimum_necessary_after_rapid_and_document_coverage():
    flow = registry()["fever"]
    answers = {
        "chief_complaint.description": _fever_fact(
            "chief_complaint.description", "Fever since yesterday with chills and body ache."
        ),
        "hpi.temperature": _fever_fact("hpi.temperature", 38, "38"),
        "medications.any": _fever_fact("medications.any", True, "Yes"),
        "medications.details": _fever_fact(
            "medications.details", "Metformin 500 mg Twice Daily", "Metformin 500 mg Twice Daily"
        ),
    }
    expected = [
        "hpi.onset",
        "hpi.timing",
        "hpi.associated",
        "past_medical_history.conditions",
        "allergies.any",
        "review_of_systems.details",
    ]

    assert InterviewEngine(flow, answers).pending == expected


@pytest.mark.parametrize(
    "selected,expected_child",
    [
        (["cough"], "hpi.associated_details"),
        (["gastrointestinal"], "hpi.gastrointestinal_details"),
        (["urinary"], "hpi.urinary_details"),
        (["rash"], "hpi.rash_details"),
    ],
)
def test_fever_only_selected_symptom_branch_activates(selected, expected_child):
    flow = registry()["fever"]
    engine = InterviewEngine(
        flow, {"hpi.associated": _fever_fact("hpi.associated", selected)}
    )
    symptom_children = {
        "hpi.associated_details",
        "hpi.gastrointestinal_details",
        "hpi.abdominal_details",
        "hpi.urinary_details",
        "hpi.rash_details",
    }

    assert set(engine.pending).intersection(symptom_children) == {expected_child}


def test_fever_none_selected_suppresses_all_symptom_children():
    flow = registry()["fever"]
    engine = InterviewEngine(
        flow, {"hpi.associated": _fever_fact("hpi.associated", ["none"])}
    )

    assert not {
        "hpi.associated_details",
        "hpi.gastrointestinal_details",
        "hpi.abdominal_details",
        "hpi.urinary_details",
        "hpi.rash_details",
    }.intersection(engine.pending)


def test_saved_flow_snapshot_survives_registry_change(client, monkeypatch):
    session_id, before = selected(client)
    changed = registry()["chest_pain"].model_copy(deep=True)
    changed.version = "9.0.0"
    changed.sections[0].questions[0].text.en = "New wording for future intakes"
    monkeypatch.setitem(registry(), "chest_pain", changed)
    assert client.get(f"/api/sessions/{session_id}/interview").json() == before


def test_latest_answers_stay_in_configuration_order_after_correction(client):
    session_id, state = selected(client)
    state = submit(client, session_id, state, "First words", "answered")
    state = submit(client, session_id, state)
    state = navigate(client, session_id, state, "chief_complaint.description")
    state = submit(client, session_id, state, "Corrected words", "answered")
    answers = client.get(f"/api/sessions/{session_id}/answers").json()
    assert [a["question_id"] for a in answers] == ["chief_complaint.description", "hpi.onset"]
    assert answers[0]["raw_value"] == "Corrected words"


def test_unknown_parent_deactivates_and_completion_recalculates(client):
    session_id, state = selected(client)
    state = until(client, session_id, state, "past_medical_history.diabetes")
    state = submit(client, session_id, state, True, "answered")
    assert "past_medical_history.diabetes_duration" in state["missing_required"]
    state = navigate(client, session_id, state, "past_medical_history.diabetes")
    state = submit(client, session_id, state)
    assert "past_medical_history.diabetes_duration" not in state["missing_required"]
    assert not state["is_complete"]


def test_server_rejects_future_question_and_forged_provenance(client):
    session_id, state = selected(client)
    url = f"/api/sessions/{session_id}/interview"
    assert (
        client.post(
            url + "/answers", json=payload(state, question_id="past_medical_history.diabetes")
        ).status_code
        == 409
    )
    assert (
        client.put(
            url + "/cursor",
            json={"question_id": "past_medical_history.diabetes", "expected_revision": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url + "/answers", json=payload(state, verification_status="clinician_verified")
        ).status_code
        == 422
    )
    assert client.post(url + "/answers", json=payload(state, source="clinician")).status_code == 422
