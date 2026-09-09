# Phase 3A — verified summary

The earlier completion claim was incomplete. Verification found an unapplied/missing persistence path, ignored timeout/provider configuration, overly broad eligibility, unused strict output validation, missing durable failure results, transaction-isolation gaps and unsupported mock confidence. These have been corrected; no existing patient data was deleted.

The active implementation now uses one provider-neutral service and strict schemas, an exact-match EN/BN/HI mock, an explicit eligible-field policy and the additive normalization_results table. Results are tied to immutable answer IDs. Edits retain historical results; inactive branches disappear from active history; reactivation reuses the original result. Typed answers and AYUSH bypass normalization. Failures preserve raw answers and the deterministic interview. Doctor review displays raw wording and machine output separately, always unverified until a future explicit field-verification process.

Verified: **159 backend tests on SQLite and PostgreSQL; 33 frontend tests; 7 browser tests; 2 browser resume checks after a real backend/PostgreSQL restart.** Ruff, ESLint, Prettier, TypeScript/build, empty/Phase 1/Phase 2/app migrations and Alembic comparison pass. Existing row fingerprints and saved normalization/provenance survive upgrade/restart.

No live LLM, API keys, automatic flow switching, diagnosis, treatment, red-flag engine or later-phase integrations were added. Fixture coverage is intentionally small and clinically unvalidated; mock confidence is null.

Full architecture, reviewed defects, tests, file inventory and exact Phase 3B recommendation: [Phase 3A verification report](docs/phase3a-implementation-status.md).
