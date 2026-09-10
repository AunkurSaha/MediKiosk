"""Local PostgreSQL upgrades, data preservation and Alembic comparisons.

All destructive downgrade checks use newly generated schemas in medikiosk_test.
The application database only upgrades; existing columns/rows are fingerprinted.
"""

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
url = make_url(dotenv_values(ROOT / "backend/.env")["DATABASE_URL"])
if (
    url.get_backend_name() != "postgresql"
    or url.host not in ("localhost", "127.0.0.1")
    or url.database != "medikiosk"
):
    raise RuntimeError("Requires the existing local medikiosk PostgreSQL database.")


def run(target, *args):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT / "backend",
        env={
            **os.environ,
            "DATABASE_URL": target.render_as_string(hide_password=False),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Alembic {' '.join(args)} failed; inspect schema locally.")


def snapshot(engine, columns=None):
    inspector = inspect(engine)
    columns = columns or {
        t: [c["name"] for c in inspector.get_columns(t)]
        for t in inspector.get_table_names()
        if t != "alembic_version"
    }
    quote = engine.dialect.identifier_preparer.quote
    hashes = {}
    with engine.connect() as connection:
        for table, names in columns.items():
            rows = connection.execute(
                text(f"SELECT {','.join(map(quote, names))} FROM {quote(table)}")
            ).mappings()
            serialized = sorted(
                json.dumps(dict(r), sort_keys=True, default=str) for r in rows
            )
            hashes[table] = {
                "count": len(serialized),
                "sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
            }
    return columns, hashes


results = []
owner = create_engine(url.set(database="medikiosk_test"))
for previous in [
    None,
    "c92f104a7e21",
    "d31a204b9e02",
    "e43b205c0f13",
    "f54c306d1e24",
    "a61e405d2e31",
]:
    schema = "stabilization_" + uuid4().hex
    with owner.begin() as connection:
        # Random name; never reuse or delete an existing schema.
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    target = url.set(database="medikiosk_test").update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = create_engine(target)
    try:
        run(target, "upgrade", previous or "head")
        with engine.begin() as connection:
            patient, sid = str(uuid4()), str(uuid4())
            connection.execute(
                text(
                    "INSERT INTO patients (id,name) VALUES (:id,'Synthetic migration record')"
                ),
                {"id": patient},
            )
            connection.execute(
                text(
                    "INSERT INTO sessions (id,patient_id,hospital_token,language,status) VALUES (:id,:patient,'STABILIZATION','en','intake')"
                ),
                {"id": sid, "patient": patient},
            )
        columns, before = snapshot(engine)
        run(target, "upgrade", "head")
        assert snapshot(engine, columns)[1] == before
        run(target, "check")
        run(target, "downgrade", "a61e405d2e31")
        run(target, "upgrade", "head")
        run(target, "check")
        results.append(
            {
                "from": previous or "empty",
                "preserved": True,
                "schema_comparison": "passed",
                "downgrade_reupgrade": "passed",
            }
        )
    finally:
        engine.dispose()
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
owner.dispose()

app_engine = create_engine(url)
columns, before = snapshot(app_engine)
run(url, "upgrade", "head")
assert snapshot(app_engine, columns)[1] == before
run(url, "check")
app_engine.dispose()
artifact = {
    "isolated_upgrades": results,
    "app_preserved": before,
    "app_schema_comparison": "passed",
}
(ROOT / ".runtime/stabilization-migrations.json").write_text(
    json.dumps(artifact, indent=2), encoding="utf-8"
)
print(
    "All isolated upgrades, downgrade/reupgrade, app data fingerprints and Alembic comparisons passed."
)
