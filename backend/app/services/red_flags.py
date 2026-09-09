import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app import models
from app.schemas.adaptive import Fact
from app.schemas.alert import AlertPriority, TriggeringFact
from app.services import intake

RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "ai" / "safety_rules" / "red_flags_v1.json"


class RuleCondition(BaseModel):
    field: str
    operator: str
    value: Any


class RuleDefinition(BaseModel):
    rule_id: str
    version: str
    flow_id: str
    priority: AlertPriority
    category: str
    reason: str
    conditions: list[RuleCondition] = Field(default_factory=list)


class RuleCatalog(BaseModel):
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


def _eval_condition(
    condition: RuleCondition,
    facts_by_field: dict[str, Fact],
    normalized_concepts: set[str],
) -> tuple[bool, TriggeringFact | None]:
    field_name = condition.field

    # Check for concept-based conditions
    if field_name.startswith("concept:"):
        concept_name = field_name.split(":", 1)[1]
        if concept_name in normalized_concepts:
            # Find the fact that produced this concept
            matching_fact = None
            for fact in facts_by_field.values():
                if fact.normalization and fact.normalization.facts:
                    for nf in fact.normalization.facts:
                        if nf.normalized_concept == concept_name:
                            matching_fact = fact
                            break
            return True, TriggeringFact(
                question_id=matching_fact.question_id if matching_fact else "normalization",
                field=field_name,
                value=concept_name,
                raw_value=matching_fact.raw_value if matching_fact else concept_name,
                label=f"Clinical concept {concept_name} identified",
            )
        return False, None

    if field_name == "any_concept":
        target_concepts = set(condition.value) if isinstance(condition.value, list) else {condition.value}
        matched = target_concepts.intersection(normalized_concepts)
        if matched:
            concept_name = sorted(matched)[0]
            matching_fact = None
            for fact in facts_by_field.values():
                if fact.normalization and fact.normalization.facts:
                    for nf in fact.normalization.facts:
                        if nf.normalized_concept in matched:
                            matching_fact = fact
                            break
            return True, TriggeringFact(
                question_id=matching_fact.question_id if matching_fact else "normalization",
                field=concept_name,
                value=concept_name,
                raw_value=matching_fact.raw_value if matching_fact else concept_name,
                label=f"Clinical concept {concept_name} identified",
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
            lower_val = val.lower()
            for word in cond_val:
                if word.lower() in lower_val:
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
        if fact.normalization and fact.normalization.facts:
            for nf in fact.normalization.facts:
                status = getattr(nf, "verification_status", getattr(nf, "status", None))
                polarity = getattr(nf, "polarity", "present")
                if status in ("machine_normalized", "verified", None) and polarity == "present":
                    normalized_concepts.add(nf.normalized_concept)

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
            alert.triggering_facts_json = tf_data
            alert.updated_at = intake.now()
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
        if rule_id not in triggered_rule_ids and alert.status == "new":
            alert.status = "resolved"
            alert.updated_at = intake.now()

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
