# Interpretation of the frozen numeric CTC audit

Primary scope is TRAIN + VALIDATION only. No test confirmation was run. These findings describe this checkpoint's emissions; they do not establish why its training trajectory regressed relative to historical weights.

## Main outcome

The evidence supports **A (weak required ordered emissions) and C (beam50 ranking)**, with **D supported as competing/merged emission structure, not a demonstrated adjacent-repeat blank defect**. B describes the ordinary argmax-and-collapse behavior, not a decoder bug. Geometry and augmentation have measurable associations/effects, but do not establish E/F as causes. **G applies to any claim of a single explanation for the entire regression.**

There is no measured shortage of total CTC timesteps: the 643-line diagnostic cohort needs at most 67 steps, versus 128 available (minimum ratio 1.9104). No cohort alignment fails or crosses the declared 1.5 margin-warning threshold. This does not prove adequate local spatial resolution, but does not justify automatic downsampling changes.

## Schedules: middle-symbol weakness and ranking both matter

|Split|Schedule N|Beam50 exact projected token|Greedy exact projected token|1-1-1 beam50|
|---|---|---|---|---|
|Train|263|153 (58.17%)|124 (47.15%)|5/64|
|Validation|35|26 (74.29%)|22 (62.86%)|3/6|

Projection uses the unchanged whole-line Levenshtein alignment, without stripping token-boundary insertions. Exact token metrics can differ from substring field scoring; duplicate-symbol deletion attribution can be ambiguous.

For incorrect TRAIN schedules, mean assigned first/middle/final digit peaks are **.6858/.1387/.7785**, versus **.9884/.7885/.9945** for correct schedules. Middle-symbol competition is substantially stronger than a universal final-digit disappearance. Incorrect validation schedules show .6201/.4049/.7317 (only N=9).

For `1-1-1` specifically, combining train/validation: incorrect N=62 has first/middle/final peaks **.8285/.1761/.9321**; correct N=8 has **.9891/.2697/.9964**. Even correctly decoded examples can have a sub-argmax middle digit: sequence probability, not a per-frame .5 threshold, determines beam ranking.

In `train_00000`, the first digit occupies frames34–35, the middle digit is forced to frame39 (p(1)=.2566, argmax is hyphen), and the final digit occupies41–43 (peak .9899). Argmax emits a single continuous hyphen run at36–40, so its valid greedy collapse is `1-1`, not `1-1-1`. The two hyphens have evidence, but the middle digit does not interrupt that run in argmax. Adding a requirement for blanks between every digit/hyphen would be mathematically incorrect: those target symbols differ.

The ±3-frame window makes incorrect TRAIN middle-digit mean peak rise to .6228. This is **not evidence for an independent correct middle-digit occurrence**: the window may borrow a neighboring first/final digit peak. Target-constrained path peaks and unconstrained local maxima are both retained to expose this distinction.

Beam ranking matters too. Among 59 incorrect TRAIN `1-1-1` tokens, **51 have the full schedule somewhere in returned top5**, and **31 have the exact full target line in top5**. For the three incorrect validation cases, neither is present in top5. This means absence from the returned five candidates, not from every explored beam state.

For `train_00000`, beam rank1 is `PCM 625 ml 1-1 for 5 days after fod` (logP −1.9677); rank2 restores `1-1-1` (−2.1600), and rank4 is the exact target (−2.6156). Exact forward target logP is −2.6114. This is a measured ranking preference under model probabilities; it does not justify changing beam width, lexicon correction, or claiming beam50 wrongly removed overwhelmingly strong ordered evidence.

`1-0-0` also is not simply final-zero loss: six TRAIN transitions are `0-1`, with forced middle-zero peaks approximately .032–.046 and final-zero peaks .127–.195. One becomes `1-0` even though its forced final-zero peak is .996, demonstrating that identical-zero edit attribution and a strong single frame are insufficient to identify which semantic occurrence was lost. Inspect its full path, not just the edit label.

## Durations: deletions and substitutions are different

TRAIN durations: 316/493 exact projected tokens; validation: 33/60. `for 3 days` has **zero** examples; its absence is a coverage limitation, not a perfect score.

Key TRAIN transitions:

- `for 5 days → for days`: 52.
- `for 7 days → for days`: 61.
- `x 7d → x 3d`: 60 (plus 2 with a boundary-space insertion).
- Correct `x 3d`: 98/99; correct `x 5d`: 99/99; correct `x 7d`: 23/85.

