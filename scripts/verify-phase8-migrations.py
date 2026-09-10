"""Verify Phase 8 draft summary enhancement migration compatibility and schema structure."""

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
    schema = "phase8_migration_test"
    with owner.begin() as connection:
        if connection.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname=:name"), {"name": schema}
        ).first():
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = target.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped)
    try:
        # 1. Upgrade to Phase 7 head
        alembic(scoped, "upgrade", "d12f4a7b9c31")

        # Insert synthetic data in Phase 7 schema
        patient, session, user, summary = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO patients (id, name) VALUES (:id, 'Phase 8 Test Patient')"),
                {"id": patient},
            )
            connection.execute(
                text(
                    "INSERT INTO sessions (id, patient_id, hospital_token, language, status) "
                    "VALUES (:id, :patient, 'P8-TEST', 'en', 'ready_for_review')"
                ),
                {"id": session, "patient": patient},
            )
            connection.execute(
                text("INSERT INTO users (id, name, email, role) VALUES (:id, 'Dr. P8', 'p8@example.com', 'doctor')"),
                {"id": user},
            )
            connection.execute(
                text(
                    "INSERT INTO clinical_summaries (id, session_id, generated_text, status, version) "
                    "VALUES (:id, :session, 'Initial draft text', 'generated', 1)"
                ),
                {"id": summary, "session": session},
            )
            connection.execute(
                text(
                    "INSERT INTO summary_revisions (id, summary_id, version, reviewed_text, actor_user_id) "
                    "VALUES (:id, :summary, 1, 'Initial draft text', :user)"
                ),
                {"id": str(uuid4()), "summary": summary, "user": user},
            )

        prior_fingerprint = fingerprint(engine)

        # 2. Upgrade to Phase 8 head
        alembic(scoped, "upgrade", "head")

        inspector = inspect(engine)
        summary_cols = {col["name"]: col for col in inspector.get_columns("clinical_summaries")}
        assert "confirmed_text" in summary_cols, "confirmed_text missing from clinical_summaries"
        assert "draft_provider" in summary_cols, "draft_provider missing from clinical_summaries"
        assert "draft_version" in summary_cols, "draft_version missing from clinical_summaries"

        rev_cols = {col["name"]: col for col in inspector.get_columns("summary_revisions")}
        assert "revision_type" in rev_cols, "revision_type missing from summary_revisions"
        assert "actor_type" in rev_cols, "actor_type missing from summary_revisions"
        assert "review_notes" in rev_cols, "review_notes missing from summary_revisions"
        assert "structured_snapshot" in rev_cols, "structured_snapshot missing from summary_revisions"
        assert rev_cols["actor_user_id"]["nullable"] is True, "actor_user_id should be nullable"

        # 3. Test inserting a Phase 8 record with SYSTEM actor_type and null actor_user_id
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO summary_revisions (id, summary_id, version, revision_type, actor_type, reviewed_text, actor_user_id) "
                    "VALUES (:id, :summary, 2, 'regenerate', 'SYSTEM', 'Regenerated system draft', NULL)"
                ),
                {"id": str(uuid4()), "summary": summary},
            )

        # 4. Downgrade back to Phase 7 and verify clean downgrade
        # Clean up the row with null actor_user_id first to allow not-null constraint on downgrade
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM summary_revisions WHERE version = 2")
            )
        alembic(scoped, "downgrade", "d12f4a7b9c31")

        down_cols = {col["name"]: col for col in inspect(engine).get_columns("clinical_summaries")}
        assert "confirmed_text" not in down_cols, "confirmed_text still in clinical_summaries after downgrade"

        # 5. Re-upgrade to head
        alembic(scoped, "upgrade", "head")
        reup_cols = {col["name"]: col for col in inspect(engine).get_columns("clinical_summaries")}
        assert "confirmed_text" in reup_cols, "confirmed_text missing after re-upgrade"

        print("Phase 8 migration verification passed successfully!")
    finally:
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


if __name__ == "__main__":
    test_migration()
