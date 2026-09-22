# clean512 schedule-context pool construction repair

## Status: READY_FOR_CONTROLLED_TRAINING

The construction blocker is repaired. The new versioned pool covers **263/263 schedule contexts**, generates **1,315 verified schedule images**, retains **437 unchanged non-schedule references**, and has **zero rejections**. Training was not started.

## Exact construction method

The rejected v1 method treated separated connected ink bands as symbols. That failed for 84/263 sources because anti-aliased/tightly placed raster ink frequently formed only two to four separable bands. Those source images were valid; the component heuristic was not a reliable representation of text layout.

Version v2 uses the frozen rendering layout directly:

1. Find the exact five-character schedule indices in `target_text`.
2. Load the recorded font path and size after verifying the stored font hash.
3. Reconstruct the entire line using the recorded `(x,y)` origin and Pillow `la` anchor; require exact equality to the frozen PNG.
4. Compute the schedule anchor as `line_x + font.getlength(prefix)`.
5. Compute symbol anchor *i* as `line_x + font.getlength(prefix + original_schedule[:i])`.
6. Render each original symbol independently at its derived anchor/baseline. Its ink pixels must exactly equal the corresponding frozen source pixels.
7. Clear only the union of those verified original-token ink pixels. Render each replacement symbol independently at the same original-symbol anchor. Unchanged symbols therefore retain their exact layout position; no component coordinates, monospaced assumption, hard-coded offset, spacing addition, scaling, or OCR output is used.
8. Composite onto the stored source image. Prefix, suffix and every non-schedule pixel remain source pixels.

This slot policy preserves the schedule's overall anchor and the original five symbol origins. Replacement advance widths are measured and recorded but do not shift later slots or suffix text. Consequently different glyph widths are allowed only if the resulting ink remains within the safe area and does not overlap remaining non-schedule ink.

## Coverage and controls

|Control|Result|
|---|---:|
|Original schedule contexts|263|
|Non-schedule TRAIN references|437|
|Compatible contexts|263/263|
|Rejected contexts|0|
|Five-pattern variants|1,315|
|Original-identity pixel-exact matches|263/263|
|Outside-authorized-region changed pixels|0|
|Overlap pixels with non-schedule ink|0|
|Clipped variants|0|
|Safe-area overflow variants|0|
|Canvas|64×512 for all variants|

Each counterfactual target is constructed as the exact source prefix + replacement schedule + exact source suffix. Medication, dose, duration, instructions, form, renderer, font, font size, baseline, context ID and all non-schedule pixels are preserved. Every source/variant/font hash, schedule indices, advances, anchors, per-symbol bboxes, authorized region and diff count are stored in `pool.json`.

No font-specific exception was needed. The method records actual advances for every font/size and does not require digit `0` and `1` to have equal ink widths or assume monospacing. All observed replacements passed the same overlap and bounds gates.

## Rotation plan

The stored deterministic rule is:

```text
pattern = patterns[(context_index + zero_based_epoch) mod 5]
```

For every one of 20 precomputed epochs:

- 437 unchanged non-schedule references;
- 263 schedule contexts, exactly one variant per context;
- 700 total examples;
- schedule pattern counts differ by at most one (53/53/53/52/52 in rotating order).

Across every complete five-epoch cycle, every context sees every identity once and each pattern receives exactly **263** exposures. The independent validator checks every stored assignment rather than invoking the constructor.

## Independent verification

`scripts/verify_schedule_context_pool_v2.py` reads only stored artifacts and frozen sources. It independently verifies file/font/source hashes, 64×512 dimensions, target substitution, original-identity equality, outside-region equality, declared bounds, five patterns per context, all epoch/cycle invariants, and all 1,005 frozen `clean512_v2` snapshot hashes.

Result: **passed** for 263 contexts and 1,315 variants, with zero outside-region differences and zero stored overlaps.

## Artifacts

- `app/layout_schedule.py`: layout/advance construction.
- `scripts/build_schedule_context_pool_v2.py`: one-time versioned builder.
- `scripts/verify_schedule_context_pool_v2.py`: independent stored-pool validator.
- `tests/test_layout_schedule_pool.py`: layout, determinism, controls, coverage, rotation and immutability tests.
- `datasets/synthetic/clean512_schedctx_v2/`: `PROTOCOL.md`, `pool.json`, `non_schedule.csv`, `independent_verification.json`, and 1,315 PNG variants.
- `benchmarks/clean512_schedctx_v2_repair/`: this report and checks.

The rejected partial v1 pool remains untouched. Frozen `clean512_v2`, validation, TEST and checkpoints remain unchanged.

## Conclusion

**READY_FOR_CONTROLLED_TRAINING**

This means the derived resource satisfies construction and rotation prerequisites. It is not permission to train. The controlled run still requires the next explicit authorization. No validation/test inference or checkpoint creation occurred.

Checks and Git state: [CHECKS.md](CHECKS.md).
