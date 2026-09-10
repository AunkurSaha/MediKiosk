from datetime import datetime, timezone

from app import models
from app.schemas.adaptive import Fact
from app.schemas.normalization import Normalization, NormalizedFact
from app.services.red_flags import (
    evaluate_and_persist,
    evaluate_rules,
    get_rule_catalog,
    get_session_alerts,
)
from tests.test_adaptive import selected, submit, until
from tests.test_workflow import DOCTOR


def _make_fact(
    field: str,
    value: object,
    raw_value: str = "",
    status: str = "answered",
    normalized_concepts: list[str] | None = None,
) -> Fact:
    norm = None
    if normalized_concepts:
        norm = Normalization(
            source_answer_id="ans-1",
            source_question_id=field.replace(".", "_"),
            canonical_field=field,
            original_language="en",
            original_text=raw_value or str(value),
            status="normalized",
            facts=[
                NormalizedFact(
                    normalized_concept=c,
                    normalized_display=c.replace("_", " ").title(),
                    normalized_value=True,
                    polarity="present",
                    evidence=raw_value or str(value),
                    confidence=0.95,
                    certainty="certain",
                    verification_status="machine_normalized",
                )
                for c in normalized_concepts
            ],
        )
    return Fact(
        answer_id="ans-1",
        question_id=field.replace(".", "_"),
        field=field,
        label={"en": field, "bn": field, "hi": field},
        value=value,
        raw_value=raw_value or str(value),
        source="typed",
        language="en",
        status=status,
        recorded_at=datetime.now(timezone.utc),
        normalization=norm,
    )


def test_rule_catalog_loads():
    catalog = get_rule_catalog()
    assert catalog.schema_version == "1.0"
    assert len(catalog.rules) == 11
    rule_ids = {r.rule_id for r in catalog.rules}
    assert "RF-CHEST-001" in rule_ids
    assert "RF-RESP-001" in rule_ids
    assert "RF-FEV-001" in rule_ids
    assert "RF-HEAD-001" in rule_ids
    assert "RF-ABD-001" in rule_ids


# 1. RF-CHEST-001: severe radiating chest pain (emergency)
def test_rf_chest_001_trigger():
    facts = [
        _make_fact("hpi.severity", 8),
        _make_fact("hpi.radiation", True),
    ]
    triggered = evaluate_rules("chest_pain", facts)
    matched = [r for r, _ in triggered if r.rule_id == "RF-CHEST-001"]
    assert len(matched) == 1
    assert matched[0].priority == "emergency"


def test_rf_chest_001_boundary_and_negative():
    # Severity 7 is below threshold 8
    facts = [
        _make_fact("hpi.severity", 7),
        _make_fact("hpi.radiation", True),
    ]
    triggered = evaluate_rules("chest_pain", facts)
    assert not any(r.rule_id == "RF-CHEST-001" for r, _ in triggered)

    # Severity 8 but no radiation
    facts2 = [
        _make_fact("hpi.severity", 8),
        _make_fact("hpi.radiation", False),
    ]
    assert not any(r.rule_id == "RF-CHEST-001" for r, _ in evaluate_rules("chest_pain", facts2))


# 2. RF-CHEST-002: concept:DYSPNEA (urgent)
def test_rf_chest_002_trigger():
    facts = [
        _make_fact("hpi.associated_details", "shortness of breath", normalized_concepts=["DYSPNEA"])
    ]
    triggered = evaluate_rules("chest_pain", facts)
    matched = [r for r, _ in triggered if r.rule_id == "RF-CHEST-002"]
    assert len(matched) == 1
    assert matched[0].priority == "urgent"


# 3. RF-CHEST-003: any_concept in SWEATING, DIZZINESS (urgent)
def test_rf_chest_003_trigger():
    facts = [
        _make_fact("hpi.associated_details", "sweating", normalized_concepts=["SWEATING"])
    ]
    triggered = evaluate_rules("chest_pain", facts)
    matched = [r for r, _ in triggered if r.rule_id == "RF-CHEST-003"]
    assert len(matched) == 1
    assert matched[0].priority == "urgent"


