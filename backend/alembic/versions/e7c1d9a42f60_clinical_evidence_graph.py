"""clinical evidence graph

Revision ID: e7c1d9a42f60
Revises: a8fb1ea7923d
"""

import json
import uuid
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = "e7c1d9a42f60"
down_revision = "a8fb1ea7923d"
branch_labels = None
depends_on = None


SOURCE_TYPES = (
    "PATIENT_TEXT",
    "PATIENT_VOICE",
    "DOCUMENT",
    "PREVIOUS_ENCOUNTER",
    "CLINICIAN",
    "DETERMINISTIC_RULE",
    "EXTERNAL_RECORD",
)
VERIFICATION_STATES = (
    "UNVERIFIED",
    "PATIENT_CONFIRMED",
    "CLINICIAN_VERIFIED",
    "REJECTED",
    "CONFLICTING",
)
EVIDENCE_NAMESPACE = uuid.UUID("3d15595b-cf66-4f53-a159-d9730a820067")


def _in(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def _id(*parts: str) -> str:
    return str(uuid.uuid5(EVIDENCE_NAMESPACE, "|".join(parts)))


def _json(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _dt(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _backfill_existing_evidence() -> None:
    """Project existing source rows without changing their canonical tables."""
    bind = op.get_bind()
    evidence = sa.table(
        "clinical_evidence",
        sa.column("id", sa.String()),
        sa.column("patient_id", sa.String()),
        sa.column("session_id", sa.String()),
        sa.column("concept_code", sa.String()),
        sa.column("value_json", sa.JSON()),
        sa.column("source_type", sa.String()),
        sa.column("source_id", sa.String()),
        sa.column("stable_key", sa.String()),
        sa.column("original_text", sa.Text()),
        sa.column("normalized_text", sa.Text()),
        sa.column("translated_text", sa.Text()),
        sa.column("language", sa.String()),
        sa.column("confidence", sa.Float()),
        sa.column("verification_status", sa.String()),
        sa.column("metadata_json", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    answers = list(
        bind.execute(
            sa.text(
                "SELECT a.*, s.patient_id FROM interview_answers a "
                "JOIN sessions s ON s.id = a.session_id"
            )
        ).mappings()
    )
    answer_evidence_ids: dict[str, str] = {}
    rows = []
    for answer in answers:
        envelope = _json(answer["value_json"])
        value = envelope.get("value") if isinstance(envelope, dict) else envelope
        status = envelope.get("status", "answered") if isinstance(envelope, dict) else "answered"
        evidence_id = _id("answer", answer["id"], "raw_answer")
        answer_evidence_ids[answer["id"]] = evidence_id
        rows.append(
            {
                "id": evidence_id,
                "patient_id": answer["patient_id"],
                "session_id": answer["session_id"],
                "concept_code": None,
                "value_json": value,
                "source_type": "PATIENT_VOICE" if answer["source"] == "voice" else "PATIENT_TEXT",
                "source_id": answer["id"],
                "stable_key": "raw_answer",
                "original_text": answer["raw_value"],
                "normalized_text": None,
                "translated_text": None,
                "language": answer["language"],
                "confidence": None,
                "verification_status": "PATIENT_CONFIRMED",
                "metadata_json": {
                    "question_id": answer["question_id"],
                    "canonical_field": answer["field"],
                    "answer_status": status,
                    "backfilled": True,
                },
                "created_at": _dt(answer["created_at"]),
                "updated_at": _dt(answer["updated_at"]),
            }
        )
    if rows:
        bind.execute(evidence.insert(), rows)

    normalizations = bind.execute(
        sa.text(
            "SELECT n.*, a.raw_value, a.source, a.language, s.patient_id "
            "FROM normalization_results n "
            "JOIN interview_answers a ON a.id = n.source_answer_id "
            "JOIN sessions s ON s.id = n.session_id"
        )
    ).mappings()
    rows = []
    for normalization in normalizations:
        result = _json(normalization["result_json"]) or {}
        for fact in result.get("facts", []):
            concept = fact.get("normalized_concept") or fact.get("concept")
            if not concept:
                continue
            rows.append(
                {
                    "id": _id("normalization", normalization["source_answer_id"], concept),
                    "patient_id": normalization["patient_id"],
                    "session_id": normalization["session_id"],
                    "concept_code": concept,
                    "value_json": fact.get("normalized_value"),
                    "source_type": "PATIENT_VOICE"
                    if normalization["source"] == "voice"
                    else "PATIENT_TEXT",
                    "source_id": normalization["source_answer_id"],
                    "stable_key": f"normalized:{concept}",
                    "original_text": normalization["raw_value"],
                    "normalized_text": fact.get("normalized_display"),
                    "translated_text": None,
                    "language": normalization["language"],
                    "confidence": fact.get("confidence"),
                    "verification_status": "PATIENT_CONFIRMED",
                    "metadata_json": {
                        "normalization_id": normalization["id"],
                        "provider": normalization["provider"],
                        "provider_version": normalization["provider_version"],
                        "schema_version": normalization["schema_version"],
                        "policy_version": normalization["policy_version"],
                        "certainty": fact.get("certainty"),
                        "polarity": fact.get("polarity", "present"),
                        "evidence": fact.get("evidence"),
                        "backfilled": True,
                    },
                    "created_at": _dt(normalization["created_at"]),
                    "updated_at": None,
                }
            )
    if rows:
        bind.execute(evidence.insert(), rows)

    for table_name, concept, entity_type in (
        ("medication_fact", "MEDICATION_MENTION", "medication"),
        ("lab_fact", "LAB_OBSERVATION", "lab_observation"),
    ):
        facts = bind.execute(
            sa.text(
                f"SELECT f.*, e.document_id, e.extractor, e.extractor_version, "
                f"e.confidence AS ocr_confidence, s.patient_id FROM {table_name} f "
                "JOIN document_extractions e ON e.id = f.document_extraction_id "
                "JOIN sessions s ON s.id = f.session_id"
            )
        ).mappings()
        rows = []
        for fact in facts:
            value = (
                {
                    key: fact[key]
                    for key in ("name", "dosage", "unit", "frequency", "route", "duration")
                }
                if table_name == "medication_fact"
                else {
                    key: fact[key]
                    for key in ("test_name", "value", "unit", "reference_range", "flag")
                }
            )
            rows.append(
                {
                    "id": _id("document", fact["id"], entity_type),
                    "patient_id": fact["patient_id"],
                    "session_id": fact["session_id"],
                    "concept_code": concept,
                    "value_json": value,
                    "source_type": "DOCUMENT",
                    "source_id": fact["id"],
                    "stable_key": entity_type,
                    "original_text": fact["source_text"],
                    "normalized_text": None,
                    "translated_text": None,
                    "language": None,
                    "confidence": fact["ocr_confidence"],
                    "verification_status": {
                        "verified": "CLINICIAN_VERIFIED",
                        "rejected": "REJECTED",
                    }.get(fact["verification_status"], "UNVERIFIED"),
                    "metadata_json": {
                        "document_id": fact["document_id"],
                        "extraction_id": fact["document_extraction_id"],
                        "entity_type": entity_type,
                        "source_location": fact["source_location"],
                        "ocr_provider": fact["extractor"],
                        "ocr_provider_version": fact["extractor_version"],
                        "ocr_confidence": fact["ocr_confidence"],
                        "backfilled": True,
                    },
                    "created_at": _dt(fact["created_at"]),
                    "updated_at": _dt(fact["updated_at"]),
                }
            )
        if rows:
            bind.execute(evidence.insert(), rows)

    answer_rows_by_question: dict[tuple[str, str], list[str]] = {}
    for answer in answers:
        answer_rows_by_question.setdefault(
            (answer["session_id"], answer["question_id"]), []
        ).append(answer_evidence_ids[answer["id"]])
    alerts = bind.execute(
        sa.text("SELECT a.*, s.patient_id FROM alerts a JOIN sessions s ON s.id = a.session_id")
    ).mappings()
    rows = []
    for alert in alerts:
        facts = _json(alert["triggering_facts_json"]) or []
        triggering_ids = sorted(
            {
                evidence_id
                for fact in facts
                for evidence_id in answer_rows_by_question.get(
                    (alert["session_id"], fact.get("question_id")), []
                )
            }
        )
        concept = "RED_FLAG_" + "_".join(
            part for part in alert["rule_id"].upper().replace("-", "_").split("_") if part
        )
        rows.append(
            {
                "id": _id("rule", alert["id"], "rule_result"),
                "patient_id": alert["patient_id"],
                "session_id": alert["session_id"],
                "concept_code": concept,
                "value_json": {
                    "triggered": alert["status"] != "resolved",
                    "priority": alert["priority"],
                },
                "source_type": "DETERMINISTIC_RULE",
                "source_id": alert["id"],
                "stable_key": "rule_result",
                "original_text": None,
                "normalized_text": None,
                "translated_text": None,
                "language": None,
                "confidence": None,
                "verification_status": "UNVERIFIED",
                "metadata_json": {
                    "rule_id": alert["rule_id"],
                    "rule_version": alert["rule_version"],
                    "reason": alert["reason"],
                    "category": alert["category"],
                    "alert_status": alert["status"],
                    "triggering_evidence_ids": triggering_ids,
                    "backfilled": True,
                },
                "created_at": _dt(alert["created_at"]),
                "updated_at": _dt(alert["updated_at"]),
            }
        )
    if rows:
        bind.execute(evidence.insert(), rows)


def upgrade() -> None:
    op.create_table(
        "clinical_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "patient_id",
            sa.String(),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("concept_code", sa.String(160)),
        sa.Column("value_json", sa.JSON()),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("stable_key", sa.String(160), nullable=False, server_default="value"),
        sa.Column("original_text", sa.Text()),
        sa.Column("normalized_text", sa.Text()),
        sa.Column("translated_text", sa.Text()),
        sa.Column("language", sa.String(16)),
        sa.Column("confidence", sa.Float()),
        sa.Column("verification_status", sa.String(40), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("verified_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_clinical_evidence_confidence",
        ),
        sa.CheckConstraint(
            f"source_type IN ({_in(SOURCE_TYPES)})",
            name="ck_clinical_evidence_source_type",
        ),
        sa.CheckConstraint(
            f"verification_status IN ({_in(VERIFICATION_STATES)})",
            name="ck_clinical_evidence_verification_status",
        ),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "stable_key",
            name="uq_clinical_evidence_provenance",
        ),
    )
    for column in (
        "patient_id",
        "session_id",
        "concept_code",
        "source_type",
        "verification_status",
        "created_at",
    ):
        op.create_index(f"ix_clinical_evidence_{column}", "clinical_evidence", [column])
    op.create_index(
        "ix_clinical_evidence_patient_created",
        "clinical_evidence",
        ["patient_id", "created_at"],
    )
    op.create_index(
        "ix_clinical_evidence_session_concept",
        "clinical_evidence",
        ["session_id", "concept_code"],
    )
    op.create_table(
        "clinical_evidence_conflicts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "evidence_a_id",
            sa.String(),
            sa.ForeignKey("clinical_evidence.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_b_id",
            sa.String(),
            sa.ForeignKey("clinical_evidence.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "evidence_a_id", "evidence_b_id", name="uq_clinical_evidence_conflict_pair"
        ),
    )
    op.create_index(
        "ix_clinical_evidence_conflicts_evidence_a_id",
        "clinical_evidence_conflicts",
        ["evidence_a_id"],
    )
    op.create_index(
        "ix_clinical_evidence_conflicts_evidence_b_id",
        "clinical_evidence_conflicts",
        ["evidence_b_id"],
    )
    _backfill_existing_evidence()


def downgrade() -> None:
    op.drop_table("clinical_evidence_conflicts")
    op.drop_table("clinical_evidence")
