"""Verify empty, Phase 1 and Phase 2 upgrades and preserve all existing local app rows."""

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
    tables = tables if tables is not None else [t for t in inspect(engine).get_table_names() if t != "alembic_version"]
    with engine.connect() as connection:
        result = {}
        for table in tables:
            # Names originate from SQLAlchemy inspection; quote via the dialect.
            quoted = engine.dialect.identifier_preparer.quote(table)
            rows = connection.execute(text(f"SELECT * FROM {quoted}")).mappings().all()
            serialized = sorted(json.dumps(dict(row), default=str, sort_keys=True) for row in rows)
            result[table] = {"count": len(rows), "sha256": hashlib.sha256("\\n".join(serialized).encode()).hexdigest()}
        return result


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


def isolated_schema_test(schema, previous=None):
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
            if previous == "d31a204b9e02":
                snapshot = (ROOT / "ai/complaint_flows/legacy/intake.json").read_text(encoding="utf-8")
                with engine.begin() as connection:
                    connection.execute(text("INSERT INTO interview_runs (session_id,flow_id,flow_version,flow_snapshot,cursor,revision) VALUES (:session,'legacy.intake','1.0.0',CAST(:snapshot AS json),'onset_duration',1)"), {"session": session, "snapshot": snapshot})
                    connection.execute(text("INSERT INTO interview_requests (session_id,request_id,payload_hash) VALUES (:session,:request,'synthetic-hash')"), {"session": session, "request": str(uuid4())})
            before = fingerprint(engine)
        alembic(scoped, "upgrade", "head")
        alembic(scoped, "check")
        assert {"interview_runs", "interview_requests", "normalization_results"} <= set(inspect(engine).get_table_names())
        if previous:
            assert fingerprint(engine, before) == before
        print(
            f"PASS: upgrade from {previous or 'empty schema'}; original rows preserved; Alembic check clean"
        )
    finally:
        engine.dispose()
        # These fixed schemas were created by this invocation in medikiosk_test only.
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


isolated_schema_test("phase3a_empty_verification")
isolated_schema_test("phase3a_phase1_verification", previous="c92f104a7e21")
isolated_schema_test("phase3a_phase2_verification", previous="d31a204b9e02")
app_engine = create_engine(url)
before = fingerprint(app_engine)
alembic(url, "upgrade", "head")
alembic(url, "check")
assert fingerprint(app_engine, before) == before, "Existing app records changed during migration"
print(
    "PASS: local app upgrade; all existing table row counts and SHA-256 fingerprints unchanged"
)
print(json.dumps({table: item["count"] for table, item in before.items()}, sort_keys=True))
(ROOT / ".runtime" / "phase3a-migration-verification.json").write_text(
    json.dumps(before, indent=2), encoding="utf-8"
)
app_engine.dispose()
