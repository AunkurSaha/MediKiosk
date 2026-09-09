# Deterministic normalization fixtures

Phase 3A has **45 exact-match fixtures**: thirteen symptom/qualitative concepts in English, Bengali and Hindi, plus one uncertain phrase and one explicit unknown phrase per language. The symptom catalog is in `ai/ontology/normalization_concepts.json`; it is independent of provider implementation.

Matching performs Unicode NFC, case folding and whitespace normalization on a temporary lookup key. It never changes stored patient wording. There is no substring matching, fuzzy match, diagnosis inference, probabilistic model, medication coding or general translation. Negated statements, family-context sentences, combined symptoms and unmatched phrases deliberately return unrecognized instead of a guessed positive finding.

Fixture confidence is null. Exact-match certainty describes the explicit wording, not a confirmed clinical fact. Uncertain fixtures remain needs_verification. All machine output remains visibly not clinician verified after summary confirmation.

Eligibility is an explicit canonical-field allowlist in `normalization_policy.py` combined with short_text type. Typed boolean/numeric/duration/choice responses and AYUSH bypass the provider. Explicit unknown/not-reported/skipped states bypass the provider too, retaining an unknown result for eligible text fields.

Configuration: `CLINICAL_NORMALIZATION_PROVIDER=mock` (default) or `disabled`; timeout 0.5 seconds by default, bounded to 0.01–5 seconds. Invalid configuration fails startup; no external fallback exists. These fixtures and translations are unvalidated prototype content. Increment provider/policy/schema versions when their meaning changes; existing result snapshots remain pinned to immutable answer IDs.
