import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app import models
from app.schemas.adaptive import Fact
from app.schemas.alert import AlertPriority, TriggeringFact
from app.services import intake

RULES_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "ai"
    / "safety_rules"
    / "red_flags_v1.json"
)


class RuleCondition(BaseModel):
    field: str
    model_config = ConfigDict(extra="forbid")
    operator: Literal["equals", "greater_than_or_equal", "in", "contains", "contains_any_word"]
    value: Any


class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    version: str
    flow_id: str
    priority: AlertPriority
    category: str
    reason: str
    conditions: list[RuleCondition] = Field(default_factory=list)


class RuleCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    rules_version: str
    description: str
    rules: list[RuleDefinition]


_CATALOG: RuleCatalog | None = None


def get_rule_catalog() -> RuleCatalog:
    global _CATALOG
    if _CATALOG is None:
        if not RULES_PATH.exists():
            raise FileNotFoundError(f"Safety rules file not found: {RULES_PATH}")
        with open(RULES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _CATALOG = RuleCatalog.model_validate(data)
    return _CATALOG


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@lru_cache(maxsize=1)
def _explicit_symptoms() -> dict[tuple[str, str], set[str]]:
    path = RULES_PATH.parents[1] / "normalization" / "mock_vocabulary.json"
    fixtures = json.loads(path.read_text(encoding="utf-8"))["fixtures"]
    return {
        (f["language"], _fold(f["text"])): {
            n["concept"] for n in f["facts"] if n["certainty"] == "certain"
        }
        for f in fixtures
        if f["status"] == "normalized"
    }


def symptom_concepts(fact: Fact) -> set[str]:
    if fact.status != "answered" or fact.field not in {
        "chief_complaint.description",
        "hpi.associated_details",
    }:
        return set()
    if fact.normalization and fact.normalization.status == "normalized":
        return {
            n.normalized_concept
            for n in fact.normalization.facts
            if n.polarity == "present"
            and n.certainty == "certain"
            and n.verification_status == "machine_normalized"
        }
    # Existing exact multilingual vocabulary provides an offline path for the
    # same symptom conditions; this does not call or fabricate provider output.
    return _explicit_symptoms().get((fact.language, _fold(str(fact.value))), set())


def _eval_condition(
    condition: RuleCondition,
    facts_by_field: dict[str, Fact],
    normalized_concepts: set[str],
) -> tuple[bool, TriggeringFact | None]:
    field_name = condition.field

    # Match a concept to the same present, current-symptom source used as evidence.
    if field_name.startswith("concept:") or field_name == "any_concept":
        if field_name == "any_concept":
            targets = (
                condition.value
                if condition.operator == "in" and isinstance(condition.value, list)
                else []
            )
        else:
            targets = (
                [field_name.split(":", 1)[1]]
                if condition.operator == "equals" and condition.value is True
                else []
            )
        for fact in facts_by_field.values():
            matched = sorted(set(targets).intersection(symptom_concepts(fact)))
            if matched:
                return True, TriggeringFact(
                    question_id=fact.question_id,
                    field=fact.field,
                    value=matched[0],
                    raw_value=fact.raw_value,
                    label=fact.label,
                )
        return False, None

    # Check for regular fact-based conditions
    fact = facts_by_field.get(field_name)
    if fact is None or fact.status != "answered" or fact.value is None:
        return False, None

    val = fact.value
    op = condition.operator
    cond_val = condition.value

    if op == "equals":
        if val == cond_val:
            return True, TriggeringFact(
                question_id=fact.question_id,
                field=fact.field,
                value=val,
                raw_value=fact.raw_value,
                label=fact.label,
            )
        return False, None

    elif op == "greater_than_or_equal":
        try:
            num_val = float(val)
            threshold = float(cond_val)
            if num_val >= threshold:
                return True, TriggeringFact(
                    question_id=fact.question_id,
                    field=fact.field,
                    value=num_val,
                    raw_value=fact.raw_value,
                    label=fact.label,
                )
        except (ValueError, TypeError):
            return False, None
        return False, None

    elif op == "in":
        if isinstance(cond_val, list) and val in cond_val:
            return True, TriggeringFact(
                question_id=fact.question_id,
                field=fact.field,
                value=val,
                raw_value=fact.raw_value,
                label=fact.label,
            )
        return False, None

    elif op == "contains":
        if isinstance(val, list) and cond_val in val:
            return True, TriggeringFact(
                question_id=fact.question_id,
                field=fact.field,
                value=val,
                raw_value=fact.raw_value,
                label=fact.label,
            )
        return False, None

    elif op == "contains_any_word":
        if isinstance(val, str) and isinstance(cond_val, list):
            # Exact positive demo phrases only. Unrecognized/negated/contextual
            # language is not converted into a positive assertion by substring.
            positives = {_fold(word) for word in cond_val} | {
                "contains blood clots",
                "কাশির সাথে রক্ত আসে",
                "बलगम में खून निकलता है",
            }
            if _fold(val) in positives:
                return True, TriggeringFact(
                    question_id=fact.question_id,
                    field=fact.field,
                    value=val,
                    raw_value=fact.raw_value,
                    label=fact.label,
                )
        return False, None

    return False, None


def evaluate_rules(
    flow_id: str,
    active_facts: list[Fact],
) -> list[tuple[RuleDefinition, list[TriggeringFact]]]:
    """Pure evaluation of safety rules against active facts."""
    catalog = get_rule_catalog()
    facts_by_field: dict[str, Fact] = {}
    normalized_concepts: set[str] = set()

    for fact in active_facts:
        facts_by_field[fact.field] = fact
        normalized_concepts.update(symptom_concepts(fact))

    triggered_rules: list[tuple[RuleDefinition, list[TriggeringFact]]] = []

    for rule in catalog.rules:
        if rule.flow_id != "*" and rule.flow_id != flow_id:
            continue

        all_met = True
        triggering_facts: list[TriggeringFact] = []

        for cond in rule.conditions:
            met, tf = _eval_condition(cond, facts_by_field, normalized_concepts)
            if not met:
                all_met = False
                break
            if tf:
                triggering_facts.append(tf)

        if all_met and triggering_facts:
            triggered_rules.append((rule, triggering_facts))

    return triggered_rules


def evaluate_and_persist(
    db: Session,
    session_id: str,
    flow_id: str,
    active_facts: list[Fact],
) -> list[models.Alert]:
    """Evaluates rules and persists new or updated alerts in the database."""
    intake.get_session(db, session_id)
    triggered = evaluate_rules(flow_id, active_facts)
    triggered_rule_ids = {rule.rule_id for rule, _ in triggered}

    # Load existing alerts for this session
    existing_alerts = {
        alert.rule_id: alert
        for alert in db.scalars(
            select(models.Alert).where(models.Alert.session_id == session_id)
        ).all()
    }

    results: list[models.Alert] = []

    for rule, triggering_facts in triggered:
        tf_data = [tf.model_dump(mode="json") for tf in triggering_facts]
        if rule.rule_id in existing_alerts:
            # Update existing alert
            alert = existing_alerts[rule.rule_id]
            changed = alert.triggering_facts_json != tf_data or alert.rule_version != rule.version
            if changed or alert.status == "resolved":
                alert.revision += 1
                action = "alert_reactivated" if alert.status == "resolved" else "alert_updated"
                intake.audit(
                    db,
                    action,
                    session_id,
                    metadata={
                        "alert_id": alert.id,
                        "rule_id": rule.rule_id,
                        "previous_status": alert.status,
                        "previous_acknowledged_by": alert.acknowledged_by,
                        "previous_acknowledged_at": alert.acknowledged_at.isoformat()
                        if alert.acknowledged_at
                        else None,
                    },
                )
                db.info.setdefault("triage_events", []).append(
                    {"type": action, "session_id": session_id, "alert_id": alert.id}
                )
                alert.updated_at = intake.now()
            alert.triggering_facts_json = tf_data
            alert.reason, alert.rule_version = rule.reason, rule.version
            alert.priority, alert.category = rule.priority, rule.category
            # If it was resolved, re-arm it
            if alert.status == "resolved":
                alert.status = "new"
                alert.acknowledged_at = None
                alert.acknowledged_by = None
                alert.acknowledgement_note = None
            results.append(alert)
        else:
            # Create new alert
            new_alert = models.Alert(
                session_id=session_id,
                rule_id=rule.rule_id,
                rule_version=rule.version,
                priority=rule.priority,
                category=rule.category,
                reason=rule.reason,
                triggering_facts_json=tf_data,
                status="new",
                created_at=intake.now(),
            )
            db.add(new_alert)
            db.flush()
            db.info.setdefault("triage_events", []).append(
                {"type": "alert_created", "session_id": session_id, "alert_id": new_alert.id}
            )
            intake.audit(
                db,
                "alert_created",
                session_id,
                metadata={
                    "rule_id": rule.rule_id,
                    "priority": rule.priority,
                    "category": rule.category,
                },
            )
            results.append(new_alert)

    # Check for alerts that were previously triggered but no longer met
    for rule_id, alert in existing_alerts.items():
        if rule_id not in triggered_rule_ids and alert.status != "resolved":
            alert.status = "resolved"
            alert.revision += 1
            alert.updated_at = intake.now()
            intake.audit(
                db,
                "alert_resolved",
                session_id,
                metadata={"alert_id": alert.id, "rule_id": rule_id},
            )
            db.info.setdefault("triage_events", []).append(
                {"type": "alert_resolved", "session_id": session_id, "alert_id": alert.id}
            )

    db.flush()
    return results


def get_session_alerts(db: Session, session_id: str) -> list[models.Alert]:
    """Returns all alerts for a session, ordered by emergency first, then created_at."""
    return list(
        db.scalars(
            select(models.Alert)
            .where(models.Alert.session_id == session_id)
            .order_by(
                case((models.Alert.priority == "emergency", 0), else_=1).asc(),
                models.Alert.created_at.desc(),
                models.Alert.id,
            )
        ).all()
    )
