# Checks

- Exactly one from-scratch D training run completed. No additional training was launched.
- Validation greedy and beam50 were evaluated before the decoder lock; test was then evaluated exactly once with locked beam50. No alternate test checkpoint/decoder inference was run.
- Full pytest initially encountered six setup errors because pytest's user-profile temporary directory was inaccessible. Re-running the identical suite with a workspace-local `--basetemp` passed: **62 passed**, with the pre-existing Starlette/AnyIO deprecation warning and one pytest-cache permission warning.
- Full Ruff over `app scripts tests` reports **19 pre-existing findings** in unrelated older files (18 stale `noqa`/import-order findings and one broad-exception finding). These were not modified.
- Scoped Ruff for all v2 construction/intervention code and tests: **passed**.
- Scoped Ruff format check: **9 files already formatted**.
- Compileall for `app`, `scripts`, and `tests`: **passed**.
- Independent v2 verifier: **passed** — 263 contexts, 1,315 variants, 263 original identities exact, zero outside-region differences, zero stored overlaps, 20 verified rotation epochs, and 1,005 clean snapshot files.
- All **1,005** frozen `clean512_v2` snapshot hashes match. This includes the original validation and test data; the test manifest remains `c54f887370daf0c301d556a67efc886e3999c1c481896f94df941c27f80a8b11`.
- Derived `pool.json` remains `a7ee1fd1e83b400328c57472f3d2d60a13d38e5e14cc21b9dc814cdbed00b805`; its independent-verification record remains `376da91da3ede66da3dd81e1fe0877743c7fb4a7756815e4dab355ac3484aa08`.
- Checkpoint C remains `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.
- Checkpoint D is `c94f5f6f76e15a77077b4cef6d43e3c81c2f68d790380450124e37673b2b00a5`.
- No commit, staging, push, page OCR, or MediKiosk integration.

## Git status

The OCR tree remains untracked as before (`?? ./`). Existing outside-scope tracked changes remain untouched:

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
