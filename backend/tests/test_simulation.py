"""Simulate multi-turn clinical interviews for:
1. Chest pain
2. Headache
3. Other health concern (joint pain / other.complaint)

For each turn, prints:
QUESTION
TARGET DOMAIN
PATIENT ANSWER
NEW FACTS EXTRACTED
COVERED DOMAINS
NEXT QUESTION ORIGIN
"""

from fastapi.testclient import TestClient

from app.services.clinical_domains import FIELD_TO_DOMAIN_MAP, extract_domains_and_facts
from tests.test_adaptive import submit
from tests.test_workflow import consent, create


def run_interview_simulation(client: TestClient, flow_id: str, chief_complaint_desc: str, answers_script: list[dict]):
    print("\n" + "=" * 80)
    print(f"SIMULATED INTERVIEW: Flow = '{flow_id}'")
    print(f"Initial Patient Statement: '{chief_complaint_desc}'")
    print("=" * 80)

    # 1. Create session & consent
    session_id, _ = create(client, language="en")
    consent(client, session_id)

    # 2. Select flow
    res = client.put(f"/api/sessions/{session_id}/interview/flow", json={"flow_id": flow_id})
    assert res.status_code == 200, res.text
    state = res.json()

    turn_idx = 1
    total_answers = len(answers_script)
    script_idx = 0
    history_records = []

    while turn_idx <= 12 and not state.get("is_complete") and state.get("question"):
        q = state["question"]
        q_id = q["question_id"]
        q_text = q["text"].get("en", str(q["text"]))
        target_field = q.get("field") or q_id
        target_domain = FIELD_TO_DOMAIN_MAP.get(target_field, "general")
        # Pick scripted patient answer
        if script_idx < total_answers:
            script_item = answers_script[script_idx]
            script_idx += 1
            patient_answer = script_item.get("answer", "No other symptoms.")
            ans_val = script_item.get("value", patient_answer)
            ans_status = script_item.get("status", "answered")
        else:
            patient_answer = "No other symptoms."
            ans_val = patient_answer
            ans_status = "answered"

        # Multi-domain extraction preview on this turn
        facts = extract_domains_and_facts(patient_answer)
        extracted_summary = [f"{f.domain}: {f.concept}={f.evidence}" for f in facts]
        if not extracted_summary:
            extracted_summary = [f"{target_domain}: {target_field}={patient_answer}"]

        q_type = q.get("type", "short_text")
        if q_type == "short_text":
            ans_val = patient_answer
        elif q_type == "duration":
            ans_val = {"amount": 2, "unit": "hours"}
        elif q_type == "boolean":
            lower_ans = patient_answer.lower()
            if any(w in lower_ans for w in ["no ", "never", "not ", "no,"]):
                ans_val = False
            else:
                ans_val = True
        elif q_type in ("number", "severity"):
            ans_val = 7
        elif q_type in ("single_choice", "multiple_choice"):
            opts = [o["value"] for o in q.get("options", [])]
            ans_val = opts[0] if opts else "none"
        else:
            ans_val = patient_answer

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
        session_res = client.get(f"/api/sessions/{session_id}/interview")
        current_data = session_res.json()
        covered_list = sorted(current_data.get("covered_domains", []))

        # Determine next question origin
        next_q = next_state.get("question")
        if next_q:
            next_origin = next_q.get("origin") or ("rag" if next_q["question_id"].startswith("rag_") else "flow")
        else:
            next_origin = "flow_completed"

        record = {
            "turn": turn_idx,
            "question": q_text,
            "question_id": q_id,
            "target_domain": target_domain,
            "target_field": target_field,
            "patient_answer": patient_answer,
            "new_facts": extracted_summary,
            "covered_domains": covered_list,
            "next_origin": next_origin,
        }
        history_records.append(record)

        print(f"\n--- TURN {turn_idx} ---")
        print(f"QUESTION:               {q_text}  [id: {q_id}]")
        print(f"TARGET DOMAIN:          {target_domain}  [field: {target_field}]")
        print(f"PATIENT ANSWER:         \"{patient_answer}\"")
        print(f"NEW FACTS EXTRACTED:    {', '.join(extracted_summary)}")
        print(f"COVERED DOMAINS:        {', '.join(covered_list)}")
        print(f"NEXT QUESTION ORIGIN:   {next_origin}")

        state = next_state
        turn_idx += 1

    print("\n" + "=" * 80)
    print(f"INTERVIEW SUMMARY: Flow='{flow_id}' Complete={state.get('is_complete')}, Turns={len(history_records)}")
    print("=" * 80 + "\n")
    assert len(history_records) >= 6, f"Expected at least 6 turns, got {len(history_records)}"
    return history_records


def test_simulation_chest_pain(client):
    """Simulate 8-12 turn interview for chest pain."""
    answers = [
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
    records = run_interview_simulation(client, "chest_pain", "Severe crushing chest pain", answers)
    # Verify variety: check no consecutive questions targeted the exact same domain
    domains = [r["target_domain"] for r in records]
    for i in range(len(domains) - 2):
        if domains[i] != "general":
            assert not (domains[i] == domains[i + 1] == domains[i + 2]), (
                f"3 consecutive questions targeted the same domain '{domains[i]}' at turns {i+1}, {i+2}, {i+3}"
            )


def test_simulation_headache(client):
    """Simulate 8-12 turn interview for headache."""
    answers = [
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
    records = run_interview_simulation(client, "headache", "Severe throbbing headache", answers)
    domains = [r["target_domain"] for r in records]
    for i in range(len(domains) - 2):
        if domains[i] != "general":
            assert not (domains[i] == domains[i + 1] == domains[i + 2]), (
                f"3 consecutive questions targeted the same domain '{domains[i]}' at turns {i+1}, {i+2}, {i+3}"
            )


def test_simulation_other_complaint(client):
    """Simulate 8-12 turn interview for other health concern."""
    answers = [
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
    records = run_interview_simulation(client, "other.complaint", "Severe knee swelling and inability to bear weight", answers)
    domains = [r["target_domain"] for r in records]
    for i in range(len(domains) - 2):
        if domains[i] != "general":
            assert not (domains[i] == domains[i + 1] == domains[i + 2]), (
                f"3 consecutive questions targeted the same domain '{domains[i]}' at turns {i+1}, {i+2}, {i+3}"
            )
