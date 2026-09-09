"""Exercise empty/Phase 1 upgrades in isolated schemas, then preserve-check the app DB."""

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
TABLES = (
    "patients",
    "sessions",
    "consents",
    "interview_answers",
    "clinical_summaries",
    "users",
    "audit_logs",
    "summary_revisions",
)


def fingerprint(engine):
    with engine.connect() as connection:
        return {
            table: {
                "count": len(
                    rows := connection.execute(text(f'SELECT * FROM "{table}" ORDER BY id'))
                    .mappings()
                    .all()
                ),
                "sha256": hashlib.sha256(
                    json.dumps([dict(r) for r in rows], default=str, sort_keys=True).encode()
                ).hexdigest(),
            }
            for table in TABLES
        }


def alembic(target, *args):
    env = {**os.environ, "DATABASE_URL": target.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # Never emit a driver exception containing a connection URI.
        raise RuntimeError(
            f"Alembic {' '.join(args)} failed; inspect locally without exposing credentials."
        )


def isolated_schema_test(schema, phase1=False):
    target = url.set(database="medikiosk_test")
    owner = create_engine(target)
    with owner.begin() as connection:
        if connection.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname=:name"), {"name": schema}
        ).first():
            raise RuntimeError(
                f"Verification schema {schema} already exists; refusing to overwrite."
            )
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = target.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped)
    try:
        if phase1:
            alembic(scoped, "upgrade", "c92f104a7e21")
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
                connection.execute(
                    text(
                        "INSERT INTO interview_answers (id,session_id,question_id,field,value_json,raw_value,source,language,verification_status) VALUES (:id,:session,'chief_complaint','chief_complaint',:value,'Original migration words','typed','en','patient_reported')"
                    ),
                    {
                        "id": str(uuid4()),
                        "session": session,
                        "value": json.dumps("Original migration words"),
                    },
                )
            before = fingerprint(engine)
        alembic(scoped, "upgrade", "head")
        alembic(scoped, "check")
        assert {"interview_runs", "interview_requests"} <= set(inspect(engine).get_table_names())
        if phase1:
            assert fingerprint(engine) == before
        print(
            f"PASS: {'Phase 1 upgrade and original row preservation' if phase1 else 'empty database schema upgrade'}; Alembic check clean"
        )
    finally:
        engine.dispose()
        # These fixed schemas were created by this invocation in medikiosk_test only.
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


isolated_schema_test("phase2_empty_verification")
isolated_schema_test("phase2_upgrade_verification", phase1=True)
app_engine = create_engine(url)
before = fingerprint(app_engine)
alembic(url, "upgrade", "head")
alembic(url, "check")
assert fingerprint(app_engine) == before, "Existing app records changed during migration"
print(
    "PASS: local app upgrade; all existing Phase 1 table row counts and SHA-256 fingerprints unchanged"
)
print(json.dumps({table: item["count"] for table, item in before.items()}, sort_keys=True))
(ROOT / ".runtime" / "phase2-migration-verification.json").write_text(
    json.dumps(before, indent=2), encoding="utf-8"
)
app_engine.dispose()
