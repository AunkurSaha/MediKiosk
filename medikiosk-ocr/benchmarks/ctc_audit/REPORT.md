# CTC alignment, renderer and geometry audit

Evaluation only. No additional training, page OCR, volunteer collection, checkpoint selection, or MediKiosk integration. The checkpoint is the existing best-validation model. Buckets are overlapping descriptive categories, not causal diagnoses.

Checkpoint SHA-256: `386988783287d4b82ea954a6d423aec01d931c75110f77f95d1aac790f8420ef`.

## 1. Sequence statistics and warnings

All original images and baseline model inputs are width 512. Actual output shape is 1×128×49 (128 CTC steps). Threshold for a diagnostic low-margin warning is ratio <1.5; this is a declared heuristic, not a clinical or mathematical safety threshold.

| Split | N | Required min/median/max | Ratio min/median/max | Clipped renders |
| --- | --- | --- | --- | --- |
| train | 700 | 14.0/36.0/67.0 | 1.91/3.56/9.14 | 102 |
| validation | 100 | 17.0/36.0/65.0 | 1.97/3.56/7.53 | 30 |
| test | 200 | 16.0/37.0/64.0 | 2.00/3.46/8.00 | 7 |

Insufficient or low-margin samples: **0**. No sample minimally satisfies the global requirement. Training now asserts feasibility instead of relying on the upstream loss's ignore-longer behavior. Full per-sample records and bucket distributions are in `alignment_samples.json` and `alignment_summary.json`.

Pixel verification reproduced all 1,000 saved images exactly. Of 139 projected bounds overflows, **136** actually lose non-white glyph pixels outside the canvas (99 train, 30 validation, 7 test). Three bounds warnings alone did not lose glyph ink. See `render_bounds_verification.json`.

| Smallest margins (first 10) | Target chars | Adjacent repeats | Required | Output | Ratio |
| --- | --- | --- | --- | --- | --- |
| train_00620 | 59 | 8 | 67 | 128 | 1.910 |
| validation_00065 | 59 | 6 | 65 | 128 | 1.969 |
| train_00127 | 56 | 8 | 64 | 128 | 2.000 |
| train_00294 | 58 | 6 | 64 | 128 | 2.000 |
| train_00690 | 55 | 9 | 64 | 128 | 2.000 |
| test_00026 | 57 | 7 | 64 | 128 | 2.000 |
| train_00061 | 55 | 8 | 63 | 128 | 2.032 |
| train_00551 | 56 | 7 | 63 | 128 | 2.032 |
| validation_00005 | 55 | 8 | 63 | 128 | 2.032 |
| test_00144 | 54 | 9 | 63 | 128 | 2.032 |

## 2. Error buckets and length distributions

Short ≤25 characters; medium 26–39; long ≥40. `repeated_character` includes repeated spaces. `spacing` means a target contains whitespace, not that spacing caused an error. All prescription lines naturally fall in the medication/spacing buckets. `1-1-1` has zero adjacent repeats.

| Test bucket | N | CER | WER |
| --- | --- | --- | --- |
| long_line | 59 | 0.1222 | 0.1850 |
| medication | 200 | 0.1102 | 0.1417 |
| medium_line | 109 | 0.1017 | 0.1202 |
| numeric_schedule | 66 | 0.1237 | 0.1915 |
| punctuation_hyphen | 66 | 0.1237 | 0.1915 |
| repeated_character | 121 | 0.1401 | 0.1693 |
| short_line | 32 | 0.1071 | 0.1047 |
| spacing | 200 | 0.1102 | 0.1417 |

train: clipped 102 (CER 0.2293); unclipped 598 (CER 0.1011).

validation: clipped 30 (CER 0.2663); unclipped 70 (CER 0.1577).

test: clipped 7 (CER 0.1201); unclipped 193 (CER 0.1096).

Whitespace-normalized test CER/WER: 0.0695/0.1417; normalized exact-line accuracy 28.50%. These supplemental metrics do not replace strict CER/WER.

Test samples with adjacent non-whitespace repeats: 82, CER 0.1334.

## 3. Local horizontal detail

Measured 505 non-space repeated glyph runs; 28 have glyph-advance/grid ratio <1 relative to that run's minimum CTC steps. Local ratio min/median/max: 0.833/2.000/3.000. This is not a hard local alignment theorem: convolutional receptive fields and recurrent alignment can borrow neighboring frames. Raw argmax runs for 25 worst greedy errors are retained in `local_repeat_alignment.json`.

## 4. Fixed-phrase renderer isolation

100 identical new phrases per renderer, disjoint from normalized baseline phrases. Diagnostic images are not in training manifests. The fixed-size pass uses font size 23 and measures clipping. The fitted pass uses the same font size for every renderer of a given phrase, reduced only until that phrase fits all renderers; all fitted images are unclipped. Font size therefore varies by phrase, never by renderer within a phrase.

