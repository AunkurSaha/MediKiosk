"""Verify Phase 6 document ingestion and OCR migration compatibility and table structure."""

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
                raise RuntimeError("Phase 6 upgrade altered existing user rows or tables.")

            # Verify new tables are present
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            for required_table in ("documents", "document_extractions"):
                if required_table not in tables:
                    raise RuntimeError(f"{required_table} table missing after upgrade to head.")

            # Verify columns for documents table
            doc_cols = {c["name"] for c in inspector.get_columns("documents")}
            expected_doc_cols = {
                "id", "session_id", "object_key", "original_filename",
                "media_type", "file_size_bytes", "sha256_hash", "document_type",
                "document_date", "processing_status", "created_at", "updated_at"
            }
            if not expected_doc_cols.issubset(doc_cols):
                missing = expected_doc_cols - doc_cols
                raise RuntimeError(f"Missing columns from documents table: {missing}")

            # Verify columns for document_extractions table
            ext_cols = {c["name"] for c in inspector.get_columns("document_extractions")}
            expected_ext_cols = {
                "id", "document_id", "session_id", "extractor",
                "extractor_version", "raw_text", "structured_json", "confidence",
                "verification_status", "verified_by", "verified_at",
                "verification_notes", "created_at", "updated_at"
            }
            if not expected_ext_cols.issubset(ext_cols):
                missing = expected_ext_cols - ext_cols
                raise RuntimeError(f"Missing columns from document_extractions table: {missing}")

            # Test inserting into documents and document_extractions
            doc_id = str(uuid4())
            ext_id = str(uuid4())
            with engine.begin() as connection:
                connection.execute(
                    text("""
                        INSERT INTO documents (
                            id, session_id, object_key, original_filename, media_type,
                            file_size_bytes, sha256_hash, document_type, processing_status, created_at
                        ) VALUES (
                            :id, :session_id, 'obj_key_123', 'prescription.jpg', 'image/jpeg',
                            1024, 'dummy_hash', 'prescription', 'completed', CURRENT_TIMESTAMP
                        )
                    """),
                    {"id": doc_id, "session_id": session},
                )
                connection.execute(
                    text("""
                        INSERT INTO document_extractions (
                            id, document_id, session_id, extractor, extractor_version,
                            raw_text, structured_json, confidence, verification_status, created_at
                        ) VALUES (
                            :id, :document_id, :session_id, 'mock_ocr', '1.0.0',
                            'Tab Paracetamol 500mg', '{"medications": []}'::json, 0.95, 'unverified', CURRENT_TIMESTAMP
                        )
                    """),
                    {"id": ext_id, "document_id": doc_id, "session_id": session},
                )

            # Test cascade delete: deleting session removes documents and extractions
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM sessions WHERE id = :session_id"),
                    {"session_id": session},
                )
                remaining_docs = connection.execute(
                    text("SELECT count(*) FROM documents WHERE id = :id"),
                    {"id": doc_id},
                ).scalar()
                remaining_exts = connection.execute(
                    text("SELECT count(*) FROM document_extractions WHERE id = :id"),
                    {"id": ext_id},
                ).scalar()
                if remaining_docs != 0 or remaining_exts != 0:
                    raise RuntimeError("Cascade delete on session_id did not remove documents or extractions.")

            # Test downgrade to Phase 5
            alembic(scoped, "downgrade", previous)
            downgraded_tables = inspect(engine).get_table_names()
            if "documents" in downgraded_tables or "document_extractions" in downgraded_tables:
                raise RuntimeError("Downgrade to Phase 5 failed to drop Phase 6 tables.")

            # Test re-upgrade to head
            alembic(scoped, "upgrade", "head")
            reupgraded_tables = inspect(engine).get_table_names()
            if "documents" not in reupgraded_tables or "document_extractions" not in reupgraded_tables:
                raise RuntimeError("Re-upgrade to head failed to recreate Phase 6 tables.")

        else:
            # Fresh install directly to head
            alembic(scoped, "upgrade", "head")
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            if "documents" not in tables or "document_extractions" not in tables:
                raise RuntimeError("Phase 6 tables missing from fresh upgrade to head.")
    finally:
        engine.dispose()
        with owner.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


def main():
    print("Testing fresh database upgrade to head in isolated schema...")
    isolated_schema_test("phase6_verify_fresh")
    print("Testing upgrade from Phase 5 (f54c306d1e24) to Phase 6 head...")
    isolated_schema_test("phase6_verify_upgrade", previous="f54c306d1e24")
    print("Phase 6 migration verification passed: documents and document_extractions tables, constraints, and cascade validated.")


if __name__ == "__main__":
    main()
