"""Exercise synthetic Phase 4 journeys against the explicit local E2E server."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

BASE = "http://127.0.0.1:8010/api"


def request(method, path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(BASE + path, data=data, headers=headers, method=method),
            timeout=30,
        ) as response:
            status = response.status
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = json.loads(exc.read())
    if status != expected:
        raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {payload}")
    return payload


def login(offset):
    phone = "9" + str(int(time.time()) % 100000000 + offset).zfill(9)
    request("POST", "/auth/otp/request", {"phone_number": phone})
    otp = request("GET", "/auth/dev/last-otp?phone_number=" + urllib.parse.quote(phone))["otp"]
    return request("POST", "/auth/otp/verify", {"phone_number": phone, "otp": otp})["token"]


def create(token, language, label):
    session_id = str(uuid4())
    session = request(
        "POST",
        "/sessions",
        {
            "id": session_id,
            "patient": {
                "name": f"Synthetic Phase 4 {label}",
                "gender": "female",
                "age_years": 36,
                "height_cm": 163,
                "weight_kg": 58,
            },
            "hospital_token": f"P4-{uuid4().hex[:10]}",
            "language": language,
        },
        token,
        201,
    )
    assert session["id"] == session_id
    request(
        "PUT",
        f"/sessions/{session_id}/consent",
        {"share_with_doctor": True, "voice_processing": False, "document_processing": False},
        token,
    )
    return session_id


def route(token, session_id, complaint, emergency=False, language="en"):
    words = {"FEVER": "Fever", "CHEST_DISCOMFORT": "Chest discomfort"}
    mapped = request(
        "POST",
        f"/sessions/{session_id}/rapid-routing/complaint/map",
        {"original_text": words[complaint], "language": language, "source": "card"},
        token,
    )
    state = request(
        "PUT",
        f"/sessions/{session_id}/rapid-routing/complaint",
        {"category": complaint, "confirmed": True, "expected_revision": mapped["revision"]},
        token,
    )
    for _ in range(10):
        if state["phase"] == "result":
            break
        question = state["question"]
        if question["input_type"] == "number":
            value = 37.5
        elif question["input_type"] == "severity":
            value = 9 if emergency else 2
        else:
            value = emergency and question["question_id"] == "rapid.chest.radiation"
        state = request(
            "POST",
            f"/sessions/{session_id}/rapid-routing/answers",
            {
                "question_id": question["question_id"],
                "value": value,
                "raw_value": str(value),
                "source": "touch" if isinstance(value, bool) else "typed",
                "language": language,
                "expected_revision": state["revision"],
            },
            token,
        )
    assert state["phase"] == "result", state
    return state["result"]


def facility(token, session_id, specialty, emergency=False):
    request(
        "PUT",
        f"/sessions/{session_id}/routing-location",
        {"source": "MANUAL_LOCALITY", "locality": "Kolkata"},
        token,
    )
    route_result = request("GET", f"/sessions/{session_id}/mediroute", token=token)
    assert route_result["status"] == "COMPLETED" and route_result["suggested_specialty"] == specialty
    if emergency:
        assert route_result["routing_state"] == "EMERGENCY"
    choice = route_result["recommendations"][0]
    if emergency:
        assert choice["emergency_available"]
    selected = request(
        "PUT",
        f"/sessions/{session_id}/mediroute/facility",
        {"facility_id": choice["facility_id"]},
        token,
    )
    assert selected["hospital_id"] == choice["facility_id"]
    return choice["facility_id"]


def interview_to_completion(token, session_id):
    state = request("GET", f"/sessions/{session_id}/interview", token=token)
    for turn in range(120):
        if state["is_complete"]:
            break
        if state["selection_required"]:
            raise AssertionError("Rapid routing did not select the interview flow")
        question = state["question"]
        assert question, state
        is_chief = question["question_id"] == "chief_complaint.description"
        state = request(
            "POST",
            f"/sessions/{session_id}/interview/answers",
            {
                "request_id": str(uuid4()),
                "expected_revision": state["revision"],
                "question_id": question["question_id"],
                "status": "answered" if is_chief else "unknown",
                "value": "Symptoms reported for clinical assessment" if is_chief else None,
                "raw_value": "Symptoms reported for clinical assessment" if is_chief else "Not known",
                "source": "typed",
                "language": "en",
            },
            token,
        )
    assert state["is_complete"], f"Interview did not complete within {turn + 1} turns"
    completed = request("POST", f"/sessions/{session_id}/complete", token=token)
    assert completed["status"] == "ready_for_review"
    return turn + 1


def doctor_match(token, session_id, specialty, facility_id):
    match = request("GET", f"/sessions/{session_id}/doctor-match", token=token)
    assert match["status"] == "COMPLETED"
    assert match["required_specialty"] == specialty
    assert match["facility_id"] == facility_id
    assert all(d["primary_specialty"] == specialty for d in match["recommendations"])
    return match


def main():
    assert request("GET", "/health")["status"] == "ok"
    assert request("GET", "/config")["local_e2e_mode"] is True, "Refusing non-E2E server"
    token_a = login(1)
    session_a = create(token_a, "en", "fever")
    assert route(token_a, session_a, "FEVER")["routing_state"] == "ROUTINE_OPD"
    facility_a = facility(token_a, session_a, "GENERAL_MEDICINE")
    first_a = doctor_match(token_a, session_a, "GENERAL_MEDICINE", facility_a)
    assert request("GET", f"/sessions/{session_a}/doctor-match", token=token_a)["id"] == first_a["id"]
    doctor_a = first_a["recommendations"][0]["doctor_id"]
    selected_a = request("PUT", f"/sessions/{session_a}/doctor-match/selection", {"doctor_id": doctor_a}, token_a)
    assert selected_a["selected_doctor_id"] == doctor_a
    recovered_a = doctor_match(token_a, session_a, "GENERAL_MEDICINE", facility_a)
    assert recovered_a["id"] == first_a["id"] and recovered_a["selected_doctor_id"] == doctor_a
    assert request("GET", f"/sessions/{session_a}", token=token_a)["session"]["selected_doctor_id"] == doctor_a
    turns_a = interview_to_completion(token_a, session_a)
    print("A PASS", session_a, "interview turns", turns_a)

    token_b = login(2)
    session_b = create(token_b, "en", "chest")
    assert route(token_b, session_b, "CHEST_DISCOMFORT")["routing_state"] == "ROUTINE_OPD"
    facility_b = facility(token_b, session_b, "CARDIOLOGY")
    match_b = doctor_match(token_b, session_b, "CARDIOLOGY", facility_b)
    assert len(match_b["recommendations"]) >= 2
    assert {d["availability_status"] for d in match_b["recommendations"]} == {"BUSY", "AVAILABLE"}
    assert not any(d["primary_specialty"] == "DERMATOLOGY" for d in match_b["recommendations"])
    doctor_b = match_b["recommendations"][0]["doctor_id"]
    request("PUT", f"/sessions/{session_b}/doctor-match/selection", {"doctor_id": doctor_b}, token_b)
    assert request("GET", f"/sessions/{session_b}", token=token_b)["session"]["selected_doctor_id"] == doctor_b
    turns_b = interview_to_completion(token_b, session_b)
    print("B PASS", session_b, "interview turns", turns_b)
    print("C PASS", [(d["primary_specialty"], d["availability_status"]) for d in match_b["recommendations"]])

    token_d = login(3)
    session_d = create(token_d, "hi", "language")
    assert route(token_d, session_d, "CHEST_DISCOMFORT", language="hi")["routing_state"] == "ROUTINE_OPD"
    facility_d = facility(token_d, session_d, "CARDIOLOGY")
    match_d = doctor_match(token_d, session_d, "CARDIOLOGY", facility_d)
    assert len(match_d["recommendations"]) >= 2
    assert "hi" in match_d["recommendations"][0]["languages"]
    assert any("hi" not in d["languages"] for d in match_d["recommendations"])
    print("D PASS", [(d["primary_specialty"], d["languages"]) for d in match_d["recommendations"]])

    token_e = login(4)
    session_e = create(token_e, "en", "emergency")
    assert route(token_e, session_e, "CHEST_DISCOMFORT", emergency=True)["routing_state"] == "EMERGENCY"
    facility(token_e, session_e, "CARDIOLOGY", emergency=True)
    bypass = request("GET", f"/sessions/{session_e}/doctor-match", token=token_e)
    assert bypass["status"] == "DOCTOR_MATCHING_BYPASSED_EMERGENCY"
    assert bypass["recommendations"] == []
    print("E PASS", session_e, bypass["status"])

    assert request("GET", f"/sessions/{session_b}/doctor-match", token=token_a, expected=403)["error"]["code"] == "FORBIDDEN"
    assert request(
        "PUT", f"/sessions/{session_b}/doctor-match/selection", {"doctor_id": doctor_b}, token_a, 403
    )["error"]["code"] == "FORBIDDEN"
    print("AUTH PASS cross-patient read and select returned 403")
    print("LIVE_LOCAL_API_E2E_VERIFIED")


if __name__ == "__main__":
    main()