# 4. RF-RESP-001: breathlessness constant (emergency)
def test_rf_resp_001_trigger():
    facts = [
        _make_fact("hpi.symptom", "breathlessness"),
        _make_fact("hpi.timing", "constant"),
    ]
    triggered = evaluate_rules("cough_breathlessness", facts)
    matched = [r for r, _ in triggered if r.rule_id == "RF-RESP-001"]
    assert len(matched) == 1
    assert matched[0].priority == "emergency"

    # Negative: intermittent timing
    facts_neg = [
        _make_fact("hpi.symptom", "breathlessness"),
        _make_fact("hpi.timing", "intermittent"),
    ]
    assert not any(r.rule_id == "RF-RESP-001" for r, _ in evaluate_rules("cough_breathlessness", facts_neg))


# 5. RF-RESP-002: hemoptysis in sputum (urgent)
def test_rf_resp_002_trigger_multilingual():
    # English
    facts_en = [_make_fact("hpi.sputum_details", "contains blood clots")]
    assert any(r.rule_id == "RF-RESP-002" for r, _ in evaluate_rules("cough_breathlessness", facts_en))

    # Bengali
    facts_bn = [_make_fact("hpi.sputum_details", "কাশির সাথে রক্ত আসে")]
    assert any(r.rule_id == "RF-RESP-002" for r, _ in evaluate_rules("cough_breathlessness", facts_bn))

    # Hindi
    facts_hi = [_make_fact("hpi.sputum_details", "बलगम में खून निकलता है")]
    assert any(r.rule_id == "RF-RESP-002" for r, _ in evaluate_rules("cough_breathlessness", facts_hi))

    # Negative: clear sputum
    facts_neg = [_make_fact("hpi.sputum_details", "clear white mucus")]
    assert not any(r.rule_id == "RF-RESP-002" for r, _ in evaluate_rules("cough_breathlessness", facts_neg))


# 6. RF-FEV-001: hyperpyrexia temp >= 40.0 (emergency)
def test_rf_fev_001_trigger_and_boundary():
    # Boundary: 40.0 triggers
    facts_40 = [_make_fact("hpi.temperature", 40.0)]
    assert any(r.rule_id == "RF-FEV-001" for r, _ in evaluate_rules("fever", facts_40))

    # High: 40.5 triggers
    facts_405 = [_make_fact("hpi.temperature", 40.5)]
    assert any(r.rule_id == "RF-FEV-001" for r, _ in evaluate_rules("fever", facts_405))

    # Boundary: 39.9 does not trigger
    facts_399 = [_make_fact("hpi.temperature", 39.9)]
    assert not any(r.rule_id == "RF-FEV-001" for r, _ in evaluate_rules("fever", facts_399))


# 7. RF-FEV-002: fever with chills (urgent)
def test_rf_fev_002_trigger():
    facts = [_make_fact("hpi.associated", ["chills", "headache"])]
    assert any(r.rule_id == "RF-FEV-002" for r, _ in evaluate_rules("fever", facts))

    facts_neg = [_make_fact("hpi.associated", ["fatigue"])]
    assert not any(r.rule_id == "RF-FEV-002" for r, _ in evaluate_rules("fever", facts_neg))


# 8. RF-HEAD-001: thunderclap headache severity >= 9 (emergency)
def test_rf_head_001_trigger_and_boundary():
    facts_9 = [_make_fact("hpi.severity", 9)]
    assert any(r.rule_id == "RF-HEAD-001" for r, _ in evaluate_rules("headache", facts_9))

    facts_8 = [_make_fact("hpi.severity", 8)]
    assert not any(r.rule_id == "RF-HEAD-001" for r, _ in evaluate_rules("headache", facts_8))


