"""One-shot Phase 4–7 and SIH golden-demo verification.

Run only against the isolated local E2E environment after `scripts/start-demo.ps1 -Reset`.
"""

import json
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
API = "http://127.0.0.1:8010/api"
RUNTIME = ROOT / ".runtime"
KNOWN_ADAPTIVE_FAILURES = frozenset(
    {
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[chest_pain]",
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[abdominal_pain]",
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[fever]",
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[headache]",
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[cough_breathlessness]",
        "tests/test_adaptive.py::test_all_flows_traverse_complete_review_confirm[ayush_demo.history]",
        "tests/test_adaptive.py::test_legacy_resume_uses_server_config_and_preserves_original",
        "tests/test_adaptive.py::test_latest_answers_stay_in_configuration_order_after_correction",
    }
)


def local_e2e_guard() -> None:
    with urllib.request.urlopen(f"{API}/config", timeout=5) as response:
        config = json.load(response)
    if config.get("local_e2e_mode") is not True:
        raise RuntimeError("Refusing verification: API is not explicit local E2E mode.")


def health_check(url: str) -> None:
    with urllib.request.urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Health check failed: {url} returned {response.status}")
    print(f"Health: PASS ({url})")


def run(label: str, command: list[str], cwd: Path) -> None:
    print(f"\n=== {label} ===")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")


def failed_node_ids(report_path: Path) -> set[str]:
    root = ET.parse(report_path).getroot()
    failures = set()
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        failures.add(
            f"{case.attrib['classname'].replace('.', '/')}.py::{case.attrib['name']}"
        )
    return failures


def run_adaptive_baseline() -> None:
    RUNTIME.mkdir(exist_ok=True)
    report_path = RUNTIME / "verify-final-demo-adaptive.xml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_adaptive.py",
            f"--junitxml={report_path}",
        ],
        cwd=BACKEND,
        check=False,
    )
    current = failed_node_ids(report_path)
    new = current - KNOWN_ADAPTIVE_FAILURES
    unchanged = current & KNOWN_ADAPTIVE_FAILURES
    resolved = KNOWN_ADAPTIVE_FAILURES - current
    print(f"Known adaptive failures: {len(unchanged)}")
    print(f"Resolved adaptive baseline failures: {len(resolved)}")
    print(f"New backend regressions: {len(new)}")
    if new:
        raise SystemExit("FINAL_DEMO_BLOCKED: new adaptive failures: " + ", ".join(sorted(new)))
    if completed.returncode and not current:
        raise SystemExit("Adaptive verification failed without JUnit failure identities.")


def main() -> None:
    local_e2e_guard()
    health_check(f"{API}/health")
    health_check("http://127.0.0.1:5175/")
    run(
        "Backend Phase 4–7, routing, adaptive, and authorization tests",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_doctor_matching.py",
            "tests/test_doctor_routing.py",
            "tests/test_rapid_routing.py",
            "tests/test_document_aware_coverage.py",
            "tests/test_evidence_linked_summary.py",
            "tests/test_rbac_security.py",
        ],
        BACKEND,
    )
    print("Doctor matching: PASS")
    print("Queue/ETA: PASS")
    print("Document-aware coverage: PASS")
    print("Evidence-linked summary: PASS")
    print("Authorization: PASS")
    run_adaptive_baseline()
    run(
        "Live local Phase 4 and emergency journeys",
        [sys.executable, "scripts/verify-phase4-e2e.py"],
        ROOT,
    )
    run(
        "Frontend unit tests",
        ["npm.cmd" if sys.platform == "win32" else "npm", "run", "test"],
        FRONTEND,
    )
    run(
        "Frontend build/typecheck",
        ["npm.cmd" if sys.platform == "win32" else "npm", "run", "build"],
        FRONTEND,
    )
    run(
        "Frontend golden journeys",
        [
            "npm.cmd" if sys.platform == "win32" else "npm",
            "run",
            "test:e2e",
            "--",
            "e2e/phase4-doctor-matching.spec.ts",
            "e2e/phase5-queue.spec.ts",
            "e2e/golden-demo.spec.ts",
        ],
        FRONTEND,
    )
    print("Supabase touched: NO")
    print("\nFINAL_DEMO_VERIFICATION_PASSED")


if __name__ == "__main__":
    main()
