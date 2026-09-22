# clean512_schedctx_v2 controlled intervention D

## Decision

**B — D creates meaningful trade-offs; retain controlled checkpoint C and document the schedule limitation.**

Intervention D was the single authorized from-scratch schedule-context training run. It sharply improved `1-0-0`, `1-0-1`, and `0-0-1`, but did not improve `1-1-1` and severely regressed `0-1-0`. Broader validation CER nearly doubled versus C, while locked test CER and strict exact-line accuracy also worsened. D therefore does not replace C.

This supports schedule identity/context sensitivity under this protocol. It does **not** establish that historical failures were caused only by schedule imbalance; prior evidence also demonstrated geometry sensitivity.

## 1. Resolved experiment configuration

D was initialized from scratch, not from C. The model and policy were unchanged from controlled baseline C except for deterministic TRAIN schedule-identity exposure:

- Flor, input 64×512, 128 CTC timesteps
- batch 32, seed 41
- AdamW: LR 0.001, betas 0.5/0.99, weight decay 0.01, clipnorm 5.0
- unchanged dropout and `light_augmentation.json`, TRAIN only
- maximum 20 epochs; early stopping patience 5, minimum delta 0.002
- checkpoint selected by minimum validation greedy CER
- original `clean512_v2` validation and test sets, unmodified

The complete code/data/config hashes are in [resolved_config.json](resolved_config.json).

## 2. Rotation verification

Every epoch contained 437 unchanged non-schedule examples and one stored variant from each of 263 schedule contexts, totaling 700 examples. The rule was `patterns[(context_index + zero_based_epoch) mod 5]`. Counts rotated as 53/53/53/52/52; across every complete five-epoch cycle, every context saw each identity once. No variants were regenerated.

The independently verified resource contains 263 contexts, 1,315 variants, 437 unchanged references, zero rejection/clipping/overlap/outside-region changes, and 263/263 pixel-exact original identities.

## 3–6. Training history and selected checkpoint

|Epoch|Train loss|Validation loss|Validation greedy CER|Improved|Patience|
|---:|---:|---:|---:|:---:|---:|
|1|164.1468|110.8787|1.000000|yes|0|
|2|113.8291|106.3444|0.991046|yes|0|
|3|101.1723|85.7318|0.995667|no|1|
|4|86.7798|79.7648|0.943385|yes|0|
|5|75.9089|65.9329|0.866262|yes|0|
|6|64.2826|60.3909|0.836511|yes|0|
|7|54.4391|49.0045|0.719237|yes|0|
|8|45.7557|46.6503|0.648469|yes|0|
|9|38.1726|40.8563|0.586944|yes|0|
|10|31.6098|50.6480|0.570479|yes|0|
|11|26.0862|57.1701|0.547083|yes|0|
|12|21.8551|32.6515|0.356730|yes|0|
|13|17.8669|77.6973|0.463605|no|1|
|14|14.8419|36.6483|0.296072|yes|0|
|15|12.9475|29.6788|0.255633|yes|0|
|16|10.4005|31.5383|**0.253033**|**yes**|0|
|17|8.5137|78.4439|0.370306|no|1|
|18|8.2982|48.8793|0.309359|no|2|
|19|7.0491|74.6598|0.353553|no|3|
|20|5.9184|40.6882|0.263432|no|4|

Best epoch: **16**. Stop epoch: **20**. Early stopping: **false**. The fixed LR was 0.001 throughout. D checkpoint SHA-256: `c94f5f6f76e15a77077b4cef6d43e3c81c2f68d790380450124e37673b2b00a5`.

## 7–9. Validation decoder lock

|Decoder|CER|WER|Exact line|
|---|---:|---:|---:|
|Greedy|0.253033|0.490028|0.020|
|Beam50|**0.218660**|**0.454416**|0.020|

Beam50 was locked using validation CER only, with the lock written before test inference. It is **validation-preferred under renderer-conditioned validation**, not universally optimal. See [decoder_lock.json](decoder_lock.json).

