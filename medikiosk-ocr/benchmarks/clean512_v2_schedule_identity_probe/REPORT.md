# Frozen TRAIN-only schedule identity probe

## Conclusion

The result supports **I1: schedule-identity/context sensitivity**, while retaining a smaller geometry contribution from the preceding probe. In the same surrounding lines and essentially the same schedule slots:

- Replacing six failing `1-1-1` rasters with `1-0-0` raised the middle-symbol assigned peak by **+0.675 mean** and made **6/6** locked schedules correct.
- Replacing six failing `1-0-0` rasters with `1-1-1` raised the middle-symbol peak only **+0.063 mean** and made **0/6** schedules correct. Four remained `1-1` or `-1`; exact `1-1-1` appeared in top5 for only 2/6.

Thus failure does not simply remain with source geometry: the substituted identity changes behavior strongly and directionally. Geometry still matters—+1px spacing corrected 5/8 prior `1-1-1` failures—but identity/context is now the stronger supported explanation for the pattern divergence. This does not identify the historical optimization cause.

Enough bounded diagnostic evidence now exists to **stop adding evaluation probes and design one controlled training intervention**. No intervention was launched.

## Protocol amendment and frozen selection

The prior geometry experiment contained only four selected `1-0-0` sources. Per the authorized amendment, those four were retained and the first two eligible failing frozen-TRAIN samples were added by ascending sample ID under identical rules: `train_00551` and `train_00658`. Selection did not use posterior strength, renderer, error severity, or outcome.

|Direction|Selected sources|
|---|---|
|`1-1-1 → 1-0-0`|train_00000, train_00007, train_00014, train_00018, train_00061, train_00084|
|`1-0-0 → 1-1-1`|train_00104, train_00159, train_00385, train_00443, train_00551, train_00658|

No selected source failed construction. Rejected expanded-pool candidates and reasons, if any before the two additions, are retained in `selection.json`. All 12 were frozen before model creation or inference.

## Counterfactual construction and pixel controls

The complete line was never rerendered for the counterpart. The five original schedule ink bands were isolated. Unchanged glyph rasters were copied exactly. Changed `1`/`0` glyphs were rendered alone using the same frozen font, size and baseline, then deterministically centered on the original ink-band center with round-half-up integer placement. Neighboring text never moved; spacing was not deliberately changed.

All originals reconstructed pixel-identically to frozen PNGs. Every counterpart remained 64×512, within the safe region, had zero overlap with non-schedule ink, and had zero changed pixels outside the old/new schedule-bbox union. Original and counterfactual full targets differ only in the five-character schedule. Exact placements and diff-mask statistics are in `selection.json` and `render_verification.json`.

## Per-pair results

|Sample|Direction|Original → counterpart schedule prediction|Middle peak original → counterpart|Target logP Δ|Exact schedule rank top5 original → counterpart|
|---|---|---|---:|---:|---|
|train_00000|111→100|`1-1` → `1-0-0`|.2566 → .8773|+.7116|2 → 1|
|train_00007|111→100|`1-1` → `1-0-0`|.1573 → .9567|+1.1554|2 → 1|
|train_00014|111→100|`1-1` → `1-0-0`|.1572 → .8811|+.9834|2 → 1|
|train_00018|111→100|`1-1` → `1-0-0`|.1606 → .9655|+.6108|2 → 1|
|train_00061|111→100|`1-1` → `1-0-0`|.1519 → .5619|+.8602|5 → 1|
|train_00084|111→100|`1-1` → `1-0-0`|.2641 → .9550|+.8052|2 → 1|
|train_00104|100→111|`0-1` → `1-1`|.0335 → .1212|+2.3096|absent → absent|
|train_00159|100→111|`0-1` → `1-1`|.0321 → .1619|+2.8117|absent → 4|
|train_00385|100→111|`0-1` → `0-1`|.0418 → .1065|+1.7298|absent → absent|
|train_00443|100→111|`0-1` → `1-1`|.0462 → .0988|+1.7247|absent → 5|
|train_00551|100→111|`1-0` → `1-1`|.1649 → .1240|+.0682|absent → absent|
|train_00658|100→111|`0-1` → `-1`|.0348 → .1175|+2.1198|absent → absent|

