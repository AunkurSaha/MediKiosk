from unittest.mock import AsyncMock

import pytest

from app.services import red_flags, triage_notifier
from tests.test_adaptive import selected, submit, until
from tests.test_red_flags import _make_fact
from tests.test_stabilization_security import STAFF


@pytest.mark.parametrize(
    "text", ["no blood in my sputum", "আমার কফে রক্ত নেই", "बलगम में खून नहीं है", "tired", "maybe blood"]
)
def test_denied_uncertain_and_substring_are_not_positive(text):
    assert not red_flags.evaluate_rules(
        "cough_breathlessness", [_make_fact("hpi.sputum_details", text)]
    )


def test_family_context_cannot_trigger_current_symptom_rule():
    fact = _make_fact(
        "family_history.details", "shortness of breath", normalized_concepts=["DYSPNEA"]
    )
    assert not red_flags.evaluate_rules("chest_pain", [fact])


def test_offline_explicit_symptom_triggers_existing_rule(client, monkeypatch):
    monkeypatch.setenv("CLINICAL_NORMALIZATION_PROVIDER", "disabled")
    sid, state = selected(client)
    state = until(client, sid, state, "hpi.associated_details")
    state = submit(client, sid, state, "shortness of breath", "answered")
    assert state["red_flag_alert"]["rule_id"] == "RF-CHEST-002"


def test_answer_commit_delivers_creation_event(client, monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(triage_notifier.notifier, "broadcast", spy)
    sid, state = selected(client, "fever")
    state = until(client, sid, state, "hpi.measured")
    state = submit(client, sid, state, True, "answered")
    state = submit(client, sid, state, 40, "answered")
    assert state["red_flag_alert"]["rule_id"] == "RF-FEV-001"
    assert any(call.args[0]["type"] == "alert_created" for call in spy.call_args_list)


def test_acknowledged_trigger_resolves_and_rearms_with_history(client, database):
    sid, _ = selected(client)
    facts = [_make_fact("hpi.severity", 9), _make_fact("hpi.radiation", True)]
    alert = red_flags.evaluate_and_persist(database, sid, "chest_pain", facts)[0]
    database.commit()
    assert (
        client.post(
            f"/api/triage/alerts/{alert.id}/acknowledge", headers=STAFF, json={"note": "Seen"}
        ).status_code
        == 200
    )
    red_flags.evaluate_and_persist(database, sid, "chest_pain", [])
    database.commit()
    assert alert.status == "resolved"
    assert alert.acknowledged_at is not None
    red_flags.evaluate_and_persist(database, sid, "chest_pain", facts)
    database.commit()
    assert alert.status == "new"
    assert alert.acknowledged_at is None
    from sqlalchemy import select

    from app import models

    events = database.scalars(select(models.AuditLog).where(models.AuditLog.entity_id == sid)).all()
    assert {"alert_created", "alert_resolved", "alert_reactivated", "alert_acknowledged"} <= {
        e.action for e in events
    }


def test_explanations_only_describe_checked_conditions():
    rules = {r.rule_id: r for r in red_flags.get_rule_catalog().rules}
    assert "thunderclap" not in rules["RF-HEAD-001"].reason.lower()
    assert "persistent" not in rules["RF-ABD-002"].reason.lower()
    assert "14" not in rules["RF-FEV-002"].reason
    assert "acs" not in rules["RF-CHEST-001"].reason.lower()