## 10–12. Schedule results before test

These tables use beam50 for both C and D so the checkpoint comparison is decoder-matched.

|Split/model|1-1-1|1-0-1|1-0-0|0-1-0|0-0-1|Macro|
|---|---:|---:|---:|---:|---:|---:|
|TRAIN C|5/64 (0.078)|49/59 (0.831)|37/44 (0.841)|23/45 (0.511)|39/51 (0.765)|0.605|
|TRAIN D|5/64 (0.078)|57/59 (0.966)|43/44 (0.977)|0/45 (0.000)|50/51 (0.980)|0.600|
|VALIDATION C|3/6 (0.500)|3/4 (0.750)|7/9 (0.778)|8/11 (0.727)|5/5 (1.000)|0.751|
|VALIDATION D|3/6 (0.500)|4/4 (1.000)|9/9 (1.000)|1/11 (0.091)|4/5 (0.800)|0.678|

The intervention redistributed schedule performance rather than solving schedule recognition: `1-1-1` was unchanged, `0-1-0` collapsed, and macro accuracy declined on both TRAIN and validation.

## 13–14. Middle-symbol posterior diagnostics

|Split/pattern/model|Exact|Middle peak mean|Median|Non-argmax|Top-5 presence|First digit|Hyphen 1|Hyphen 2|Final digit|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|TRAIN 1-1-1 C|5/64|0.1829|0.1663|1.000|0.875|0.8620|0.9073|0.6356|0.9454|
|TRAIN 1-1-1 D|5/64|0.1927|0.1893|1.000|0.812|0.9950|0.6264|0.7985|0.9586|
|VAL 1-1-1 C|3/6|0.2281|0.1891|1.000|0.500|0.6848|0.9507|0.5177|0.8760|
|VAL 1-1-1 D|3/6|0.2321|0.2336|1.000|1.000|0.9976|0.7705|0.6455|0.9613|
|TRAIN 1-0-0 C|37/44|0.7948|0.9327|0.159|0.841|0.8919|0.9909|0.9066|0.8784|
|TRAIN 1-0-0 D|43/44|0.9256|0.9524|0.023|0.977|0.9939|0.9756|0.9637|0.9890|
|VAL 1-0-0 C|7/9|0.7513|0.9610|0.222|0.778|0.8143|0.9898|0.8983|0.8098|
|VAL 1-0-0 D|9/9|0.9246|0.9253|0.000|1.000|0.9970|0.9883|0.9887|0.9780|

D clearly strengthened `1-0-0` emissions. For `1-1-1`, middle-symbol probability changed only modestly, remained non-argmax in every sample, and exact accuracy did not move.

## 15. Overall validation C versus D

|Beam50 validation|C|D|Delta D−C|
|---|---:|---:|---:|
|CER|0.112940|0.218660|+0.105719|
|WER|0.249288|0.454416|+0.205128|
|Exact line|0.050|0.020|-0.030|
|Numeric-schedule CER|0.101824|0.213526|+0.111702|
|Punctuation/hyphen CER|0.101824|0.213526|+0.111702|
|Repeated-character CER|0.102681|0.236711|+0.134030|
|Medicine|0.740|0.330|-0.410|
|Dose|0.620|0.230|-0.390|
|Frequency|0.690|0.630|-0.060|
|Duration overall / present|0.730 / 0.550|0.620 / 0.367|-0.110 / -0.183|
|Forms overall / present|0.990 / 0.987|0.820 / 0.769|-0.170 / -0.218|
|Instructions overall / present|0.670 / 0.195|0.650 / 0.146|-0.020 / -0.049|

This met predeclared classification **T4: broader OCR performance degrades materially**.

## 16. Analysis freeze

[analysis_freeze.json](analysis_freeze.json) was written before any test inference. It froze epoch 16, the D checkpoint SHA, beam50, metric definitions, all pre-test comparisons, T4 classification, and prohibited further configuration changes. It records exactly one subsequently completed test evaluation.

