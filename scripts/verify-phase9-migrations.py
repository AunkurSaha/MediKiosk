"""Verify Phase 9 verification hardening migration compatibility and schema structure."""

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
        raise RuntimeError(f"Alembic {' '.join(args)} failed; stderr: {result.stderr}")


def test_migration():
    target = url.set(database="medikiosk_test")
    owner = create_engine(target)
    schema = "phase9_migration_test"
    with owner.connect() as connection:
        connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {schema}"))

    schema_target = target.set(query={"options": f"-csearch_path={schema}"})

    try:
        # 1. Upgrade from empty to Phase 8 head
        alembic(schema_target, "upgrade", "1915850a59d1")

        # 2. Insert sample records into clinical_summaries
        test_engine = create_engine(schema_target)
        with test_engine.begin() as conn:
            pid = str(uuid4())
            sid = str(uuid4())
            sum_id = str(uuid4())
            conn.execute(
                text(
                    f"INSERT INTO patients (id, name) VALUES ('{pid}', 'Phase9 Test')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO sessions (id, patient_id, hospital_token, language, status) VALUES ('{sid}', '{pid}', 'T-P9-01', 'en', 'ready_for_review')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO clinical_summaries (id, session_id, status, generated_text, reviewed_text, confirmed_text, draft_provider, draft_version) "
                    f"VALUES ('{sum_id}', '{sid}', 'confirmed', 'Draft', 'Reviewed', 'Confirmed Text', 'deterministic_template', 1)"
                )
            )

        fp_phase8 = fingerprint(test_engine, ["clinical_summaries"])

        # 3. Upgrade to Phase 9 head
        alembic(schema_target, "upgrade", "head")

        # Verify table existence and new columns
        inspector = inspect(test_engine)
        tables = inspector.get_table_names()
        assert "field_verifications" in tables, "field_verifications table missing"
        assert "field_verification_revisions" in tables, "field_verification_revisions table missing"

        sum_cols = {c["name"] for c in inspector.get_columns("clinical_summaries")}
        assert "amended_text" in sum_cols, "amended_text missing in clinical_summaries"
        assert "amended_by" in sum_cols, "amended_by missing in clinical_summaries"
        assert "amended_at" in sum_cols, "amended_at missing in clinical_summaries"
        assert "amendment_notes" in sum_cols, "amendment_notes missing in clinical_summaries"

        # Verify data preservation
        with test_engine.connect() as conn:
            row = conn.execute(text(f"SELECT * FROM clinical_summaries WHERE id = '{sum_id}'")).mappings().one()
            assert row["confirmed_text"] == "Confirmed Text"
            assert row["amended_text"] is None

        # 4. Downgrade back to Phase 8 and re-upgrade
        alembic(schema_target, "downgrade", "1915850a59d1")
        inspector_down = inspect(test_engine)
        assert "field_verifications" not in inspector_down.get_table_names()
        alembic(schema_target, "upgrade", "head")

        # 5. Apply to application database
        app_target = url.set(database="medikiosk")
        alembic(app_target, "upgrade", "head")

        # 6. Alembic check for drift
        alembic(app_target, "check")
        print("Phase 9 migration verification passed successfully on PostgreSQL!")

    finally:
        with owner.connect() as connection:
            connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))


if __name__ == "__main__":
    test_migration()
