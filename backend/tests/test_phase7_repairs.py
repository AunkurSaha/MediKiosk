from pathlib import Path

from sqlalchemy.orm import configure_mappers


def test_fact_relationships_configure_without_breaking_existing_models():
    configure_mappers()


def test_alembic_config_does_not_contain_local_credentials():
    from configparser import ConfigParser

    from sqlalchemy.engine import make_url

    config = ConfigParser()
    config.read(Path(__file__).resolve().parents[1] / "alembic.ini")
    url = make_url(config["alembic"]["sqlalchemy.url"])
    assert not bool(url.password), "Tracked migration configuration must not contain a password"


def upload(client, kind="prescription"):
    from tests.test_documents import _setup_session, fixture

    sid = _setup_session(client)
    response = client.post(
        f"/api/sessions/{sid}/documents",
        files={"file": ("synthetic.png", fixture(kind), "image/png")},
    )
    assert response.status_code == 201
    return sid, response.json()


def test_fact_extraction_retry_keeps_ids_and_source_without_logging_medical_values(
    client, database, caplog
):
    import logging

    from sqlalchemy import select

    from app import models
    from app.services.medical_extractor import extract_medical_facts

    sid, doc = upload(client)
    ext = database.get(models.DocumentExtraction, doc["extractions"][0]["id"])
    before = list(
        database.scalars(
            select(models.MedicationFact).where(models.MedicationFact.session_id == sid)
        )
    )
    assert len(before) == len(doc["extractions"][0]["structured_json"]["medications"]) > 0
    with caplog.at_level(logging.DEBUG, logger="app.services.medical_extractor"):
        extract_medical_facts(database, ext)
        database.flush()
    after = list(
        database.scalars(
            select(models.MedicationFact).where(models.MedicationFact.session_id == sid)
        )
    )
    assert {fact.id for fact in before} == {fact.id for fact in after}
    assert all(fact.source_text == ext.raw_text and fact.source_location is None for fact in after)
    assert all(fact.name not in caplog.text for fact in after)


def test_invalid_fact_collection_is_atomic(client, database):
    import pytest
    from sqlalchemy import select

    from app import models
    from app.services.medical_extractor import extract_medical_facts

    sid, doc = upload(client)
    ext = models.DocumentExtraction(
        document_id=doc["id"],
        session_id=sid,
        extractor="mock",
        extractor_version="test",
        raw_text="Synthetic source",
        structured_json={
            "document_type": "prescription",
            "medications": [{"name": "Synthetic A"}, {"name": ["invalid"]}],
        },
    )
    database.add(ext)
    database.flush()
    with pytest.raises(ValueError):
        extract_medical_facts(database, ext)
    database.flush()
    assert not list(
        database.scalars(
            select(models.MedicationFact).where(
                models.MedicationFact.document_extraction_id == ext.id
            )
        )
    )


def test_lab_materialization_preserves_missing_flag_and_unverified_source(client, database):
    from sqlalchemy import select

    from app import models

    sid, doc = upload(client, "lab_missing_flag")
    fact = database.scalar(select(models.LabFact).where(models.LabFact.session_id == sid))
    assert fact.flag is None
    assert fact.verification_status == "unverified"
    assert fact.verified_by is None
    assert fact.observation_timestamp is None
    assert (
        fact.source_text
        == database.get(models.DocumentExtraction, doc["extractions"][0]["id"]).raw_text
    )


def test_failed_fact_insert_preserves_document_without_partial_facts(client, database):
    from sqlalchemy import event, select

    from app import models

    def fail(mapper, connection, target):
        raise RuntimeError("Synthetic fact insertion failure")

    event.listen(models.MedicationFact, "before_insert", fail)
    try:
        sid, doc = upload(client)
    finally:
        event.remove(models.MedicationFact, "before_insert", fail)
    assert doc["processing_status"] == "failed"
    assert doc["extractions"][0]["raw_text"]
    assert not list(
        database.scalars(
            select(models.MedicationFact).where(models.MedicationFact.session_id == sid)
        )
    )
    assert database.get(models.Document, doc["id"]) is not None


def test_phase7_migration_matches_models_and_preserves_existing_scaffold(tmp_path):
    import os
    import subprocess
    import sys

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, text

    from app.database import Base

    backend = Path(__file__).resolve().parents[1]
    url = "sqlite:///" + str(tmp_path / "migration.sqlite")

    def migrate(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, "Isolated migration failed"

    migrate("upgrade", "1dc135740d9c")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO patients (id,name,created_at) VALUES ('p','Synthetic',CURRENT_TIMESTAMP)"
            )
        )
        db.execute(
            text(
                "INSERT INTO sessions (id,patient_id,hospital_token,language,status,created_at,started_at) VALUES ('s','p','SYNTHETIC','en','intake',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        db.execute(
            text(
                "INSERT INTO timeline_fact (id,session_id,source_type,fact_type,fact_data,timestamp_precision,is_approximate) VALUES ('t','s','document','source_record','Synthetic original','unknown',1)"
            )
        )
        before = dict(db.execute(text("SELECT * FROM timeline_fact")).mappings().one())
    for command in [("upgrade", "head"), ("downgrade", "1dc135740d9c"), ("upgrade", "head")]:
        migrate(*command)
        with engine.connect() as db:
            assert dict(db.execute(text("SELECT * FROM timeline_fact")).mappings().one()) == before
    with engine.connect() as db:
        # Phase 1's historical SQLite users.email constraint differs from PostgreSQL.
        # This regression compares every Phase 7 table, column, FK and index;
        # the full production-dialect comparison is run by the PostgreSQL verifier.
        context = MigrationContext.configure(
            db,
            opts={
                "include_object": lambda obj, name, kind, reflected, compare_to: (
                    kind != "table" or name in {"medication_fact", "lab_fact", "timeline_fact"}
                )
            },
        )
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()