Fitted font sizes span 14-23, versus 22-24 in the original training renders. Fixed-versus-fitted changes therefore conflate removing clipping with changing scale; do not interpret that difference as a pure clipping-effect estimate. Within either pass, phrase/font-size configuration is matched across renderers.

| Renderer | Fixed CER | Fixed clipped | Fitted CER | WER | Exact | Medicine | Dose | Frequency | Duration present |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| arial | 0.1047 | 10 | 0.1727 | 0.2514 | 19.00% | 41.00% | 81.00% | 77.00% | 84.06% |
| calibri | 0.1096 | 1 | 0.2653 | 0.3617 | 16.00% | 37.00% | 77.00% | 62.00% | 68.12% |
| cambria | 0.1018 | 6 | 0.2407 | 0.3170 | 20.00% | 38.00% | 81.00% | 74.00% | 68.12% |
| comic | 0.1185 | 16 | 0.1601 | 0.2263 | 19.00% | 43.00% | 84.00% | 78.00% | 88.41% |
| consola | 0.1561 | 33 | 0.1520 | 0.2500 | 22.00% | 43.00% | 79.00% | 75.00% | 82.61% |
| cour | 0.2014 | 39 | 0.1621 | 0.2626 | 19.00% | 43.00% | 79.00% | 69.00% | 73.91% |
| georgia | 0.0995 | 10 | 0.2037 | 0.2919 | 19.00% | 41.00% | 81.00% | 73.00% | 75.36% |
| segoepr | 0.2051 | 29 | 0.1902 | 0.3310 | 7.00% | 52.00% | 44.00% | 67.00% | 65.22% |
| times | 0.1142 | 4 | 0.2146 | 0.3296 | 13.00% | 33.00% | 73.00% | 68.00% | 76.81% |
| trebuc | 0.1070 | 11 | 0.1509 | 0.2430 | 17.00% | 41.00% | 77.00% | 73.00% | 88.41% |

Hardest unclipped renderer: **calibri**, CER 0.2653. Renderer rankings are conditional on this font-size/configuration and phrase set, not all handwriting.

## 5. Controlled geometry probes and decoder ablation

| Same checkpoint / same 200 test images | CER | WER | Exact | Medicine | Schedule |
| --- | --- | --- | --- | --- | --- |
| A 512 greedy | 0.1102 | 0.1417 | 17.50% | 49.00% | 50.00% |
| B 1024 greedy | 0.5836 | 1.0319 | 0.00% | 2.50% | 22.73% |
| A 512 beam50 | 0.0479 | 0.0750 | 47.50% | 79.50% | 83.33% |
| B 1024 beam50 | 0.6115 | 1.0403 | 0.00% | 3.00% | 36.36% |

| Configuration | Long-line CER | Repeated-character CER |
| --- | --- | --- |
| A greedy | 0.1222 | 0.1401 |
| B greedy | 0.5345 | 0.5779 |
| A beam | 0.0671 | 0.0679 |

B changes only horizontal resize/input width to 1024, doubling glyph width and output steps to 256. It loads the SAME weights; seed, data, dropout inference behavior and decoder are otherwise constant. This is an out-of-distribution inference probe, NOT a retrained width experiment. C (horizontal downsampling change) was not run because global sequence feasibility is adequate; local ratios alone do not establish a downsampling cause. No medical dictionary, language model, or correction is used in beam search.

| Beam split | CER | WER | Exact |
| --- | --- | --- | --- |
| train | 0.0578 | 0.0782 | 46.86% |
| validation | 0.1727 | 0.3105 | 11.00% |
| test | 0.0479 | 0.0750 | 47.50% |

Decoder preferred by validation CER: **beam** (greedy 0.2005, beam 0.1727). This diagnostic choice does not establish readiness.

### Proposed retrained A/B configuration — NOT launched

A: 64×512; B: 64×1024; only input width changes. Both start from scratch with seed 41, identical immutable corpus/splits, AdamW lr=0.001 beta1=0.5 beta2=0.99 weight_decay=0.01 clipnorm=5, batch32, original Flor dropout, light train-only augmentation, up to20 epochs, patience5/min_delta0.002, best-validation checkpointing. Estimated paired CPU runtime: roughly 3–5 hours (A about3–5 minutes/epoch; B conservatively up to twice that). Requires approval before launch. First fix clipping in a separate versioned corpus and establish a clean A baseline; do not confound that repair with a simultaneous architecture change.

## 6. Optional-field conditional metrics

Forms and instructions are also optional in the generator. All conditional metrics, including these fields, are saved in `optional_fields_all.json`. Vocabulary lists are used only for scoring; they never influence decoding.

