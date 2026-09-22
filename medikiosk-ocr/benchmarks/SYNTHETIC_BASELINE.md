# Renderer-independent synthetic baseline

The full 700/100/200 split was evaluated from the best validation checkpoint.
Dropout was enabled during training and light augmentation applied only to
training inputs. No MediKiosk integration or page OCR was attempted.

The original run was interrupted. Its weights were recovered and validated at
CER 0.2929, but its exact source epoch and optimizer state were not saved.
Continuation used a fresh optimizer for nine epochs, labelled 11 through 19.
Early stopping fired at label 19 after five non-improving epochs. The selected
checkpoint is continuation label 14 (the fourth continuation epoch), not the
final epoch. These labels do not establish an uninterrupted 19-epoch run.

| Metric | Train (700) | Validation (100) | Test (200) |
| --- | ---: | ---: | ---: |
| CER | 0.1258 | 0.2005 | 0.1102 |
| WER | 0.1515 | 0.3063 | 0.1417 |
| Exact-line accuracy | 20.14% | 10.00% | 17.50% |
| Medicine accuracy | 48.57% | 61.00% | 49.00% |
| Dose accuracy | 98.00% | 44.00% | 94.50% |
| Frequency accuracy | 87.00% | 78.00% | 83.00% |
| Duration accuracy | 94.86% | 82.00% | 100.00% |

Field matching is case-insensitive and whitespace-normalized. Correct absence
of an optional duration counts as correct. CER/WER and exact-line accuracy
retain their strict transcription definitions. Test renderers are different
from the more challenging validation renderer; lower test CER is not evidence
of writer-independent handwriting performance.

## Representative worst errors

| Ground truth | Prediction | CER | Coarse error type |
| --- | --- | ---: | --- |
| Tab  Amoxicillin  40  ml  1-1-1 | Tab Amoxilin 40 ml 1 | 0.3548 | number |
| Tab Cetirizine 5 g 1-1-1 x 7d | Tab Cetine 5 g 1 x 7d | 0.2759 | number |
| Inj  Cetirizine  625  g  SOS  x 3d | Inj Cetine 625 g SOS x 3d | 0.2647 | long_line |
| Capsule  Amoxicillin  40  mg  AC  as needed | Capsule Amoxilin 40 mg AC as ned | 0.2558 | long_line |
| Amoxicillin  625  mg  0-0-1  before food | Amoxilin 625 mg 0-1 before fod | 0.2500 | number |

All 25 worst test records are retained in `generalization.json`. Error tags
are heuristic review aids, not established causal diagnoses. Repeated-letter,
numeric-abbreviation, and spacing omissions require further investigation.

## Decision

The model demonstrably generalizes beyond memorization, but 49% exact medicine
accuracy and 17.5% exact-line accuracy are not useful prescription recognition.
Debug repeat/alignment behavior and renderer sensitivity before a substantial
volunteer collection effort. Do not add epochs blindly, start page OCR, or
integrate the model into MediKiosk.
