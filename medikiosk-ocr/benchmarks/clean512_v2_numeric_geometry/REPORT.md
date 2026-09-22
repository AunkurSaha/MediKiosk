# Frozen TRAIN-only numeric local-geometry counterfactual

## Result

The experiment supports **heterogeneous schedule-spacing sensitivity**. The fixed +1-pixel inter-symbol intervention increased the target-constrained middle-digit peak in all eight selected failing `1-1-1` samples and corrected five locked beam50 schedule tokens. It did essentially nothing useful for the four selected `1-0-0` failures: no decoder correction and all four target forward probabilities decreased.

The separate duration numeral-width probe supports **D2**: this single 110% horizontal-width intervention does not account for the selected duration failures. All eight assigned numeral peaks decreased slightly, no locked token became correct, and space remained dominant. These two interventions are not combined into a common causal estimate.

This is selected-failure sensitivity evidence for a frozen checkpoint. It does **not** show that training failed because schedule symbols were close, or that duration numerals were too narrow.

## Frozen controls

- Checkpoint before/after SHA-256: `c7dda1f89025f2053429fc2a16fb72a5ec569a1ecf30e3e8517fe69af182395b`.
- All 1,005 frozen `clean512_v2` snapshot entries matched before and after.
- In-memory model-weight byte hash was identical before/after inference.
- Exactly 40 images were inferred: 20 originals and their 20 counterfactuals.
- TRAIN only. No validation or test selection/inference.
- Input remained 64×512; unchanged preprocessing, greedy decoder, and ordinary beam width 50.
- All reconstructed originals were pixel-identical to frozen PNGs.
- Every pair had zero clipping, safe-area overflow, neighboring-ink overlap, and unintended changed pixels outside the intervention region.
- Targets, fonts, font sizes, canvas size, vertical position, and non-intervention pixels were unchanged.

## Frozen deterministic selection

|Pattern|Selected ascending sample IDs|
|---|---|
|`1-1-1`|train_00000, train_00007, train_00014, train_00018, train_00061, train_00084, train_00085, train_00095|
|`1-0-0`|train_00104, train_00159, train_00385, train_00443|
|`for 5 days`|train_00010, train_00028, train_00039, train_00044|
|`for 7 days`|train_00009, train_00042, train_00050, train_00051|

Rejected before inference:

- `train_00006` (`1-0-0`): raster token segmentation produced four separated ink bands rather than the required five; rejected as ambiguous.
- `train_00007` (`for 5 days`): already selected for `1-1-1`; rejected to retain 20 unique source lines.

No category substitution was needed. Selection, rejections, protocol, endpoint definitions, tolerances, and source hashes were saved before inference in `selection.json` and `PROTOCOL.md`.

## Exact interventions

Schedule glyph raster bands were copied unchanged. Symbols 1–5 were translated by 0, 1, 2, 3, and 4 pixels, producing exactly +1 pixel at each consecutive inter-symbol gap. The schedule remained left-anchored; later text was not shifted. Modified schedule bboxes were exactly four pixels wider.

For durations, only the tight numeral ink bitmap was resized horizontally with OpenCV `INTER_CUBIC`, with unchanged height. Integer widths realized scales from 1.0833 to 1.10 and a +0.5-pixel center shift. Surrounding `for`, spaces, `days`, and all other line pixels remained fixed.

Changed-pixel counts were 77–415 for schedules and 63–123 for numerals. Full bboxes and coordinate changes are in `selection.json` and `render_verification.json`.

## Paired results

Primary peak is the target-constrained middle digit for schedules and numeral for durations. Δ is counterfactual minus original.

|Sample|Token|Original beam token/line|Counterfactual beam token/line|Peak original→CF (Δ)|Target logP Δ|Token corrected|Exact token rank original→CF|
|---|---|---|---|---|---|---|---|
|train_00000|1-1-1|`1-1`|`1-1-1`|.2566→.3632 (+.1066)|+.2694|yes|2→1|
|train_00007|1-1-1|`1-1`|`1-1-1`|+.0661|+.4567|yes|2→1|
|train_00014|1-1-1|`1-1`|`1-1-1`|+.0795|+.2177|yes|2→1|
|train_00018|1-1-1|`1-1`|`1-1-1`|+.0823|+.0669|yes|2→1|
|train_00061|1-1-1|`1-1`|`1-1`|+.0641|−.1366|no|5→3|
|train_00084|1-1-1|`1-1`|`1-1-1`|+.0674|+.1666|yes|2→1|
|train_00085|1-1-1|`1-1`|`1-1`|+.0086|−.5900|no|4→4|
|train_00095|1-1-1|`1-1`|`1-1`|+.0007|+.0067|no|absent→absent|
|train_00104|1-0-0|`0-1`|`0-1`|−.00009|−.0370|no|absent→absent|
|train_00159|1-0-0|`0-1`|`0-1`|+.00017|−.0029|no|absent→absent|
|train_00385|1-0-0|`0-1`|`0-1`|+.00017|−.0200|no|absent→absent|
|train_00443|1-0-0|`0-1`|`0-1`|+.00007|−.0163|no|absent→absent|
|train_00010|for 5 days|`for days`|`for days`|−.00371|−.0519|no|absent→absent|
|train_00028|for 5 days|`for days`|`for days`|−.00031|+.0242|no|absent→4|
|train_00039|for 5 days|`for days`|`for days`|−.00026|+.0055|no|absent→absent|
|train_00044|for 5 days|`for days`|`for days`|−.00013|−.0080|no|3→3|
|train_00009|for 7 days|`for days`|`for days`|−.00015|+.0192|no|4→4|
|train_00042|for 7 days|`for days`|`for days`|−.00003|−.0051|no|2→2|
|train_00050|for 7 days|`for days`|`for days`|−.00001|−.0120|no|absent→absent|
|train_00051|for 7 days|`for days`|`for days`|−.00004|−.0016|no|5→5|

