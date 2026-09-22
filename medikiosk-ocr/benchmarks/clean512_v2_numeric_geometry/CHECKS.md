# Checks

- Full pytest: **50 passed**, one pre-existing Starlette/AnyIO deprecation warning.
- Scoped Ruff and Ruff formatting: passed for `app/numeric_geometry.py`, `scripts/numeric_geometry_probe.py`, and `tests/test_numeric_geometry.py`.
- Compileall: passed for app, scripts, and tests.
- Production inference verified frozen checkpoint/corpus before and after and byte-identical in-memory weights.
- Tests verify exact original reconstruction, deterministic selection/intervention, unchanged schedule glyph raster bands, untouched outside pixels and surrounding glyphs, 64×512 canvas, unchanged target, safe-region/clipping/overlap controls, and frozen model/corpus state.
- No training, validation/test inference, intervention sweep, frozen-corpus mutation, integration, commit, or push.

## Files created

- `app/numeric_geometry.py`
- `scripts/numeric_geometry_probe.py`
- `tests/test_numeric_geometry.py`
- `benchmarks/clean512_v2_numeric_geometry/`: `PROTOCOL.md`, `selection.json`, `render_verification.json`, `paired_samples.jsonl`, `posterior_deltas.json`, `beam_comparison.json`, `summary.json`, `immutability.json`, `frame_examples.json`, `REPORT.md`, `CHECKS.md`, 40 diagnostic PNGs, and 40 raw NPZ arrays.

No existing source or benchmark file was modified.

## Git status

No commit, staging, or push. The OCR directory remains untracked (`?? ./`). Existing outside-scope tracked changes remain untouched:

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
