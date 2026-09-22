# Renderer-independent synthetic and writer-independent handwriting protocol

## Synthetic stage

`build_generalization_dataset.py` creates 1,000 unique prescription-style
phrases with renderer- and phrase-disjoint manifests:

| Split | Samples | Synthetic renderers |
| --- | ---: | ---: |
| Train | 700 | 7 |
| Validation | 100 | 1 unseen |
| Test | 200 | 2 unseen |

Renderers are fonts, not people. Results from this stage measure synthetic
renderer transfer and must not be described as handwriting accuracy.

Training uses Flor's intended dropout (`training=True`). Only training images
receive the stage-1 light preset: rotation up to 1.5 degrees, perspective up
to 0.012, 12% slight blur, and 20% brightness scaling. Validation and test
images are never augmented. The best validation-CER checkpoint is evaluated
once on the held-out test split.

## Volunteer stage

Collect 30 predefined lines from each of 10 consenting volunteers. Assign an
opaque writer ID; do not put names or other personal data in filenames or the
manifest. Use seven complete writers for training, one complete writer for
validation, and two complete writers for final testing. Never distribute one
writer's lines across splits.

The manifest contract remains:

```csv
image,text,writer_id,sample_id,source_type
writer_01_001.png,Tab Paracetamol 500 mg BD,writer_01,writer_01_001,volunteer
```

Keep consent records outside the OCR dataset. Volunteer images are private,
Git-ignored inputs and must not be derived from MediKiosk patient uploads.

## Reported metrics

- Corpus-weighted character error rate (CER)
- Corpus-weighted word error rate (WER)
- Exact medicine-name extraction accuracy
- Exact dose extraction accuracy
- Exact frequency extraction accuracy
- Exact duration extraction accuracy

The synthetic smoke report is only a plumbing check. It is not an acceptance
result. Do not proceed to page OCR or MediKiosk integration until a separately
approved threshold is met on two completely unseen volunteer writers.