Validation has five `for 5 days → for days`, three `for 7 days → for days`, twelve `x 7d → x 3d`, and five `x 5d → x 3d`. An additional `for 7 days` error projects to `fofor days` and must not be silently grouped as an exact plain deletion transition.

Correct/incorrect TRAIN duration-numeral mean assigned peaks are **.8441/.1338** (medians .8868/.0461). Among incorrect tokens, 62.15% of numeral peaks are below .1; 98.31% of local-window numeral maxima are not argmax. Validation correct/incorrect means are **.8123/.2309**; incorrect-token weak rate29.63%, local nonargmax96.30%. Some duration-token errors affect words rather than the digit, so these groups are not identical to numeral-deletion cohorts.

`train_00007`, `for 5 days → for days`: assigned numeral frame82 has p(5)=**.011881** versus p(space)=**.982216**. This directly supports weak numeral evidence competing with space, not a decoder removing a strongly emitted5. Word/space probability traces are retained for every token. `x 7d → x 3d` is separately a class-substitution phenomenon.

## Numeric recognition is context-dependent

|Character/context|Occurrences|Mean assigned peak|Median|Mean frame span|
|---|---|---|---|---|
|0, dose|688|.9385|.9976|2.2253|
|0, schedule|393|.8036|.9525|1.9288|
|1, dose|109|.9741|.9948|1.9266|
|1, schedule|501|.7396|.9794|1.9042|
|5, dose|505|.9908|.9978|2.1327|
|5, duration|224|.6799|.9089|1.6339|
|7, duration|219|.4120|.3486|1.2694|
|a|1500|.9857|.9991|3.1353|
|e|1341|.8777|.9946|2.0298|

These counts are across all800 TRAIN/VALIDATION lines, not just the diagnostic cohort. They favor a schedule/duration-context problem over uniformly poor digit recognition. Comparisons are observational and target-constrained; character/span differences are not an architectural diagnosis. Digit8/9 are not in the frozen vocabulary and cannot be evaluated.

## Geometry and augmentation

Incorrect versus correct TRAIN schedule mean x-starts are239.64 versus244.22: **no general right-edge failure pattern is shown there**. Validation means307.33 versus258.35 differ, but renderer, font size, phrase and length are confounded, and only nine validation failures are available. Incorrect TRAIN lines are shorter on average (33.19 versus39.56 characters). Renderer/font/fitting groups are retained, not treated as randomized interventions.

All263 schedule-bearing TRAIN images received one declared controlled in-memory augmentation example. Approximate paired schedule-mask width ratios: mean1.00287, range **.95349–1.04545**. Horizontal centroid shifts: mean−.13982px, range **−2.9360 to1.1812px**. Zero paired masks have edge ink; this does not prove complete glyph preservation. Laplacian-variance ratios have median .5067, p10 .1550 and minimum .0498: interpolation/blur measurably changes this sharpness proxy, which is also affected by scaling and contrast.

The implementation's expanded-canvas rotation/resizing creates vertical compression; its configured perspective is effectively identity at this canvas size. Explicit horizontal scaling/shift is not enabled. These current-implementation controlled examples are **not proven historical epoch replay**. No checkpoint inference on augmented images was used to assert an OCR effect, and no causal attribution to augmentation is established.

## Smallest justified next experiment — proposal only

Before any new training, separately authorize a **frozen-checkpoint paired numeric-spacing inference diagnostic**: preselect20 TRAIN phrases containing failing `1-1-1`/`1-0-0` and duration numerals; preserve each phrase, renderer, font, canvas and all nonnumeric glyph positions, and compare original spacing with one declared small numeric-token spacing increase. Use a new diagnostic-only artifact directory, never alter the clean corpus, and select no weights/decoder. Approximately40 lines, bounded to a few minutes on this CPU including startup. Check bounds explicitly and compare ordered middle-digit/duration evidence, hyphen-run interruption, target sequence probability and locked decoder output. This isolates a local geometry sensitivity, not the historical training cause. Freeze the protocol first and do not use TEST.

If this does not improve ordered evidence, investigate context/class competition with similarly bounded evaluation-only counterfactuals before proposing optimization or augmentation training ablations. No epochs, model/downsampling changes, beam tuning, renderer-balanced retraining, data collection or integration are justified automatically by this audit.

Full machine-readable results and examples: REPORT.md and its linked artifact filenames. Checks and Git status: CHECKS.md.
