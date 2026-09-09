# Authoritative interview configuration

These are the only runtime question/branch definitions. The frontend receives questions from the backend and does not import these files. All wording and translations are **prototype, clinically unvalidated content**.

Five standard flows and one isolated AYUSH demonstration are available for explicit patient selection. `legacy/intake.json` is only for resuming retained Phase 1 answers. No new patient can select it through the flow API.

## Schema and validation

The executable schema is `backend/app/schemas/flow.py`. Every JSON file is validated at FastAPI startup by `flow_registry.load_flows`; invalid files, empty registries and duplicate flow IDs fail startup clearly. Tests exercise malformed JSON, missing translations, duplicate IDs/options, bad references, dependencies, cycles, incompatible operators, sections, namespaces and bounds.

A flow requires:
- `schema_version: 1`, stable `flow_id`, semantic `version`, `namespace`, `applicable_complaint`, and three-language `label`.
- `content_status: prototype_unvalidated`.
- Ordered sections with canonical section IDs and localized labels.
- Ordered questions with stable `question_id`, canonical `field`, type, required flag, unknown policy, localized text, options, constraints, dependencies and conditions.
- `traversal: ordered_applicable` and `completion: all_applicable_addressed`.

Supported types: boolean, single_choice, multiple_choice, short_text, number, duration, severity. Duration is a nonnegative amount and explicit unit; severity is an integer 0–10. Numeric bounds validate input shape, not clinical safety. Choice options may be exclusive (for example “none of these”).

Conditions are an AND list. Only `equals` on earlier boolean/single-choice questions and `contains` on earlier multiple-choice questions are allowed. Conditions inspect **active answered** facts only. Unknown, not-reported, skipped, unanswered and inactive parents cannot activate a branch.

Example:
```json
{
  "depends_on": ["past_medical_history.diabetes"],
  "when": [{"question_id": "past_medical_history.diabetes", "operator": "equals", "value": true}]
}
```

## Editing and versions

Increment the version whenever wording, translations, fields, options or branching change. A selected interview stores an immutable snapshot; replacing source configuration affects only future selections. Keep schema readers compatible with retained snapshots.

Corrections append answers. Inactive answers remain stored and are omitted from current history. If a branch becomes active again, its latest saved answers are restored with their original provenance and shown during forward traversal. The engine never infers a new answer.

Every applicable question must be addressed before completion. Required questions accept explicit unknown/not-reported when allowed; optional questions additionally accept skipped. Missing data and explicit “No” remain distinct.

The repeated general-history sections are part of each versioned flow document; change them consistently and increment every affected flow version. There is no second runtime flow source or generator.
