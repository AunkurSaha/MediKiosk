# RAG-driven interview implementation status

Date: 2026-09-13

## Implemented

- Chief complaint acquisition initiates the interview and seeds multi-domain clinical context.
- Every turn executes the dynamic QuestionPlanner: extracts multi-domain entities from free-text answers, updates covered/missing domain tracking, and checks deterministic red flags.
- Retrieval queries incorporate chief complaint, confirmed clinical facts, recent patient statements, and missing high-priority domains.
- Generates multiple (~3-5) candidate questions across missing clinical domains grounded in pre-indexed knowledge base chunks.
- Deterministic explainable candidate scoring balances clinical relevance (+2 to +5), information gain (+1.5 to +2.5), missing required domain priority (+3.0), evidence strength, and context specificity against domain cooldown penalties (-4.0/consecutive turn) and duplicate penalties (-100.0).
- Live generative question synthesis via NVIDIA NIM (`meta/llama-3.2-11b-vision-instruct`) powered by semantic vector embeddings (`nvidia/nemotron-3-embed-1b`) over the clinical knowledge base.
- Context-aware validation in `rag_wording_validator`: allows follow-up questions to naturally reference symptoms already established by the patient without false cross-contamination rejections.
- Strict anti-hallucination prompt constraints ensuring questions reference only explicitly reported facts and retrieved guideline evidence.
- Semantic duplicate detection prevents repeating concepts, fields, or clinical synonyms (e.g. walking exertion, left arm radiation, timing onset).
- Branch continuation priority preserves clinical flow when child questions are activated by preceding answers.
- Preserves flow canonical question ID, field, input type, constraints, and dependencies, with fail-safe fallback to deterministic sequential flow on retrieval failure or rejection.
- Bengali/Hindi localization and TTS integration remain fully functional via the translation provider boundary.
- Verified with live NVIDIA API end-to-end evaluation, 30 wording validator tests, 10 dedicated conversational variety tests, and full regression test suite.

## Deliberately unchanged

- Authentication, consent, RBAC, session ownership, and audit logging.
- Deterministic red-flag screening authority and emergency alert evaluation.
- Structured answer validation, persistence, normalization, and clinician verification boundaries.
- Doctor review, editing, and FHIR export architecture.
- Knowledge ingestion remains pre-indexed and offline; no indexing occurs during patient turns.

## Clinical Scope & Safety Notice

- The clinical rules and question templates are prototype demonstration logic for the SIH prototype.
- Real-world deployment requires formal clinician review and ontology alignment before patient-facing use.