Raw logits/posteriors, five symbol alignments and local ±3-frame maxima, argmax status, frames/spans, Viterbi scores, top-five beams and full predictions are retained in `paired_samples.jsonl`, `posterior_comparison.json`, `beam_comparison.json`, and `raw/`.

## Directional aggregates

|Direction|N|Middle peak Δ mean/median/range|First peak Δ mean|Final peak Δ mean|Target logP Δ mean/median/range|Exact beam schedule original→CF|Top5 presence original→CF|
|---|---:|---|---:|---:|---|---|---|
|111→100|6|+.675 / +.707 / +.410…+.805|+.0078|+.0045|+.854 / +.833 / +.611…+1.155|0/6 → 6/6|6/6 → 6/6|
|100→111|6|+.063 / +.074 / −.041…+.130|+.0500|+.4896|+1.794 / +1.925 / +.068…+2.812|0/6 → 0/6|0/6 → 2/6|

The large final-digit increase in 100→111 reflects changing a final `0` to `1`; it does not rescue the weak ordered middle occurrence. Forward target probability improved in both directions, but beam correctness did not: absolute competing-sequence ranking matters, not merely positive Δ logP.

## Answers to the key questions

1. **Does 100 become easier in original 111 geometry?** Yes, for these six selected failures: 6/6 counterpart schedules were beam-correct.
2. **Does 111 in original 100 geometry show weak-middle behavior?** Yes. It remained incorrect 6/6; middle peaks stayed .099–.162 and were insufficient for an exact locked schedule.
3. **Does weakness follow numeral identity?** Strongly in this paired sample: middle `0` evidence rose far more than substituted middle `1` evidence.
4. **Does it remain tied to source geometry?** Not primarily. Swapping identity reversed recognition behavior in the 111-source direction. The earlier spacing response still shows geometry sensitivity within 111.
5. **Do beam rankings follow identity?** Yes directionally: every 100 counterpart ranked first, while only two 111 counterparts entered top5 and none ranked first.
6. **Which target has lower probability?** Paired Δ values favor each counterpart over its source because glyphs and diagnostic targets both change. The decisive distinction is that 111 still loses sequence ranking despite positive logP changes; absolute per-pair arrays are retained. This experiment cannot convert those directional changes into a universal schedule prior.

Overall classification: **identity/context sensitivity with a previously demonstrated geometry interaction**, not pure geometry and not an inconsistent/no-mechanism result.

## Recommended training correction — proposal only

Design one bounded, from-scratch controlled training comparison that changes only **schedule-token sampling balance**: keep the clean512_v2 renderer, architecture, width, augmentation, optimizer, seed, stopping and validation policy fixed; construct a versioned TRAIN corpus with equal counts of the five schedule patterns and balanced schedule positions/line contexts, including equal `1-1-1` and `1-0-0` counts. Do not apply geometry changes in the first comparison. Evaluate unchanged train/validation metrics with predeclared per-pattern schedule accuracy and middle-symbol posterior diagnostics; do not inspect TEST until configuration/selection is frozen.

This is justified because identity/context remains decisive at matched local positions, while mixing spacing and sampling changes would prevent attribution. The intervention is a proposal only—no training or dataset generation occurred.

## Limitations

Only 12 selected failing TRAIN lines were studied; results are sensitivity measurements, not accuracy estimates. Replacement uses isolated raster glyphs centered on source ink slots, so glyph width necessarily changes and exact kerning is not reproduced. Source geometry and identity cannot be made mathematically independent in raster text. Forced alignments are target-constrained; local maxima may borrow nearby evidence. The counterfactual label is synthetic, not part of the frozen corpus. No validation/test confirmation, statistical uncertainty estimate, beam tuning, or training was performed.

See [PROTOCOL.md](PROTOCOL.md), machine-readable artifacts, and [CHECKS.md](CHECKS.md).
