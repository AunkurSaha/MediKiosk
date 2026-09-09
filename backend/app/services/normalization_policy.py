"""Explicit eligibility. No flow decisions and no AYUSH interpretation."""

POLICY_VERSION = "1.0"
NORMALIZABLE_FIELDS = frozenset(
    {
        "chief_complaint.description",
        "hpi.site",
        "hpi.character",
        "hpi.radiation_site",
        "hpi.associated_details",
        "hpi.exacerbating",
        "hpi.relieving",
        "hpi.bowel_details",
        "hpi.previous_details",
        "hpi.travel_details",
        "hpi.sputum_details",
        "hpi.activity",
        "past_medical_history.diabetes_care",
        "past_medical_history.details",
        "past_surgical_history.details",
        "medications.details",
        "allergies.details",
        "family_history.details",
        "review_of_systems.details",
        # Compatibility for existing Phase 1 clients; typed Phase 2 durations bypass this service.
        "chief_complaint",
        "onset_duration",
        "medications",
        "allergies",
        "past_history",
    }
)


def eligible(question):
    return question.type == "short_text" and question.field in NORMALIZABLE_FIELDS
