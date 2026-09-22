"""Exercise Phase 5 queue journeys against the explicit local E2E server only."""

import importlib.util
from pathlib import Path


def load_phase4_helpers():
    path = Path(__file__).with_name("verify-phase4-e2e.py")
    spec = importlib.util.spec_from_file_location("phase4_e2e", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Phase 4 E2E helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_patient(p4, token, label):
    session_id = p4.create(token, "en", label)
    assert p4.route(token, session_id, "FEVER")["routing_state"] == "ROUTINE_OPD"
    facility_id = p4.facility(token, session_id, "GENERAL_MEDICINE")
    return session_id, facility_id


def main():
    p4 = load_phase4_helpers()
    assert p4.request("GET", "/config")["local_e2e_mode"] is True, (
        "Refusing non-E2E server"
    )

    patient_a_token = p4.login(51)
    session_a, facility_id = prepare_patient(p4, patient_a_token, "queue-a")
    doctor_login = p4.request(
        "POST",
        "/auth/demo-login",
        {"role": "doctor", "hospital_id": facility_id, "specialty": "GENERAL_MEDICINE"},
    )
    doctor_token = doctor_login["token"]
    doctor_id = doctor_login["user"]["id"]
    match_a = p4.doctor_match(
        patient_a_token, session_a, "GENERAL_MEDICINE", facility_id
    )
    assert doctor_id in {item["doctor_id"] for item in match_a["recommendations"]}
    p4.request(
        "PUT",
        f"/sessions/{session_a}/doctor-match/selection",
        {"doctor_id": doctor_id},
        patient_a_token,
    )
    p4.interview_to_completion(patient_a_token, session_a)
    queue_a = p4.request(
        "GET", f"/sessions/{session_a}/queue-estimate", token=patient_a_token
    )
    assert queue_a["position"] == 1 and queue_a["patients_ahead"] == 0
    assert queue_a["visit_token"].startswith("MK-") and queue_a["is_estimate"] is True
    assert (
        p4.request("POST", f"/sessions/{session_a}/complete", token=patient_a_token)[
            "status"
        ]
        == "ready_for_review"
    )
    assert (
        p4.request(
            "GET", f"/sessions/{session_a}/queue-estimate", token=patient_a_token
        )["visit_token"]
        == queue_a["visit_token"]
    )
    print("SCENARIO 1 PASS", queue_a["visit_token"], "position", queue_a["position"])

    patient_b_token = p4.login(52)
    session_b, facility_b = prepare_patient(p4, patient_b_token, "queue-b")
    assert facility_b == facility_id
    match_b = p4.doctor_match(
        patient_b_token, session_b, "GENERAL_MEDICINE", facility_b
    )
    assert doctor_id in {item["doctor_id"] for item in match_b["recommendations"]}
    p4.request(
        "PUT",
        f"/sessions/{session_b}/doctor-match/selection",
        {"doctor_id": doctor_id},
        patient_b_token,
    )
    p4.interview_to_completion(patient_b_token, session_b)
    queue_b = p4.request(
        "GET", f"/sessions/{session_b}/queue-estimate", token=patient_b_token
    )
    assert queue_b["visit_token"] != queue_a["visit_token"]
    assert queue_b["position"] == 2 and queue_b["patients_ahead"] == 1
    assert queue_b["estimated_wait_minutes"] == 12
    print("SCENARIO 2 PASS", queue_b["visit_token"], "position", queue_b["position"])

    for status in ("CALLED", "IN_CONSULTATION", "COMPLETED"):
        p4.request(
            "PUT",
            f"/doctor/sessions/{session_a}/queue",
            {"status": status},
            doctor_token,
        )
    advanced_b = p4.request(
        "GET", f"/sessions/{session_b}/queue-estimate", token=patient_b_token
    )
    assert advanced_b["position"] == 1 and advanced_b["patients_ahead"] == 0
    assert advanced_b["estimated_wait_minutes"] == 0
    print("SCENARIO 3 PASS position", advanced_b["position"])

    emergency_token = p4.login(53)
    emergency_session = p4.create(emergency_token, "en", "queue-emergency")
    assert (
        p4.route(
            emergency_token, emergency_session, "CHEST_DISCOMFORT", emergency=True
        )["routing_state"]
        == "EMERGENCY"
    )
    p4.facility(emergency_token, emergency_session, "CARDIOLOGY", emergency=True)
    missing = p4.request(
        "GET",
        f"/sessions/{emergency_session}/queue-estimate",
        token=emergency_token,
        expected=404,
    )
    assert missing["error"]["code"] == "QUEUE_ENTRY_NOT_FOUND"
    print("SCENARIO 4 PASS emergency queue bypass")

    forbidden = p4.request(
        "GET",
        f"/sessions/{session_b}/queue-estimate",
        token=patient_a_token,
        expected=403,
    )
    assert forbidden["error"]["code"] == "FORBIDDEN"
    print("SCENARIO 5 PASS cross-patient read returned 403")
    print("LIVE_LOCAL_QUEUE_E2E_VERIFIED")


if __name__ == "__main__":
    main()
