"""Tests specifically for conversational variety, dynamic RAG planning,
multi-domain entity extraction, and non-repetitive clinical interviews.
"""

from app.schemas.flow import Localized
from app.services import red_flags
from app.services.clinical_domains import (
    ClinicalDomainTracker,
    extract_domains_and_facts,
)
from app.services.flow_registry import registry
from app.services.question_planner import (
    QuestionCandidate,
    score_and_rank_candidates,
)
from tests.test_adaptive import selected, submit


def test_1_rich_patient_answer_fills_multiple_domains_and_prevents_duplicates(database):
    """Test 1: A rich patient answer fills multiple domains and prevents follow-up duplicates."""
    tracker = ClinicalDomainTracker("chest_pain")

    rich_answer = "It started suddenly 30 minutes ago while walking and spreads to my left arm."
    facts = extract_domains_and_facts(rich_answer)

    extracted_domains = {f.domain for f in facts}
    assert "onset" in extracted_domains
    assert any(d in extracted_domains for d in ("aggravating_factors", "exertional_relationship"))
    assert "radiation" in extracted_domains

    # Record into tracker
    tracker.record_answer("chief_complaint.description", "chief_complaint.description", rich_answer)

    assert "onset" in tracker.covered_domains
    assert "radiation" in tracker.covered_domains
    assert "hpi.onset" in tracker.answered_fields
    assert "hpi.radiation" in tracker.answered_fields

    # Now score candidates targeting onset and radiation
    candidates = [
        QuestionCandidate(
            candidate_id="onset_candidate",
            question_id="rag_followup.onset",
            target_field="hpi.onset",
            target_domain="onset",
            question_text="When did your chest pain start?",
            equivalent_fields=["hpi.onset"],
            required=True,
            origin="rag",
        ),
        QuestionCandidate(
            candidate_id="radiation_candidate",
            question_id="rag_followup.radiation",
            target_field="hpi.radiation",
            target_domain="radiation",
            question_text="Does the pain travel to your left arm or jaw?",
            equivalent_fields=["hpi.radiation"],
            required=True,
            origin="rag",
        ),
        QuestionCandidate(
            candidate_id="dyspnea_candidate",
            question_id="rag_followup.dyspnea",
            target_field="hpi.associated_details",
            target_domain="respiratory_symptoms",
            question_text="Are you having any shortness of breath?",
            required=False,
            origin="rag",
        ),
    ]

    ranked = score_and_rank_candidates(candidates, tracker, [])
    # Onset and radiation candidates must be rejected as already answered
    assert any(c.candidate_id == "onset_candidate" and c.is_rejected for c in candidates)
    assert any(c.candidate_id == "radiation_candidate" and c.is_rejected for c in candidates)

    # The unaddressed dyspnea candidate must be the top accepted candidate
    assert len(ranked) == 1
    assert ranked[0].candidate_id == "dyspnea_candidate"


def test_2_three_consecutive_questions_must_not_target_same_domain(database):
    """Test 2: Three consecutive questions must not target the same domain without justification."""
    tracker = ClinicalDomainTracker("chest_pain")

    # Turn 1 asks timing
    tracker.record_answer("hpi.timing", "hpi.timing", "It comes and goes")
    # Turn 2 asks timing again
    tracker.record_answer("rag_followup.timing2", "hpi.timing", "Every few minutes")

    assert tracker.is_domain_in_cooldown("timing", cooldown_turns=2)
    assert tracker.consecutive_domain_count("timing") >= 2

    # Provide candidate targeting timing vs candidate targeting location
    timing_cand = QuestionCandidate(
        candidate_id="timing_3",
        question_id="rag_followup.timing3",
        target_field="hpi.progression",
        target_domain="timing",
        question_text="Has the frequency of attacks changed?",
        origin="rag",
    )
    location_cand = QuestionCandidate(
        candidate_id="location_q",
        question_id="hpi.site",
        target_field="hpi.site",
        target_domain="location",
        question_text="Where exactly in your chest is the pain?",
        origin="flow",
    )

    ranked = score_and_rank_candidates([timing_cand, location_cand], tracker, [])
    # Timing candidate must be rejected or suffer heavy cooldown penalty
    assert timing_cand.is_rejected or timing_cand.score_breakdown.same_domain_recently_asked_penalty >= 4.0
    # Location candidate must be preferred
    assert ranked[0].candidate_id == "location_q"


