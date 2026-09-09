"""Verify Phase 5 red_flag_alerts schema compatibility and table structure."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
url = make_url(dotenv_values(BACKEND / ".env")["DATABASE_URL"])
if url.get_backend_name() != "postgresql" or url.host not in ("localhost", "127.0.0.1"):
    raise RuntimeError("This verification is only for the local PostgreSQL demo.")


def fingerprint(engine, tables=None):
    tables = (
        tables
        if tables is not None
        else [t for t in inspect(engine).get_table_names() if t != "alembic_version"]
    )
    with engine.connect() as connection:
        result = {}
        for table in tables:
            quoted = engine.dialect.identifier_preparer.quote(table)
            rows = connection.execute(text(f"SELECT * FROM {quoted}")).mappings().all()
            serialized = sorted(
                json.dumps(dict(row), default=str, sort_keys=True) for row in rows
            )
            result[table] = {
                "count": len(rows),
                "sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
            }
        return result


def alembic(target, *args):
    env = {**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Alembic {' '.join(args)} failed; stderr: {result.stderr}"
        )


def isolated_schema_test(schema, previous=None):
    target = url.set(database="medikiosk_test")
    owner = create_engine(target)
    with owner.begin() as connection:
        if connection.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname=:name"), {"name": schema}
        ).first():
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = target.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped)
    try:
        if previous:
            alembic(scoped, "upgrade", previous)
            patient, session = str(uuid4()), str(uuid4())
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO patients (id,name) VALUES (:id,'Synthetic migration patient')"
                    ),
                    {"id": patient},
                )
                connection.execute(
                    text(
                        "INSERT INTO sessions (id,patient_id,hospital_token,language,status) VALUES (:id,:patient,'MIGRATION-DEMO','en','intake')"
                    ),
                    {"id": session, "patient": patient},
                )
            prior = fingerprint(engine)
            alembic(scoped, "upgrade", "head")
            # Existing tables and rows must not be altered
            after = fingerprint(engine, tables=list(prior.keys()))
            if prior != after:
                raise RuntimeError("Phase 5 upgrade altered existing user rows or tables.")
            # Verify new alerts table is present and functional
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            if "alerts" not in tables:
                raise RuntimeError("alerts table missing after upgrade to head.")
            # Verify columns
            cols = {c["name"]: c for c in inspector.get_columns("alerts")}
            expected_cols = [
                "id", "session_id", "rule_id", "rule_version", "priority",
                "category", "reason", "triggering_facts_json", "status",
                "acknowledged_at", "acknowledged_by", "acknowledgement_note",
                "created_at", "updated_at"
            ]
            for col in expected_cols:
                if col not in cols:
                    raise RuntimeError(f"Column {col} missing from alerts table.")
            # Test inserting into alerts
            alert_id = str(uuid4())
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO alerts (
                            id, session_id, rule_id, rule_version, priority,
                            category, reason, triggering_facts_json, status, created_at
                        ) VALUES (
                            :id, :session_id, 'RF-CHEST-001', '1.0.0', 'emergency',
                            'cardiovascular', 'Severe pain', '[]'::json, 'new', CURRENT_TIMESTAMP
                        )
                    """),
                    {"id": alert_id, "session_id": session},
                )
                # Verify unique constraint on (session_id, rule_id)
                duplicate_threw = False
                try:
                    connection.execute(
                        text("""
                            INSERT INTO alerts (
                                id, session_id, rule_id, rule_version, priority,
                                category, reason, triggering_facts_json, status, created_at
                            ) VALUES (
                                :id, :session_id, 'RF-CHEST-001', '1.0.0', 'emergency',
                                'cardiovascular', 'Severe pain', '[]'::json, 'new', CURRENT_TIMESTAMP
                            )
                        """),
                        {"id": str(uuid4()), "session_id": session},
                    )
                except Exception:
                    duplicate_threw = True
                if not duplicate_threw:
                    raise RuntimeError("Unique constraint uq_session_rule_alert did not enforce uniqueness.")
        else:
            # Fresh install directly to head
            alembic(scoped, "upgrade", "head")
            inspector = inspect(engine)
            if "alerts" not in inspector.get_table_names():
                raise RuntimeError("alerts table missing from fresh upgrade to head.")
    finally:
        engine.dispose()
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


def main():
    print("Testing fresh database upgrade to head in isolated schema...")
    isolated_schema_test("phase5_verify_fresh")
    print("Testing upgrade from Phase 3 (e43b205c0f13) to Phase 5 head...")
    isolated_schema_test("phase5_verify_upgrade", previous="e43b205c0f13")
    print("Phase 5 migration verification passed: alerts table and constraints validated.")


if __name__ == "__main__":
    main()
