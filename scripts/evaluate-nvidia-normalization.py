"""Explicitly opt-in synthetic NVIDIA evaluation through the real API and local PostgreSQL.

Run from the project root with backend/.venv/Scripts/python.exe and --run-live.
Never runs during pytest/CI. Prints only case IDs, verdicts and technical metadata.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=8)
    args = parser.parse_args()
    if not args.run_live:
        parser.error(
            "Pass --run-live to authorize synthetic hosted calls and demo records."
        )
    load_dotenv(ROOT / "backend/.env")
    if not os.getenv("NVIDIA_API_KEY", "").strip():
        raise SystemExit("NVIDIA_API_KEY missing; no calls made.")
    target = make_url(os.environ["DATABASE_URL"])
    if (
        target.get_backend_name() != "postgresql"
        or target.host not in ("127.0.0.1", "localhost")
        or target.database != "medikiosk"
    ):
        raise SystemExit(
            "This evaluation is restricted to the local medikiosk demo database."
        )
    os.environ["CLINICAL_NORMALIZATION_PROVIDER"] = "nvidia"
    # Only this evaluation process; do not change the running app or .env.
    os.environ["CLINICAL_NORMALIZATION_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    sys.path.insert(0, str(ROOT / "backend"))
    from app import models
    from app.database import SessionLocal
    from app.main import app
    from app.services.nvidia_normalization import PROMPT_VERSION, NvidiaSettings
    from fastapi.testclient import TestClient

    settings = NvidiaSettings.from_environment()
    if (
        settings.model != "google/gemma-4-31b-it"
        or settings.base_url != "https://integrate.api.nvidia.com/v1"
    ):
        raise SystemExit(
            "Evaluation requires the explicitly requested NVIDIA model and endpoint."
        )
    cases = json.loads(
        (ROOT / "ai/normalization/nvidia_evaluation.json").read_text(encoding="utf-8")
    )["cases"]
    if args.smoke_only:
        cases = [case for case in cases if case["id"].startswith("smoke_")]
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "model": settings.model,
        "endpoint": settings.base_url + "/chat/completions",
        "prompt_version": PROMPT_VERSION,
        "timeout_seconds": settings.timeout,
        "max_tokens": settings.max_tokens,
        "content_status": "synthetic_prototype_unvalidated",
        "cases": [],
    }
    destination = ROOT / (
        ".runtime/nvidia-live-smoke.json"
        if args.smoke_only
        else ".runtime/nvidia-live-evaluation.json"
    )
    destination.parent.mkdir(exist_ok=True)
    doctor = {"X-Demo-Doctor": "true"}

    def checked(response):
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Local synthetic API operation failed: HTTP {response.status_code}"
            )
        return response.json()

    with TestClient(app, raise_server_exceptions=False) as client:
        for case in cases:
            sid = str(uuid4())
            checked(
                client.post(
                    "/api/sessions",
                    json={
                        "id": sid,
                        "patient": {
                            "name": "Synthetic NVIDIA Evaluation",
                            "demo_abha_id": None,
                        },
                        "hospital_token": "NIM-" + case["id"],
                        "language": case["language"],
                    },
                )
            )
            checked(
                client.put(
                    f"/api/sessions/{sid}/consent",
                    json={
                        "share_with_doctor": True,
                        "voice_processing": False,
                        "document_processing": False,
                    },
                )
            )
            state = checked(
                client.put(
                    f"/api/sessions/{sid}/interview/flow",
                    json={"flow_id": "chest_pain"},
                )
            )
            started = perf_counter()
            state = checked(
                client.post(
                    f"/api/sessions/{sid}/interview/answers",
                    json={
                        "request_id": str(uuid4()),
                        "expected_revision": state["revision"],
                        "question_id": state["question"]["question_id"],
                        "value": case["text"],
                        "raw_value": case["text"],
                        "language": case["language"],
                        "status": "answered",
                        "source": "typed",
                    },
                )
            )
            elapsed = round((perf_counter() - started) * 1000)
            fact = state["active_answers"][0]
            norm = fact["normalization"]
            actual = [
                {
                    "concept": f["normalized_concept"],
                    "polarity": f["polarity"],
                    "certainty": f["certainty"],
                }
                for f in norm["facts"]
            ]
            domain_pass = norm["status"] == case["expected_status"] and sorted(
                actual, key=lambda f: f["concept"]
            ) == sorted(case["expected"], key=lambda f: f["concept"])
            with SessionLocal() as db:
                row = db.get(models.NormalizationResult, norm["id"])
                answer = db.get(models.InterviewAnswer, fact["answer_id"])
                persistence_pass = (
                    row is not None
                    and row.result_json == norm
                    and answer.raw_value == case["text"]
                )
            assert persistence_pass and fact["raw_value"] == case["text"]
            assert (
                state["flow_id"] == "chest_pain"
                and state["question"]["question_id"] == "hpi.onset"
            )
            item = {
                "case": case["id"],
                "language": case["language"],
                "session_id": sid,
                "expected_status": case["expected_status"],
                "expected": case["expected"],
                "actual": actual,
                "status": norm["status"],
                "reason": norm["reason"],
                "pass": domain_pass,
                "raw_preserved": True,
                "persisted": persistence_pass,
                "normalization": norm,
                "request_latency_ms": elapsed,
                "latency_ms": norm["latency_ms"],
                "token_usage": norm["token_usage"],
            }
            if case["id"].startswith("smoke_"):
                while state["question"]:
                    state = checked(
                        client.post(
                            f"/api/sessions/{sid}/interview/answers",
                            json={
                                "request_id": str(uuid4()),
                                "expected_revision": state["revision"],
                                "question_id": state["question"]["question_id"],
                                "value": None,
                                "raw_value": "Unknown",
                                "status": "unknown",
                                "source": "typed",
                                "language": case["language"],
                            },
                        )
                    )
                checked(client.post(f"/api/sessions/{sid}/complete"))
                detail = checked(
                    client.get(f"/api/doctor/sessions/{sid}", headers=doctor)
                )
                assert (
                    detail["history"]["sections"][0]["facts"][0]["normalization"]
                    == norm
                )
                item["doctor_representation_preserved"] = True
                if case["id"] == "smoke_en":
                    checked(
                        client.put(
                            f"/api/doctor/sessions/{sid}/summary",
                            headers=doctor,
                            json={
                                "reviewed_text": "Synthetic NVIDIA evaluation: source reviewed; machine output remains unverified.",
                                "expected_version": 1,
                            },
                        )
                    )
                    checked(
                        client.post(
                            f"/api/doctor/sessions/{sid}/summary/confirm",
                            headers=doctor,
                            json={"expected_version": 2},
                        )
                    )
                    (ROOT / ".runtime/last-phase3b-e2e.json").write_text(
                        json.dumps({"sessionId": sid, "normalizationId": norm["id"]}),
                        encoding="utf-8",
                    )
            elif case["id"] == "direct_en":
                (ROOT / ".runtime/phase3b-resume.json").write_text(
                    json.dumps(
                        {
                            "sessionId": sid,
                            "normalizationId": norm["id"],
                            "questionId": state["question"]["question_id"],
                            "revision": state["revision"],
                            "text": state["question"]["text"]["en"],
                        }
                    ),
                    encoding="utf-8",
                )
            report["cases"].append(item)
            report["passed"] = sum(c["pass"] for c in report["cases"])
            report["total"] = len(report["cases"])
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        k: item[k]
                        for k in (
                            "case",
                            "pass",
                            "status",
                            "reason",
                            "persisted",
                            "latency_ms",
                            "token_usage",
                        )
                    }
                ),
                flush=True,
            )
    print(
        f"Live domain evaluation: {report['passed']}/{report['total']} passed; all raw answers/results persisted."
    )
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
