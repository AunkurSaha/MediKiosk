"""Read-only assertion for a synthetic browser-created document's persisted facts."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import models
from app.database import engine
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def verify(session_id, document_id):
    with Session(engine) as db:
        document = db.get(models.Document, document_id)
        assert document and document.session_id == session_id
        extraction = db.scalar(
            select(models.DocumentExtraction).where(
                models.DocumentExtraction.document_id == document_id
            )
        )
        assert extraction and extraction.extractor == "mock"
        data = extraction.structured_json
        model, key = (
            (models.MedicationFact, "medications")
            if data["document_type"] == "prescription"
            else (models.LabFact, "observations")
        )
        facts = list(
            db.scalars(
                select(model).where(model.document_extraction_id == extraction.id)
            )
        )
        assert len(facts) == len(data[key]) > 0
        expected = sorted(json.dumps(value, sort_keys=True) for value in data[key])
        actual = sorted(
            json.dumps(
                {key: getattr(fact, key) for key in data[key][0]}, sort_keys=True
            )
            for fact in facts
        )
        assert expected == actual
        assert all(
            f.session_id == session_id
            and f.source_text == extraction.raw_text
            and f.verification_status == "unverified"
            and f.verified_by is None
            for f in facts
        )
        print(
            json.dumps(
                {"facts": len(facts), "source_preserved": True, "unverified": True}
            )
        )


if __name__ == "__main__":
    try:
        verify(*sys.argv[1:])
    except (AssertionError, SQLAlchemyError, ValueError, TypeError, KeyError) as error:
        print(
            "Phase 7 persistence check failed: " + type(error).__name__, file=sys.stderr
        )
        raise SystemExit(1) from None
