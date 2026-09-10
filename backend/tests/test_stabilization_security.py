"""Regression coverage for the independent 2026-09-09 audit."""

import pytest
from starlette.websockets import WebSocketDisconnect

from app import models
from app.api.deps import DEMO_DOCTOR_ID
from app.services import red_flags
from tests.test_adaptive import selected
from tests.test_red_flags import _make_fact

STAFF = {"X-Demo-Doctor": "true"}


@pytest.mark.parametrize("demo", ["true", "false"])
def test_staff_routes_reject_anonymous(client, demo, monkeypatch):
    sid, _ = selected(client)
    monkeypatch.setenv("DEMO_MODE", demo)
    for path in [
        "/api/triage/alerts",
        f"/api/sessions/{sid}/alerts",
        f"/api/triage/sessions/{sid}/alerts",
        f"/api/sessions/{sid}/documents",
        f"/api/sessions/{sid}/documents/missing",
        f"/api/sessions/{sid}/documents/missing/file",
    ]:
        assert client.get(path).status_code == 401, path
    assert (
        client.post(
            f"/api/sessions/{sid}/documents/missing/extractions/missing/verify",
            json={"status": "verified"},
        ).status_code
        == 401
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/triage/ws"):
            pass


def test_ack_actor_is_server_owned_and_retry_preserves_attribution(client, database):
    sid, _ = selected(client)
    alert = red_flags.evaluate_and_persist(
        database,
        sid,
        "chest_pain",
        [_make_fact("hpi.severity", 9), _make_fact("hpi.radiation", True)],
    )[0]
    database.commit()
    url = f"/api/triage/alerts/{alert.id}/acknowledge"
    assert client.post(url, json={"note": "Reviewed"}).status_code == 401
    assert client.post(url, headers=STAFF, json={"acknowledged_by": "Forged"}).status_code == 422
    first = client.post(url, headers=STAFF, json={"note": "Reviewed"})
    assert first.status_code == 200
    assert first.json()["acknowledged_by"] == DEMO_DOCTOR_ID
    second = client.post(url, headers=STAFF, json={"note": "Overwrite"})
    assert second.json()["acknowledged_at"] == first.json()["acknowledged_at"]
    assert second.json()["acknowledgement_note"] == "Reviewed"


def test_websocket_ticket_requires_identity_origin_and_is_single_use(client):
    assert client.post("/api/triage/ws-ticket").status_code == 401
    ticket = client.post("/api/triage/ws-ticket", headers=STAFF).json()["ticket"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/api/triage/ws",
            subprotocols=["medikiosk", ticket],
            headers={"Origin": "https://attacker.invalid"},
        ):
            pass
    ticket = client.post("/api/triage/ws-ticket", headers=STAFF).json()["ticket"]
    options = {
        "subprotocols": ["medikiosk", ticket],
        "headers": {"Origin": "http://127.0.0.1:5175"},
    }
    with client.websocket_connect("/api/triage/ws", **options) as ws:
        assert ws.accepted_subprotocol == "medikiosk"
        ws.send_text("ping")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/triage/ws", **options):
            pass


def test_document_review_is_attributed_audited_and_locked(client, database):
    sid, _ = selected(client)
    doc = models.Document(
        session_id=sid,
        object_key="synthetic",
        original_filename="synthetic.png",
        media_type="image/png",
        file_size_bytes=1,
        sha256_hash="0" * 64,
        document_type="other",
        processing_status="completed",
    )
    database.add(doc)
    database.flush()
    ext = models.DocumentExtraction(
        document_id=doc.id,
        session_id=sid,
        extractor="mock",
        extractor_version="fixture",
        structured_json={},
        raw_text="Synthetic",
    )
    database.add(ext)
    database.commit()
    url = f"/api/sessions/{sid}/documents/{doc.id}/extractions/{ext.id}/verify"
    assert (
        client.post(
            url, headers=STAFF, json={"status": "verified", "verified_by": "Forged"}
        ).status_code
        == 422
    )
    result = client.post(url, headers=STAFF, json={"status": "verified", "notes": "First review"})
    assert result.status_code == 200
    assert result.json()["verified_by"] == DEMO_DOCTOR_ID
    assert client.post(url, headers=STAFF, json={"status": "rejected"}).status_code == 409
    assert (
        client.post(
            url,
            headers=STAFF,
            json={"status": "rejected", "expected_status": "verified", "expected_version": 1},
        ).status_code
        == 200
    )
    from sqlalchemy import select

    events = database.scalars(
        select(models.AuditLog).where(models.AuditLog.action == "document_extraction_verified")
    ).all()
    assert len(events) == 2
    assert all(event.actor_user_id == DEMO_DOCTOR_ID for event in events)
    assert events[-1].metadata_json["previous"]["notes"] == "First review"
    database.get(models.Session, sid).status = "confirmed"
    database.commit()
    assert (
        client.post(
            url,
            headers=STAFF,
            json={"status": "verified", "expected_status": "rejected", "expected_version": 2},
        ).status_code
        == 409
    )
    assert client.get(f"/api/sessions/{sid}").json()["documents"] == []