Every original remained a locked token failure, as required. Full lines, greedy outputs, five candidates and scores, exact target ranks, per-symbol assignments, raw argmax paths, forced paths, logits, and posteriors are machine-readable in `paired_samples.jsonl`, `beam_comparison.json`, `frame_examples.json`, and `raw/`.

## Aggregate endpoints

|Pattern|N|Primary Δ mean / median / min / max|Improved / worsened / unchanged|Target logP Δ mean|logP improved / worsened|Incorrect→correct|
|---|---:|---|---|---:|---|---:|
|1-1-1|8|+.05942 / +.06676 / +.00067 / +.10660|8 / 0 / 0|+.05716|6 / 2|5|
|1-0-0|4|+.000081 / +.000121 / −.000090 / +.000173|3 / 1 / 0|−.01903|0 / 4|0|
|for 5 days|4|−.001105 / −.000287 / −.003711 / −.000134|0 / 4 / 0|−.00753|2 / 2|0|
|for 7 days|4|−.0000569 / −.0000319 / −.000150 / −.0000135|0 / 4 / 0|+.000122|1 / 3|0|

“Improved/worsened” uses the predeclared ±1e−8 primary and ±1e−6 logP numerical tolerances. These counts are not uncertainty estimates. Correct→incorrect is zero, but that follows from selected failures rather than a hard-coded assumption.

## Posterior and decoder interpretation

For `1-1-1`, the middle-digit assigned peak rose consistently and five top candidates switched from truncated `1-1` to full `1-1-1`. Assigned middle digits nevertheless remained non-argmax in these pairs: sequence ranking can improve before the target character owns its forced frame. Full-target logP was heterogeneous—two lines worsened—so “spacing always improves the whole target” is unsupported.

For `1-0-0`, changes were numerically tiny and no returned top-five exact token appeared. This specific intervention does not explain those failures.

For duration failures, primary peaks decreased slightly in all eight. Space probability increased slightly in all eight and remained the principal competition in the selected deletion cases; no token corrected. The numeral glyph width probe therefore provides no evidence that 110% widening restores the missing evidence.

## Predeclared frame-level extremes

- Schedule highest deltas: train_00000, train_00018, train_00014.
- Schedule lowest deltas: train_00104, train_00443, train_00159.
- Duration highest (least negative): train_00050, train_00042.
- Duration lowest: train_00010, train_00028.

Selection used only the predeclared primary delta and deterministic sample-ID tie-breaking. `frame_examples.json` contains both full frame-level versions, argmax paths, forced paths, and beam candidates—no visual cherry-picking.

## Conclusions and limitations

**Schedule finding:** S1 is supported for the selected failing `1-1-1` lines: the frozen checkpoint is sensitive to this controlled +1-pixel schedule-spacing perturbation. S2 applies to selected `1-0-0`: it changes little and does not restore decoding. Sensitivity is pattern-dependent, not one common schedule mechanism.

**Duration finding:** D2 is supported. This specific numeral-width perturbation does not account for the selected duration regression.

The sample is deliberately small, selected exclusively from failures, and not an accuracy estimate. Renderer/phrase distributions are not balanced. Pixel counterfactuals are raster operations, not fresh font-layout observations. Forced peaks are target-constrained and uncalibrated. Local ±3-frame maxima can borrow neighboring occurrence evidence. Levenshtein token projection can be ambiguous around repeated symbols and boundary spaces. No validation/test confirmation was performed.

## Smallest justified next experiment — proposal only

Freeze a small **TRAIN-only, evaluation-only schedule-template substitution probe** before inference: preserve 12 of these exact source images and raster geometry, and replace only the five schedule glyph bands using matched-width counterfactual schedules (`1-1-1`↔`1-0-0`) where the bitmap fits without shifting non-schedule pixels. This would test whether the divergent response follows glyph identity/context rather than the mechanical displacement itself. One predetermined counterpart per source, no magnitude sweep, no validation/test, and no training. Do not launch it without separate authorization.

Checks and Git state are in [CHECKS.md](CHECKS.md). Protocol: [PROTOCOL.md](PROTOCOL.md).
