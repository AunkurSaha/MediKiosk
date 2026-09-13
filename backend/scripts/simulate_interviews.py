"""Simulate multi-turn clinical interviews for:
1. Chest pain
2. Headache
3. Other health concern (joint pain / other.complaint)

For each turn, prints:
- QUESTION
- TARGET DOMAIN
- PATIENT ANSWER
- NEW FACTS EXTRACTED
- COVERED DOMAINS
- NEXT QUESTION ORIGIN
"""

import json
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.services.clinical_domains import FIELD_TO_DOMAIN_MAP, ClinicalDomainTracker, extract_domains_and_facts
from tests.test_adaptive import payload, submit
from tests.test_workflow import consent, create


def run_simulation(client: TestClient, flow_id: str, chief_complaint_desc: str, answers_script: list[dict]):
    print("=" * 80)
    print(f"SIMULATED INTERVIEW: Flow='{flow_id}'")
    print(f"Initial Patient Statement: '{chief_complaint_desc}'")
    print("=" * 80)

    # 1. Create session & consent
    session_id, _ = create(client, language="en")
    consent(client, session_id)

    # 2. Select flow
    res = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": flow_id})
    assert res.status_code == 200, res.text
    state = res.json()

    # Pre-seed chief complaint into session structured data
    # (equivalent to triage/intake recording chief complaint)
    client.post(
        f"/api/sessions/{session_id}/interview/answers",
        json={
            "request_id": str(uuid4()),
            "expected_revision": state["revision"],
            "question_id": "chief_complaint.description",
            "status": "answered",
            "value": chief_complaint_desc,
            "raw_value": chief_complaint_desc,
            "source": "typed",
            "language": "en",
        },
    )
    # Refresh state
    get_res = client.get(f"/api/sessions/{session_id}/interview/state")
    state = get_res.json()

    turn_idx = 1
    total_answers = len(answers_script)
    script_idx = 0

    while turn_idx <= 12 and not state.get("is_complete") and state.get("question"):
        q = state["question"]
        q_id = q["question_id"]
        q_text = q["text"].get("en", str(q["text"]))
        target_field = q.get("field") or q_id
        target_domain = FIELD_TO_DOMAIN_MAP.get(target_field, "general")
        origin = q.get("origin") or ("rag" if q_id.startswith("rag_") else "flow")

        # Pick scripted patient answer
        if script_idx < total_answers:
            script_item = answers_script[script_idx]
            script_idx += 1
            patient_answer = script_item.get("answer", "I am not sure")
            ans_val = script_item.get("value", patient_answer)
            ans_status = script_item.get("status", "answered")
        else:
            patient_answer = "No other symptoms."
            ans_val = patient_answer
            ans_status = "answered"

        # Multi-domain extraction preview on this turn
        facts = extract_domains_and_facts(patient_answer)
        extracted_summary = [f"{f.domain}: {f.concept}={f.value}" for f in facts]
        if not extracted_summary:
            extracted_summary = [f"{target_domain}: {target_field}={ans_val}"]

        # Submit answer to backend
        next_state = submit(
            client,
            session_id,
            state,
            value=ans_val,
            raw_value=patient_answer,
            status=ans_status,
        )

        # Inspect covered domains from session facts
        # We can extract covered domains from current facts
        session_res = client.get(f"/api/sessions/{session_id}/interview/state")
        current_data = session_res.json()
        structured = current_data.get("structured", {})
        
        # Determine covered domains
        tracker = ClinicalDomainTracker(flow_id)
        # populate tracker with structured data
        def recurse_facts(d, prefix=""):
            for k, v in d.items():
                p = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    recurse_facts(v, p)
                elif v is not None:
                    tracker.record_answer(p, p, v)
        recurse_facts(structured)
        covered_list = sorted(list(tracker.covered_domains))

        # Determine next question origin
        next_q = next_state.get("question")
        if next_q:
            next_origin = next_q.get("origin") or ("rag" if next_q["question_id"].startswith("rag_") else "flow")
        else:
            next_origin = "flow_completed"

        print(f"\n--- TURN {turn_idx} ---")
        print(f"QUESTION:               {q_text}  (id: {q_id})")
        print(f"TARGET DOMAIN:          {target_domain}  (field: {target_field})")
        print(f"PATIENT ANSWER:         \"{patient_answer}\"")
        print(f"NEW FACTS EXTRACTED:    {', '.join(extracted_summary)}")
        print(f"COVERED DOMAINS:        {', '.join(covered_list)}")
        print(f"NEXT QUESTION ORIGIN:   {next_origin}")

        state = next_state
        turn_idx += 1

    print("\n" + "=" * 80)
    print(f"INTERVIEW SUMMARY: Flow='{flow_id}' finished with is_complete={state.get('is_complete')}, Total Turns={turn_idx - 1}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    client = TestClient(app)

    # 1. CHEST PAIN SCRIPT
    chest_pain_answers = [
        {
            "answer": "It started suddenly about 45 minutes ago while climbing stairs, and feels like heavy crushing pressure.",
            "value": "sudden, 45 minutes ago, heavy crushing pressure while climbing stairs",
        },
        {
            "answer": "Yes, it travels down my left arm into my fingers and up to my jaw.",
            "value": "radiates to left arm and jaw",
        },
        {
            "answer": "I am sweating heavily with cold sweats and feeling quite nauseated.",
            "value": "profuse diaphoresis, nausea",
        },
        {
            "answer": "I am feeling short of breath, like I can't catch a deep breath.",
            "value": "dyspnea present",
        },
        {
            "answer": "I have high blood pressure and take amlodipine daily.",
            "value": "hypertension, amlodipine 5mg",
        },
        {
            "answer": "No, I have never experienced severe pain like this before.",
            "value": False,
        },
        {
            "answer": "Resting doesn't help at all, it stays constant.",
            "value": "no relief with rest",
        },
        {
            "answer": "My father had a heart attack when he was 52.",
            "value": "family history of premature CAD (father MI age 52)",
        },
        {
            "answer": "No fever or cough.",
            "value": "no fever or cough",
        },
    ]

    # 2. HEADACHE SCRIPT
    headache_answers = [
        {
            "answer": "It came on suddenly yesterday afternoon behind my right eye and in my temple.",
            "value": "sudden onset yesterday afternoon, right retro-orbital and temporal",
        },
        {
            "answer": "It is a severe throbbing and pulsating ache, rated 8 out of 10.",
            "value": 8,
        },
        {
            "answer": "Bright room lights and loud sounds make the throbbing much worse.",
            "value": "photophobia and phonophobia present",
        },
        {
            "answer": "I see shimmering zigzag lines in my vision and feel nauseous.",
            "value": "visual aura (scintillating scotoma), nausea",
        },
        {
            "answer": "No stiff neck, no high fever, and no numbness or limb weakness.",
            "value": "no neck stiffness, no fever, no focal weakness",
        },
        {
            "answer": "I have had milder migraines in the past, but this is much more severe.",
            "value": "past history of migraine",
        },
        {
            "answer": "I took ibuprofen 400mg two hours ago with minimal relief.",
            "value": "ibuprofen 400mg with minimal relief",
        },
        {
            "answer": "Lying still in a completely dark, quiet room helps slightly.",
            "value": "relieved by dark quiet room",
        },
    ]

    # 3. OTHER HEALTH CONCERN SCRIPT (e.g. knee / joint swelling)
    other_answers = [
        {
            "answer": "My right knee has been severely swollen, warm, and painful for the past 3 days.",
            "value": "right knee swelling, warmth, pain for 3 days",
        },
        {
            "answer": "It started after I twisted it stepping off a curb.",
            "value": "precipitating factor: twisted knee",
        },
        {
            "answer": "Pain is about 7 out of 10 and I cannot bear any weight on that leg.",
            "value": 7,
        },
        {
            "answer": "No fever, no chills, and no rash.",
            "value": "no systemic signs, no fever",
        },
        {
            "answer": "I have type 2 diabetes managed with metformin.",
            "value": True,
        },
        {
            "answer": "I have had diabetes for about 5 years.",
            "value": "5 years",
        },
        {
            "answer": "No other swollen joints, only the right knee.",
            "value": "monoarticular",
        },
        {
            "answer": "Ice packs help reduce the swelling slightly.",
            "value": "ice helps mildly",
        },
    ]

    run_simulation(client, "chest_pain", "Severe crushing chest pain", chest_pain_answers)
    run_simulation(client, "headache", "Severe throbbing headache", headache_answers)
    run_simulation(client, "other.complaint", "Severe knee swelling and inability to bear weight", other_answers)