| Split/decoder | Optional field | Present N | Absent N | Overall | Present only |
| --- | --- | --- | --- | --- | --- |
| train/greedy | forms | 508 | 192 | 100.00% | 100.00% |
| train/greedy | instructions | 243 | 457 | 74.86% | 27.57% |
| validation/greedy | forms | 78 | 22 | 100.00% | 100.00% |
| validation/greedy | instructions | 41 | 59 | 61.00% | 4.88% |
| test/greedy | forms | 148 | 52 | 100.00% | 100.00% |
| test/greedy | instructions | 74 | 126 | 75.00% | 32.43% |
| train/beam | forms | 508 | 192 | 100.00% | 100.00% |
| train/beam | instructions | 243 | 457 | 78.71% | 38.68% |
| validation/beam | forms | 78 | 22 | 100.00% | 100.00% |
| validation/beam | instructions | 41 | 59 | 65.00% | 14.63% |
| test/beam | forms | 148 | 52 | 100.00% | 100.00% |
| test/beam | instructions | 74 | 126 | 78.00% | 40.54% |

| Split/decoder | Field | Present N | Absent N | Overall | Present only |
| --- | --- | --- | --- | --- | --- |
| train/greedy | medicines | 700 | 0 | 48.57% | 48.57% |
| train/greedy | doses | 700 | 0 | 98.00% | 98.00% |
| train/greedy | frequencies | 700 | 0 | 87.00% | 87.00% |
| train/greedy | durations | 493 | 207 | 94.86% | 92.70% |
| validation/greedy | medicines | 100 | 0 | 61.00% | 61.00% |
| validation/greedy | doses | 100 | 0 | 44.00% | 44.00% |
| validation/greedy | frequencies | 100 | 0 | 78.00% | 78.00% |
| validation/greedy | durations | 60 | 40 | 82.00% | 70.00% |
| test/greedy | medicines | 200 | 0 | 49.00% | 49.00% |
| test/greedy | doses | 200 | 0 | 94.50% | 94.50% |
| test/greedy | frequencies | 200 | 0 | 83.00% | 83.00% |
| test/greedy | durations | 144 | 56 | 100.00% | 100.00% |

| Test beam field | Present N | Absent N | Overall | Present only |
| --- | --- | --- | --- | --- |
| medicines | 200 | 0 | 79.50% | 79.50% |
| doses | 200 | 0 | 99.00% | 99.00% |
| frequencies | 200 | 0 | 94.00% | 94.00% |
| durations | 144 | 56 | 100.00% | 100.00% |
| forms | 148 | 52 | 100.00% | 100.00% |
| instructions | 74 | 126 | 78.00% | 40.54% |

## 7. Truncation and schedule changes

| Medicine | Decoder | N | Exact name accuracy | Line CER |
| --- | --- | --- | --- | --- |
| Amoxicillin | greedy | 38 | 0.00% | 0.1648 |
| Amoxicillin | beam | 38 | 57.89% | 0.0746 |
| Cetirizine | greedy | 25 | 0.00% | 0.1449 |
| Cetirizine | beam | 25 | 84.00% | 0.0266 |

| 1-1-1 decoder | N | Exact schedule accuracy |
| --- | --- | --- |
| greedy | 18 | 11.11% |
| beam | 18 | 66.67% |

## 8. Twenty-five worst errors, validation-preferred decoder

