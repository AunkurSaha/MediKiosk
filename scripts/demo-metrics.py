"""Print runtime-derived metrics for one local synthetic demo session."""

import argparse
import json
import urllib.request

API = "http://127.0.0.1:8010/api"


def get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        API + path,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_id")
    parser.add_argument("patient_token", help="Bearer token for the synthetic session owner")
    parser.add_argument("--doctor-token", help="Assigned doctor's bearer token")
    args = parser.parse_args()
    with urllib.request.urlopen(f"{API}/config", timeout=5) as response:
        if json.load(response).get("local_e2e_mode") is not True:
            raise RuntimeError("Metrics are restricted to local E2E mode.")

    sid = args.session_id
    token = args.patient_token
    interview = get(f"/sessions/{sid}/interview", token)
    rapid = get(f"/sessions/{sid}/rapid-routing", token)
    coverage = get(f"/sessions/{sid}/coverage", token)
    document_metrics = get(f"/sessions/{sid}/coverage/demo-metrics", token)
    doctor_match = get(f"/sessions/{sid}/doctor-match", token)
    queue = get(f"/sessions/{sid}/queue-estimate", token)
    output = {
        "session_id": sid,
        "interview_answers_recorded": len(interview.get("history", {}).get("sections", [])),
        "questions_without_document_context": document_metrics[
            "questions_without_document_context"
        ],
        "questions_with_document_context": document_metrics["questions_with_document_context"],
        "questions_avoided": document_metrics["questions_avoided"],
        "document_confirmation_questions": document_metrics["confirmation_questions_added"],
        "routing_state": (rapid.get("result") or {}).get("routing_state"),
        "matching_doctors": len(doctor_match.get("recommendations", [])),
        "queue_position": queue.get("queue_position"),
        "estimated_wait_minutes": queue.get("estimated_wait_minutes"),
        "coverage": {
            key: coverage[key]
            for key in ("confirmed", "document_supported_unconfirmed", "conflicted", "missing")
        },
    }
    if args.doctor_token:
        summary = get(f"/doctor/sessions/{sid}/summary", args.doctor_token)
        output["evidence_backed_summary_items"] = len(summary.get("evidence") or [])
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
