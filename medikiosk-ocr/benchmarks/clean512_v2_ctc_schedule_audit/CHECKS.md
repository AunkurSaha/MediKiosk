# Final checks

- Full OCR pytest: **45 passed**, one pre-existing Starlette/AnyIO deprecation warning. Command: `rtk proxy .venv\Scripts\python.exe -m pytest -q --basetemp tmp/ctc_numeric_all_20260918b -p no:cacheprovider`.
- Scoped Ruff: passed on app/ctc_alignment_audit.py, scripts/audit_ctc_schedules.py, scripts/report_ctc_schedules.py, tests/test_ctc_alignment_audit.py.
- Scoped Ruff formatting check: all four files formatted.
- Compileall: passed for app, scripts, tests.
- Full existing app/scripts/tests Ruff: **19 pre-existing findings**, unchanged; full formatting check: **11 pre-existing files** would be reformatted, unchanged. No unrelated fixes.
- New tests cover simple paths, adjacent repeats and blank separation, five-symbol schedules and final zero, exact forward probability versus exhaustive paths, immutable normalization, impossible alignment rejection, existing greedy equivalence, token digit deletion, raw inference weight preservation, exact frozen vocabulary IDs and checkpoint/all1,005 dataset hashes.
- Production frozen-model inference additionally asserts byte-identical in-memory weights before/after all800 lines, exact checkpoint/sidecar/dataset hashes before/after, raw128×49 outputs, unchanged production greedy output, and top1 equivalence between beam50 top1/top5 calls.
- No training, test inference, frozen artifact changes, integration, commit or push.

## Files created by this audit

Source/tests (no pre-existing application file modified):

- app/ctc_alignment_audit.py
- scripts/audit_ctc_schedules.py
- scripts/report_ctc_schedules.py
- tests/test_ctc_alignment_audit.py

New versioned benchmark artifacts:

- REPORT.md, FINDINGS.md, CHECKS.md
- audit_config.json, analysis_freeze.json, immutability.json
- sample_index.json, forced_alignments.jsonl, posterior_traces.jsonl
- posterior_summary.json, token_details.json, line_metrics.json
- schedule_error_matrix.json, duration_error_matrix.json
- character_statistics.json, decoder_path_comparison.json
- local_emission_analysis.json, repeated_symbol_analysis.json
- geometry_correlations.json, augmentation_audit.json, test_confirmation.json
- raw/: 800 per-line NPZ files containing original logits and full softmax posteriors (TRAIN/VALIDATION only).

Pytest/compileall also create local temporary/cache files; these are not benchmark inputs or frozen artifacts.

## Git status

Repository OCR directory is untracked (`?? ./` when Git is invoked here). No commit/staging/push occurred.

Pre-existing outside-scope tracked modifications remain untouched:

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