| ID / renderer | Ground truth | Prediction | CER | Buckets |
| --- | --- | --- | --- | --- |
| test_00088 / times | Tab  Amoxicillin  40  ml  1-1-1 | Tab Amoxillin 40 ml 1-1 | 0.2581 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line |
| test_00168 / times | Syp  Amoxicillin  650  g  AC  x 5d  before food | Syp Amoxillin 650 g AC x 5d betfore fod | 0.2128 | repeated_character, medication, spacing, long_line |
| test_00156 / times | Inj  PCM  10  mcg  1-0-0 | Inj PCM 10 mcg  1-0 | 0.2083 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line |
| test_00090 / times | Inj  Amoxicillin  650  ml  AC  x 3d | Inj Amoxillin 650 ml AC x 3d | 0.2000 | repeated_character, medication, spacing, medium_line |
| test_00046 / times | Paracetamol  5  g  1-1-1  x 3d  at bedtime | Pacetamol 5 g 1-1  x 3d at bedtime | 0.1905 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line |
| test_00076 / times | Metformin  10  ml  PC  x 7d  as needed | Metformin  10 ml PC x 7d as ned | 0.1842 | repeated_character, medication, spacing, medium_line |
| test_00184 / times | Amoxicillin 10 g 1-0-0 | Amoxillin 10 g 1-0 | 0.1818 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, short_line |
| test_00034 / times | Paracetamol  5  mg  QID  x 5d | Pacetamol 5 mg QID  x 5d | 0.1724 | repeated_character, medication, spacing, medium_line |
| test_00060 / times | Capsule  Paracetamol  625  g  1-0-0  x 5d | Capsule Pacetmol 625 g 1-0-0  x 5d | 0.1707 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line |
| test_00082 / times | Cap  Amoxicillin  625  mcg  HS  for 5 days  as needed | Cap Amoxillin 625 mcg HS  for 5 days as need | 0.1698 | repeated_character, medication, spacing, long_line |
| test_00096 / times | Tablet  Amoxicillin  5  mcg  PC  x 7d  with water | Tablet Amoxillin 5 mcg PC x 7d with water | 0.1633 | repeated_character, medication, spacing, long_line |
| test_00144 / times | Tab  Amoxicillin  500  g  PRN  for 5 days  before food | Tab Amoxillin 50  g PRN  for 5 days before fod | 0.1481 | repeated_character, medication, spacing, long_line |
| test_00120 / times | Inj  Cetirizine  625  g  SOS  x 3d | Inj Cetizine  625 g SOS  x 3d | 0.1471 | repeated_character, medication, spacing, medium_line |
| test_00042 / times | Amoxicillin  650  ml  OD  for 5 days  before food | Amoxillin 650 ml OD  for 5 days before fod | 0.1429 | repeated_character, medication, spacing, long_line |
| test_00054 / times | Syp Amoxicillin 650 ml 1-0-0 | Syp Amoxillin 650 ml 1-0 | 0.1429 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line |
| test_00108 / times | Syp  Pantoprazole  5  mcg  SOS  after food | Syp  Pantoprazole 5 mcg SOS aftr fod | 0.1429 | repeated_character, medication, spacing, long_line |
| test_00174 / times | Tab  Cetirizine  250  ml  1-0-1  x 3d  with water | Tab Cetizine 250 ml 1-0-1  x 3d with water | 0.1429 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line |
| test_00192 / times | Paracetamol 250 g 1-1-1 x 7d | Pacetamol 250 g 1-1 x 7d | 0.1429 | numeric_schedule, medication, punctuation_hyphen, spacing, medium_line |
| test_00026 / times | Tab  Paracetamol  625  mcg  1-0-1  for 7 days  after food | Tab  Paracetamol  625  mcg  1-0-1 for 7 days ater | 0.1404 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line |
| test_00114 / times | Capsule  Metformin  20  ml  BD  for 5 days  as needed | Capsule  Metfrmin 20 ml BD  for 5 days as need | 0.1321 | repeated_character, medication, spacing, long_line |
| test_00052 / times | Syrup  Paracetamol  20  mcg  QID  x 3d | Syrup Pacetamol  20  mcg QID x 3d | 0.1316 | repeated_character, medication, spacing, medium_line |
| test_00006 / times | PCM 40 g BD before food | PCM 10 g BD betore fod | 0.1304 | repeated_character, medication, spacing, short_line |
| test_00040 / times | Paracetamol  500  mg  1-1-1  after food | Pacetamol 500  mg  1-1-1 after fod | 0.1282 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, medium_line |
| test_00012 / times | Syp  Paracetamol  5  mcg  1-0-0  for 7 days  after food | Syp Pacetamol 5 mcg  1-0-0  for 7 days after fod | 0.1273 | repeated_character, numeric_schedule, medication, punctuation_hyphen, spacing, long_line |
| test_00021 / trebuc | Tablet  Paracetamol  500  g  TDS | Tablet Pacetamol  500  g TDS | 0.1250 | repeated_character, medication, spacing, medium_line |

## 9. Evidence and next decision

Measured global output shortage is NOT the explanation: every target fits with substantial margin. Silent render clipping is a demonstrated data defect and makes some full transcriptions impossible. It does not explain all internal name truncations. Local glyph span estimates, decoder ablation, and matched-phrase renderer results constrain remaining hypotheses but do not prove a single cause. Recommended next change: fail-fast rendering bounds and a clean, versioned width512 corpus, retaining this checkpoint/dataset as immutable references. Then inspect repeat/hyphen posteriors and establish a clean baseline before a separately approved width-only retraining trial. No large volunteer collection, page OCR, or MediKiosk integration.

## 10. Verification and Git status

16 tests passed; Ruff checks and formatting checks passed for touched Python files; Python compilation passed. Pytest emitted an existing cache-permission warning and a Starlette/AnyIO deprecation warning. No commit or push. Outside-workspace changes below are pre-existing and were not edited by this audit.

```text
 M ../backend/.env.example
 M ../backend/app/services/paddleocr_ocr.py
 M ../frontend/src/api/client.ts
?? ./
```