## 17–19. Locked test results

The untouched original `clean512_v2` test set was evaluated exactly once with D epoch 16 and the validation-locked beam50 decoder.

|Metric|D locked test|
|---|---:|
|CER|0.053276|
|WER|0.093056|
|Strict exact line|0.315|
|Whitespace-normalized CER|0.032111|
|Whitespace-normalized WER|0.093056|
|Whitespace-normalized exact line|0.475|
|Medicine|0.910|
|Dose|0.935|
|Frequency|0.745|
|Duration overall / present|0.815 / 0.743|
|Forms overall / present|1.000 / 1.000|
|Instructions overall / present|0.925 / 0.797|
|Numeric-schedule CER|0.057893|
|Punctuation/hyphen CER|0.057893|
|Repeated-character CER|0.064825|

|Schedule|D exact test accuracy|
|---|---:|
|1-1-1|0/18 (0.000)|
|1-0-1|15/15 (1.000)|
|1-0-0|14/14 (1.000)|
|0-1-0|0/9 (0.000)|
|0-0-1|10/10 (1.000)|
|Macro|0.600|

## 20–21. Full locked-test C versus D and trade-offs

|Metric|C|D|Delta D−C|
|---|---:|---:|---:|
|Best validation greedy CER|0.119873|0.253033|+0.133160|
|Locked decoder|beam50|beam50|—|
|Test CER|0.034413|0.053276|+0.018862|
|Test WER|0.092361|0.093056|+0.000694|
|Strict exact line|0.375|0.315|-0.060|
|WS CER|0.033778|0.032111|-0.001666|
|WS exact line|0.395|0.475|+0.080|
|Medicine|0.995|0.910|-0.085|
|Dose|1.000|0.935|-0.065|
|Frequency|0.785|0.745|-0.040|
|Duration present|0.660|0.743|+0.083|
|Instructions present|0.500|0.797|+0.297|
|Numeric-schedule CER|0.051645|0.057893|+0.006247|
|Repeated-character CER|0.032524|0.064825|+0.032301|
|Schedule macro|0.596|0.600|+0.004|
|1-1-1|2/18 (0.111)|0/18 (0.000)|-0.111|
|1-0-1|12/15 (0.800)|15/15 (1.000)|+0.200|
|1-0-0|7/14 (0.500)|14/14 (1.000)|+0.500|
|0-1-0|6/9 (0.667)|0/9 (0.000)|-0.667|
|0-0-1|9/10 (0.900)|10/10 (1.000)|+0.100|

D improved whitespace-normalized exactness, duration/instruction extraction, and three schedule identities. Those gains are outweighed by the target `1-1-1` regression, total `0-1-0` failure, worse broad validation, worse raw CER/exactness, and medicine/dose/frequency regressions. The nearly unchanged macro schedule score conceals the severe identity redistribution.

## 22. Final recommendation

Retain checkpoint **C** as the OCR prototype checkpoint. Document its schedule limitation; do not adopt D and do not conduct another schedule-targeted run on this fixed test set.

## 23–24. Checks and Git status

Final verification is recorded in [CHECKS.md](CHECKS.md). No commit, staging, push, page OCR, or MediKiosk integration was performed.

## 25. Remaining OCR work

Stop schedule tuning against this synthetic test. The scientifically useful next step is a separately specified data/protocol reset followed by cropped-line real-handwriting evaluation with whole-writer separation and an untouched test set. Model changes should be selected using training/validation and a newly protected evaluation set. Only after unseen-writer line recognition is useful should page segmentation, batching/performance work, or MediKiosk integration begin.

Machine-readable evidence: [training_summary.json](training_summary.json), [pretest_comparison.json](pretest_comparison.json), [decoder_lock.json](decoder_lock.json), [analysis_freeze.json](analysis_freeze.json), and [locked_test.json](locked_test.json).