# 9. RF-HEAD-002: severe radiating headache severity >= 7 and radiation == true (urgent)
def test_rf_head_002_trigger():
    facts = [
        _make_fact("hpi.severity", 7),
        _make_fact("hpi.radiation", True),
    ]
    assert any(r.rule_id == "RF-HEAD-002" for r, _ in evaluate_rules("headache", facts))

    # Severity 6 does not trigger
    facts_neg = [
        _make_fact("hpi.severity", 6),
        _make_fact("hpi.radiation", True),
    ]
    assert not any(r.rule_id == "RF-HEAD-002" for r, _ in evaluate_rules("headache", facts_neg))


# 10. RF-ABD-001: severe constant abdominal pain (emergency)
def test_rf_abd_001_trigger():
    facts = [
        _make_fact("hpi.severity", 8),
        _make_fact("hpi.timing", "constant"),
    ]
    assert any(r.rule_id == "RF-ABD-001" for r, _ in evaluate_rules("abdominal_pain", facts))

    facts_neg = [
        _make_fact("hpi.severity", 8),
        _make_fact("hpi.timing", "intermittent"),
    ]
    assert not any(r.rule_id == "RF-ABD-001" for r, _ in evaluate_rules("abdominal_pain", facts_neg))


# 11. RF-ABD-002: abdominal pain with persistent vomiting (urgent)
def test_rf_abd_002_trigger():
    facts = [
        _make_fact("hpi.associated_details", "vomiting", normalized_concepts=["VOMITING"])
    ]
    assert any(r.rule_id == "RF-ABD-002" for r, _ in evaluate_rules("abdominal_pain", facts))


# Missing/unknown values do not raise exceptions
def test_missing_data_safety():
    facts = [
        _make_fact("hpi.severity", None, status="skipped"),
        _make_fact("hpi.radiation", None, status="skipped"),
    ]
    assert evaluate_rules("chest_pain", facts) == []
    assert evaluate_rules("cough_breathlessness", []) == []


# Flow scoping prevents false triggers across complaints
def test_flow_scoping():
    facts = [
        _make_fact("hpi.severity", 10),
        _make_fact("hpi.radiation", True),
    ]
    # Chest pain rule should not fire in cough flow
    triggered = evaluate_rules("cough_breathlessness", facts)
    assert not any(r.rule_id == "RF-CHEST-001" for r, _ in triggered)


# Database persistence, idempotency, and alert resolution
def test_evaluate_and_persist_idempotent(database):
    # Setup session
    patient = models.Patient(name="Test Patient")
    database.add(patient)
    database.flush()

    session = models.Session(
        hospital_token="TEST-001",
        patient_id=patient.id,
        language="en",
        status="in_progress",
    )
    database.add(session)
    database.commit()

    facts = [
        _make_fact("hpi.severity", 9),
        _make_fact("hpi.radiation", True),
    ]

    # Initial evaluation creates alert
    alerts = evaluate_and_persist(database, session.id, "chest_pain", facts)
    database.commit()
    assert len(alerts) == 1
    assert alerts[0].rule_id == "RF-CHEST-001"
    assert alerts[0].priority == "emergency"
    assert alerts[0].status == "new"

    # Second evaluation with same facts updates existing alert, does not duplicate
    alerts2 = evaluate_and_persist(database, session.id, "chest_pain", facts)
    database.commit()
    assert len(alerts2) == 1
    assert alerts2[0].id == alerts[0].id

    all_alerts = get_session_alerts(database, session.id)
    assert len(all_alerts) == 1

    # Answering with resolved facts resolves the alert
    resolved_facts = [
        _make_fact("hpi.severity", 4),
        _make_fact("hpi.radiation", False),
    ]
    evaluate_and_persist(database, session.id, "chest_pain", resolved_facts)
    database.commit()

    db_alert = database.get(models.Alert, alerts[0].id)
    assert db_alert.status == "resolved"