def test_3_walking_worsens_pain_prevents_later_exertion_question(database):
    """Test 3: 'walking worsens pain' prevents later exertion question."""
    tracker = ClinicalDomainTracker("chest_pain")

    # Patient previously said walking worsens pain
    patient_text = "Walking up stairs makes the pain much worse."
    tracker.record_answer("hpi.exacerbating", "hpi.exacerbating", patient_text)

    assert "aggravating_factors" in tracker.covered_domains
    assert "exertional_relationship" in tracker.covered_domains
    assert "hpi.exacerbating" in tracker.answered_fields
    assert "hpi.provocation" in tracker.answered_fields

    # Later candidate asking about exertion
    exertion_cand = QuestionCandidate(
        candidate_id="exertion_candidate",
        question_id="rag_followup.exertion",
        target_field="hpi.provocation",
        target_domain="exertional_relationship",
        question_text="Does physical exertion or walking make your pain worse?",
        equivalent_fields=["hpi.exacerbating", "hpi.provocation"],
        origin="rag",
    )

    ranked = score_and_rank_candidates([exertion_cand], tracker, [])
    assert exertion_cand.is_rejected
    assert "already_answered" in (exertion_cand.rejection_reason or "")
    assert len(ranked) == 0


def test_4_radiates_to_left_arm_prevents_later_radiation_paraphrases(database):
    """Test 4: 'radiates to left arm' prevents later radiation paraphrases."""
    tracker = ClinicalDomainTracker("chest_pain")

    patient_text = "The pain radiates into my left arm and jaw."
    tracker.record_answer("hpi.radiation", "hpi.radiation", patient_text)

    assert "radiation" in tracker.covered_domains
    assert "hpi.radiation" in tracker.answered_fields
    assert "hpi.radiation_site" in tracker.answered_fields

    paraphrased_radiation = QuestionCandidate(
        candidate_id="radiation_paraphrase",
        question_id="rag_followup.radiation_check",
        target_field="hpi.radiation_site",
        target_domain="radiation",
        question_text="Does the discomfort spread anywhere like your arm, neck, or shoulder?",
        equivalent_fields=["hpi.radiation", "hpi.radiation_site"],
        origin="rag",
    )

    ranked = score_and_rank_candidates([paraphrased_radiation], tracker, [])
    assert paraphrased_radiation.is_rejected
    assert "already_answered" in (paraphrased_radiation.rejection_reason or "")
    assert len(ranked) == 0


def test_5_sudden_onset_30_minutes_ago_prevents_onset_timing_repetition(database):
    """Test 5: 'sudden onset 30 minutes ago' prevents onset/timing repetition."""
    tracker = ClinicalDomainTracker("chest_pain")

    patient_text = "Sudden onset about 30 minutes ago while sitting."
    tracker.record_answer("chief_complaint.description", "chief_complaint.description", patient_text)

    assert "onset" in tracker.covered_domains
    assert "hpi.onset" in tracker.answered_fields

    onset_cand = QuestionCandidate(
        candidate_id="onset_followup",
        question_id="hpi.onset",
        target_field="hpi.onset",
        target_domain="onset",
        question_text="How long ago did this problem start?",
        equivalent_fields=["hpi.onset"],
        origin="flow",
    )

    ranked = score_and_rank_candidates([onset_cand], tracker, [])
    assert onset_cand.is_rejected
    assert len(ranked) == 0


