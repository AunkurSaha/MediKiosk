# Implementation status

MediKiosk is a local, synthetic-data prototype covering the twelve phases in the
[roadmap](roadmap.md). It supports patient intake, deterministic safety screening,
document fixtures, clinician review, FHIR export, mock ABDM/HIS integration, and a
seeded demonstration journey.

## Implemented

- Patient and staff authentication flows for the local demonstration environment.
- Consent-gated, multilingual-friendly adaptive intake with touch and voice paths.
- Structured answers as the source of truth, with provenance and verification state.
- Deterministic, versioned red-flag rules and staff acknowledgement workflows.
- Document upload, validated storage, fixture extraction, medical facts, discrepancies,
  and a computed timeline.
- Doctor-controlled draft summaries, revisions, confirmation, and amendments.
- FHIR R4 document and collection bundle exports.
- Mock ABDM care-context and HIS dispatch workflows.
- Demo seeding/reset tools and browser acceptance journeys.

## Important limitations

- This is not a diagnostic or prescribing system and requires clinician review.
- Clinical rules, translations, fixtures, and question wording are not clinically validated.
- Arbitrary uploaded documents do not have production OCR; deterministic fixtures are used.
- Live NVIDIA and BHASHINI reliability is not established.
- Sarvam has synthetic transport evidence only, not physical microphone/accent acceptance.
- Demo authentication, local storage, process-local WebSockets, and mock interoperability are
  not production security or deployment architecture.
- PostgreSQL process-restart verification remains environment-dependent on Windows.

## Sources of truth

- Product scope and sequencing: [roadmap](roadmap.md)
- Architecture and boundaries: [architecture](architecture.md) and
  [decision log](decisions.md)
- API and persistence contracts: [API contract](api-contract.md) and
  [data model](data-model.md)
- Clinical and privacy constraints: [clinical scope](clinical-scope.md) and
  [security/privacy](security-privacy.md)
- Reproducible checks: [testing guide](testing.md)
- Local operation: [setup guide](setup.md)

Detailed historical implementation reports were removed during repository cleanup. Their
content remains recoverable from Git history.
