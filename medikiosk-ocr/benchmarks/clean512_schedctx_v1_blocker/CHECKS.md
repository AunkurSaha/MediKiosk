# Checks

- Training, validation inference, TEST inference, decoder selection and checkpoint creation: **not run**.
- Frozen reference checkpoint expected SHA: `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.
- Relevant derived-pool verifier checks exact counts, five variants per compatible context, hashes for all 895 PNGs, zero stored control violations, epoch size, per-epoch balance and five-epoch equality.
- Final pytest/Ruff/format/compile results are recorded after execution below.
- No commit or push.

## Files created

- `scripts/build_schedule_context_pool.py`
- `tests/test_schedule_context_pool.py`
- `datasets/synthetic/clean512_schedctx_v1/` partial rejected build
- this versioned blocker report/check file

Supporting substitution code was generalized from the prior two-pattern diagnostic to the five predeclared schedule identities in `app/schedule_identity.py`; its existing rejection test was updated accordingly. No frozen artifact was changed.

## Final checks

- Full pytest: **56 passed**, one pre-existing Starlette/AnyIO deprecation warning.
- Scoped Ruff: passed.
- Scoped Ruff format check: four files formatted.
- Compileall: passed for app, scripts and tests.
- Derived verifier: passed; 179 compatible, 84 rejected, 895 hash-verified variants.
- Controlled checkpoint SHA-256 reverified exactly.

Git status remains:

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
