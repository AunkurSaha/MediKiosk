# clean512 schedule-context intervention compatibility blocker

## Outcome

Training was **not started**. The pre-training render verification triggered the protocol's mandatory stop condition.

The frozen TRAIN split contains the expected **263 schedule-bearing** and **437 non-schedule** lines. Under the unchanged strict raster substitution rules:

- Fully compatible schedule contexts: **179/263 (68.06%)**.
- Incompatible contexts: **84/263 (31.94%)**.
- Verified variants produced: **895** (`179 × 5`).
- Rejections: all 84 fail reliable five-symbol isolated ink-band segmentation; observed band counts range from two to four instead of five.

This is substantial. Dropping those contexts would produce epochs of **616**, not 700, and would systematically change which schedule contexts are trained. It would violate the experiment's sole-change claim and its exact prevalence/step controls. The criteria were therefore not relaxed and no checkpoint, optimizer, validation inference, decoder selection, analysis freeze, or TEST inference exists for intervention D.

## What was verified

The source counts were measured rather than hard-coded. Every one of the 179 accepted contexts supports exactly these five identities:

```text
1-1-1
1-0-1
1-0-0
0-1-0
0-0-1
```

For the original identity, the stored variant is pixel-identical to the source image. For substitutions, unchanged symbols use copied rasters and changed numerals use the frozen font/font size/baseline, centered deterministically on source ink slots. Across all 895 accepted variants:

- no clipping;
- no safe-area overflow;
- no overlap with non-schedule ink;
- zero changes outside the declared intervention region;
- canvas remains 64×512;
- non-schedule text and pixels remain unchanged.

The partial deterministic rotation is internally correct but unusable for the authorized controlled run:

- each partial epoch has 437 non-schedule + 179 schedule contexts = 616 examples;
- per-epoch pattern counts differ by at most one;
- across five epochs every pattern receives exactly 179 exposures.

The complete rejected list and reason per source are in `datasets/synthetic/clean512_schedctx_v1/pool.json`. No candidate was rejected based on model posterior, renderer, error severity, or predicted outcome. No model inference was used in construction.

## Why reliable segmentation failed

The validated diagnostic helper identifies schedule symbols through separated raster ink bands. In 84 otherwise valid frozen source renders, anti-aliased glyph ink and/or the font's tight horizontal placement makes two or more neighboring schedule glyph bands connected or not separable into exactly five components by that frozen rule. Treating guessed split locations as reliable would relax the explicit eligibility requirement and invalidate pixel-shape preservation controls.

This does not mean the source images are clipped or corrupt. It means the diagnostic raster-isolation method is not general enough to construct all 263 contexts under the authorized constraints.

## Derived resource status

`datasets/synthetic/clean512_schedctx_v1/` is a **partial, rejected pre-training build**, not an approved training dataset. It contains:

- `pool.json`: full compatibility/rejection inventory and precomputed partial rotation;
- `non_schedule.csv`: references to the unchanged 437 sources;
- `variants/`: 895 verified PNG variants for compatible contexts.

It must not be used for training as currently constructed. The original `clean512_v2` dataset, validation, TEST, historical checkpoint, and controlled checkpoint were not modified.

## Scientifically justified next step

No model-training experiment should run from this partial pool. A separately authorized **construction-method repair** would be needed first: derive each symbol's raster and slot directly from font layout/advance metadata rather than connected-component ink-band segmentation, then independently prove exact reconstruction of every original schedule token and unchanged non-schedule pixels for all 263 contexts. That is a data-construction validation task, not another OCR diagnostic and not permission to train.

Until that succeeds for all—or a predeclared acceptably small, demonstrably nonsystematic rejection count—the intended controlled comparison D is not identifiable.

## Requested final-report fields

Items 1–7 are captured in this report and `pool.json`. Items 8–21 (training history, checkpoint, validation/TEST metrics, C-vs-D results and interpretation) are **not applicable because training was stopped before launch**. There is no D checkpoint and no test-set reuse.

Checks and Git state: [CHECKS.md](CHECKS.md).
