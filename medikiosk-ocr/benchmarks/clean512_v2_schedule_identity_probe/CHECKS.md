# Checks

- Full pytest: **54 passed**, with one pre-existing Starlette/AnyIO deprecation warning.
- Scoped Ruff and formatting: passed for all three new code/test files.
- Compileall: passed for app, scripts and tests.
- Checkpoint SHA-256 remained `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.
- All 1,005 clean-corpus snapshot entries and in-memory model weights were unchanged before/after.
- No validation/test inference, training, tuning, corpus modification, integration, commit, or push.

## Files created

- `app/schedule_identity.py`
- `scripts/schedule_identity_probe.py`
- `tests/test_schedule_identity.py`
- `benchmarks/clean512_v2_schedule_identity_probe/`: protocol, selection, render verification, paired results, posterior/beam comparisons, summary, immutability, report/checks, 24 PNGs and 24 raw NPZ arrays.

No prior benchmark artifact was overwritten.

## Git status

No commit, staging or push. OCR remains untracked (`?? ./`). Outside-scope tracked changes remain untouched:

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