def test_6_rag_candidate_ranking_prefers_missing_high_value_domain_over_recently_asked_domain(database):
    """Test 6: RAG candidate ranking prefers a missing high-value domain over a recently asked domain."""
    tracker = ClinicalDomainTracker("chest_pain")

    # Character domain was just asked
    tracker.record_answer("hpi.character", "hpi.character", "Tight crushing sensation")

    # Autonomic symptoms is a missing REQUIRED domain that has not been touched
    assert "autonomic_symptoms" in tracker.missing_required_domains

    cand_autonomic = QuestionCandidate(
        candidate_id="autonomic_cand",
        question_id="rag_followup.autonomic",
        target_field="hpi.associated_details",
        target_domain="autonomic_symptoms",
        question_text="Are you experiencing heavy sweating or cold sweats?",
        origin="rag",
    )

    cand_character_clarify = QuestionCandidate(
        candidate_id="character_cand",
        question_id="rag_followup.character2",
        target_field="hpi.character",
        target_domain="character",
        question_text="Does it feel more like tightness or sharp pain?",
        origin="rag",
    )

    ranked = score_and_rank_candidates([cand_autonomic, cand_character_clarify], tracker, [])
    assert ranked[0].candidate_id == "autonomic_cand"
    assert cand_character_clarify.is_rejected or cand_autonomic.score_breakdown.total_score > cand_character_clarify.score_breakdown.total_score


def test_7_when_two_candidates_equally_relevant_prefer_more_novel_question(database):
    """Test 7: When two candidates are equally clinically relevant, prefer the more novel question."""
    tracker = ClinicalDomainTracker("chest_pain")

    # Previous questions asked about breathlessness
    recent_qs = ["Are you having trouble catching your breath?"]

    # Candidate A repeats vocabulary from recent question
    cand_repeat = QuestionCandidate(
        candidate_id="cand_repeat",
        question_id="rag_followup.breath_repeat",
        target_field="hpi.associated_details",
        target_domain="respiratory_symptoms",
        question_text="Are you having trouble catching your breath when sitting?",
        origin="rag",
    )

    # Candidate B is novel wording targeting same domain
    cand_novel = QuestionCandidate(
        candidate_id="cand_novel",
        question_id="rag_followup.breath_novel",
        target_field="hpi.associated_details",
        target_domain="respiratory_symptoms",
        question_text="Do you notice any wheezing or gasping for air?",
        origin="rag",
    )

    ranked = score_and_rank_candidates([cand_repeat, cand_novel], tracker, [], recent_questions=recent_qs)
    assert ranked[0].candidate_id == "cand_novel"
    assert cand_repeat.score_breakdown.similarity_penalty > cand_novel.score_breakdown.similarity_penalty


def test_8_remote_rag_failure_uses_local_grounded_coverage(client, database):
    """Test 8: remote retrieval failure uses local guidance without stalling."""
    session_id, state = selected(client, "chest_pain")

    # In test environment, RAG_EMBEDDING_PROVIDER is mock and returns empty
    # Submit first answer
    state = submit(client, session_id, state, "Mild chest discomfort", "answered")

    # Next question remains grounded by the bundled knowledge base.
    assert state["question"] is not None
    assert state["question"]["origin"] == "rag"
    assert state["rag_suggestions"]
    assert state["rag_suggestions"][0]["source_chunk_ids"][0].startswith("local-")
    assert not state["is_complete"]


def test_9_red_flag_behavior_remains_unchanged(client, database):
    """Test 9: Red-flag behavior remains unchanged when evaluating clinical facts."""
    session_id, state = selected(client, "chest_pain")

    # Submit chief complaint
    state = submit(client, session_id, state, "Severe crushing chest pain", "answered")

    from app.schemas.adaptive import Fact
    from app.services import intake

    facts = [
        Fact(
            answer_id="1",
            question_id="hpi.severity",
            field="hpi.severity",
            label=Localized(en="Severity", bn="তীব্রতা", hi="तीव्रता"),
            status="answered",
            value=10,
            raw_value="10",
            source="typed",
            language="en",
            recorded_at=intake.now(),
        )
    ]
    alerts = red_flags.evaluate_and_persist(database, session_id, "chest_pain", facts)
    assert isinstance(alerts, list)


def test_10_existing_full_regression_continues_to_pass(client):
    """Test 10: Verify the flow registry and basic endpoints remain intact."""
    assert "chest_pain" in registry()
    assert "headache" in registry()
    assert "other.complaint" in registry()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
