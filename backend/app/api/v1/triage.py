from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import require_triage
from app.database import get_db
from app.services import intake, triage_notifier
from app.services.staff_tickets import admit_websocket, issue_ticket

router = APIRouter()


@router.get("/queue", response_model=schemas.SessionList)
def list_waiting_patients(
    hospital_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_triage),
):
    rows = db.execute(
        select(
            models.Session,
            models.Patient.name,
            models.DoctorQueueEntry.status,
            models.DoctorQueueEntry.joined_at,
        )
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .join(models.Consent, models.Consent.session_id == models.Session.id)
        .join(models.DoctorQueueEntry, models.DoctorQueueEntry.session_id == models.Session.id)
        .where(
            models.Session.hospital_id == hospital_id,
            models.Consent.share_with_doctor.is_(True),
            models.DoctorQueueEntry.status == "WAITING",
        )
        .order_by(models.DoctorQueueEntry.joined_at, models.Session.id)
    ).all()
    return schemas.SessionList(
        items=[
            schemas.SessionListItem(
                **schemas.Session.model_validate(session).model_dump(),
                patient_name=patient_name,
                queue_status=queue_status,
                queue_joined_at=joined_at,
            )
            for session, patient_name, queue_status, joined_at in rows
        ]
    )


def _to_alert_item(
    alert: models.Alert,
    hospital_token: str | None = None,
    patient_name: str | None = None,
    hospital_id: str | None = None,
    hospital_name: str | None = None,
) -> schemas.AlertItem:
    tf_raw = alert.triggering_facts_json or []
    triggering_facts = [
        schemas.TriggeringFact.model_validate(tf) if isinstance(tf, dict) else tf for tf in tf_raw
    ]
    return schemas.AlertItem(
        id=alert.id,
        session_id=alert.session_id,
        rule_id=alert.rule_id,
        rule_version=alert.rule_version,
        priority=alert.priority,
        category=alert.category,
        reason=alert.reason,
        triggering_facts=triggering_facts,
        status=alert.status,
        revision=alert.revision,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        acknowledgement_note=alert.acknowledgement_note,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        hospital_token=hospital_token,
        patient_name=patient_name,
        hospital_id=hospital_id,
        hospital_name=hospital_name,
    )


@router.get("/alerts", response_model=schemas.AlertList)
def list_alerts(
    status: Literal["new", "acknowledged", "resolved"] | None = Query(default=None),
    priority: Literal["emergency", "urgent", "priority"] | None = Query(default=None),
    hospital_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_triage),
):
    query = (
        select(
            models.Alert,
            models.Session.hospital_token,
            models.Patient.name,
            models.Session.hospital_id,
            models.Hospital.name.label("hospital_name"),
        )
        .join(models.Session, models.Session.id == models.Alert.session_id)
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .outerjoin(models.Hospital, models.Hospital.id == models.Session.hospital_id)
    )

    if hospital_id:
        query = query.where(models.Session.hospital_id == hospital_id)
    if status:
        query = query.where(models.Alert.status == status)
    if priority:
        query = query.where(models.Alert.priority == priority)

    query = query.order_by(
        case((models.Alert.priority == "emergency", 0), else_=1).asc(),
        models.Alert.created_at.desc(),
        models.Alert.id,
    )

    rows = db.execute(query).all()

    items = [
        _to_alert_item(alert, token, name, hosp_id, hosp_name)
        for alert, token, name, hosp_id, hosp_name in rows
    ]

    # Compute overall statistics filtered by hospital if specified
    stats_query = select(models.Alert).join(
        models.Session, models.Session.id == models.Alert.session_id
    )
    if hospital_id:
        stats_query = stats_query.where(models.Session.hospital_id == hospital_id)
    all_alerts = db.scalars(stats_query).all()

    emergency_count = sum(
        1 for a in all_alerts if a.priority == "emergency" and a.status in ("new", "acknowledged")
    )
    urgent_count = sum(
        1 for a in all_alerts if a.priority == "urgent" and a.status in ("new", "acknowledged")
    )
    acknowledged_count = sum(1 for a in all_alerts if a.status == "acknowledged")

    return schemas.AlertList(
        items=items,
        total=len(items),
        emergency_count=emergency_count,
        urgent_count=urgent_count,
        acknowledged_count=acknowledged_count,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=schemas.AlertItem)
async def acknowledge_alert(
    alert_id: str,
    payload: schemas.AlertAcknowledgeRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_triage),
):
    alert_row = db.execute(
        select(models.Alert, models.Session.hospital_token, models.Patient.name)
        .join(models.Session, models.Session.id == models.Alert.session_id)
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .where(models.Alert.id == alert_id)
    ).first()

    if not alert_row:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert, token, name = alert_row
    intake.get_session(db, alert.session_id)  # serialize against reconciliation
    db.refresh(alert)
    if payload.expected_revision != alert.revision:
        raise HTTPException(
            status_code=409, detail="Alert evidence changed; reload before acknowledging."
        )
    if alert.status == "resolved":
        raise HTTPException(status_code=409, detail="The alert is resolved.")
    if alert.acknowledged_at is not None:
        return _to_alert_item(alert, token, name)
    alert.status = "acknowledged"
    alert.acknowledged_at = intake.now()
    alert.acknowledged_by = user.id
    alert.acknowledgement_note = payload.note
    alert.updated_at = intake.now()

    intake.audit(
        db,
        "alert_acknowledged",
        alert.session_id,
        user=user,
        metadata={
            "alert_id": alert_id,
            "rule_id": alert.rule_id,
            "acknowledged_by": user.id,
            "note": payload.note,
        },
    )
    db.commit()

    # Broadcast update to connected triage WebSocket clients
    alert_item = _to_alert_item(alert, token, name)
    await triage_notifier.notifier.broadcast(
        {
            "type": "alert_acknowledged",
            "alert": alert_item.model_dump(mode="json"),
        }
    )

    return alert_item


session_router = APIRouter()


@session_router.get("/{session_id}/alerts", response_model=list[schemas.AlertItem])
def get_session_alerts_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_triage),
):
    return get_session_alerts(session_id, db, user)


@router.get("/sessions/{session_id}/alerts", response_model=list[schemas.AlertItem])
def get_session_alerts(
    session_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_triage),
):
    rows = db.execute(
        select(models.Alert, models.Session.hospital_token, models.Patient.name)
        .join(models.Session, models.Session.id == models.Alert.session_id)
        .join(models.Patient, models.Patient.id == models.Session.patient_id)
        .where(models.Alert.session_id == session_id)
        .order_by(
            case((models.Alert.priority == "emergency", 0), else_=1).asc(),
            models.Alert.created_at.desc(),
            models.Alert.id,
        )
    ).all()

    return [_to_alert_item(alert, token, name) for alert, token, name in rows]


@router.post("/ws-ticket")
def websocket_ticket(user: models.User = Depends(require_triage)):
    return {"ticket": issue_ticket(user.id)}


@router.websocket("/ws")
async def triage_websocket_feed(websocket: WebSocket, db: Session = Depends(get_db)):
    if not await admit_websocket(websocket, db):
        return
    await triage_notifier.notifier.connect(websocket)
    try:
        while True:
            # Keep connection open; receive any client pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        triage_notifier.notifier.disconnect(websocket)
    except Exception:
        triage_notifier.notifier.disconnect(websocket)