def test_interview_submission_triggers_red_flag_in_state(client):
    session_id, state = selected(client, "chest_pain")
    assert state["red_flag_alert"] is None

    # Advance to hpi.radiation
    state = until(client, session_id, state, "hpi.radiation")
    state = submit(client, session_id, state, value=True, status="answered")

    # Advance to hpi.severity
    state = until(client, session_id, state, "hpi.severity")
    state = submit(client, session_id, state, value=9, status="answered")

    # RF-CHEST-001 should now be triggered in state
    assert state["red_flag_alert"] is not None
    assert state["red_flag_alert"]["priority"] == "emergency"
    assert state["red_flag_alert"]["rule_id"] == "RF-CHEST-001"
    assert "severity at least 8/10 with radiation" in state["red_flag_alert"]["reason"].lower()


def test_triage_api_list_and_acknowledge(client):
    session_id, state = selected(client, "headache")

    # Advance to hpi.severity
    state = until(client, session_id, state, "hpi.severity")
    state = submit(client, session_id, state, value=9, status="answered")
    assert state["red_flag_alert"] is not None
    assert state["red_flag_alert"]["rule_id"] == "RF-HEAD-001"

    # 1. List alerts via GET /api/triage/alerts
    list_res = client.get("/api/triage/alerts", headers=DOCTOR)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 1
    assert data["emergency_count"] >= 1

    alert = next(a for a in data["items"] if a["session_id"] == session_id)
    assert alert["rule_id"] == "RF-HEAD-001"
    assert alert["status"] == "new"
    assert alert["hospital_token"] == "DEMO-104"
    assert alert["patient_name"] == "Synthetic Patient"

    # Filter by priority
    emer_res = client.get("/api/triage/alerts?priority=emergency", headers=DOCTOR)
    assert emer_res.status_code == 200
    assert any(a["id"] == alert["id"] for a in emer_res.json()["items"])

    # 2. Acknowledge alert via POST /api/triage/alerts/{id}/acknowledge
    ack_res = client.post(
        f"/api/triage/alerts/{alert['id']}/acknowledge",
        headers=DOCTOR,
        json={"note": "Patient moved to resuscitation bay."},
    )
    assert ack_res.status_code == 200
    ack_data = ack_res.json()
    assert ack_data["status"] == "acknowledged"
    assert ack_data["acknowledged_by"] == "00000000-0000-4000-8000-000000000001"
    assert ack_data["acknowledgement_note"] == "Patient moved to resuscitation bay."
    assert ack_data["acknowledged_at"] is not None

    # 3. Verify session alerts endpoint
    session_alerts = client.get(f"/api/sessions/{session_id}/alerts", headers=DOCTOR)
    assert session_alerts.status_code == 200
    assert len(session_alerts.json()) == 1
    assert session_alerts.json()[0]["id"] == alert["id"]

    # 4. Verify doctor session detail includes alerts
    doc_detail = client.get(
        f"/api/doctor/sessions/{session_id}",
        headers=DOCTOR,
    )
    assert doc_detail.status_code == 200
    detail_data = doc_detail.json()
    assert "alerts" in detail_data
    assert len(detail_data["alerts"]) >= 1
    assert detail_data["alerts"][0]["rule_id"] == "RF-HEAD-001"


def test_triage_websocket_feed(client):
    ticket = client.post("/api/triage/ws-ticket", headers=DOCTOR).json()["ticket"]
    with client.websocket_connect("/api/triage/ws", subprotocols=["medikiosk", ticket], headers={"Origin": "http://127.0.0.1:5175"}) as ws:
        session_id, state = selected(client, "headache")
        state = until(client, session_id, state, "hpi.severity")
        state = submit(client, session_id, state, value=9, status="answered")

        created = ws.receive_json()
        assert created["type"] == "alert_created"
        alerts = client.get("/api/triage/alerts", headers=DOCTOR).json()["items"]
        alert = next(a for a in alerts if a["session_id"] == session_id)

        client.post(
            f"/api/triage/alerts/{alert['id']}/acknowledge",
            headers=DOCTOR,
            json={"note": "Priority confirmed."},
        )
        msg = ws.receive_json()
        assert msg["type"] == "alert_acknowledged"
        assert msg["alert"]["id"] == alert["id"]
        assert msg["alert"]["status"] == "acknowledged"

