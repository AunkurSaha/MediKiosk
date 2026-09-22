# Upstream architecture and training behavior

## Reproducible source

- Repository: `https://github.com/arthurflor23/handwritten-text-recognition.git`
- Branch: `master`
- Commit: `fc8515f9aa9dc54a93a75366ca8d8ac4adaf35c8`
- License: MIT; the upstream notice is preserved in `LICENSES/`.

## Flor recognition model

The upstream `sarah/models/recognition/flor.py` model is a TensorFlow/Keras
CNN-attention-BLSTM recognizer. It uses seven convolution stages (8, 16, 32,
64, 80, 112 and 128 filters), gated residual convolution blocks, asymmetric
pooling, four-head self-attention, and three stacked pairs of forward/backward
128-unit LSTMs. A dense layer produces per-timestep character logits.

The upstream data default is `(64, 1024, 1)` grayscale. The bounded MediKiosk
tiny test uses `(64, 512, 1)` to reduce CPU time. For its 46-class synthetic
vocabulary the model has approximately 1.62 million trainable/non-trainable
parameters (the exact output-layer count depends on vocabulary size).

Training uses an upstream CTC loss (`tf.compat.v1.nn.ctc_loss`) and AdamW in
the normal Sarah pipeline. Decoding uses Keras CTC beam search; the standalone
smoke wrapper uses greedy CTC decoding for predictable latency.

Weights are persisted as Keras `*.weights.h5` files. The MediKiosk wrapper
stores non-secret character/image metadata beside a checkpoint as JSON.

## Random initialization

Source inspection confirms `Compose.compile(run_context=None)` creates a new
MLflow run and compiles the newly constructed Keras model without calling
`load_weights`. A supplied existing run context takes the other branch and
loads `model/<model>.weights.h5`. Therefore a new recognition run is random
initialization when no recognition run/checkpoint is supplied.

Upstream dataset command after an approved dataset is installed:

```powershell
python sarah --source iam --text-level line --recognition flor --training --gpu -1
```

Do not pass `--recognition-run-id` when starting a fresh model. The local
MediKiosk tiny proof uses `scripts/tiny_overfit.py`, directly instantiating the
same upstream `RecognitionModel` and upstream `CTCLoss`, with a fixed seed and
no weight loading.

## Segmentation decision

Upstream includes a trainable Flor segmentation model, but no suitable
prescription checkpoint is present locally. The first standalone prototype
therefore uses conservative OpenCV connected-line segmentation and preserves
`[x, y, width, height]` boxes in reading order. It is a smoke-test component,
not validated full-page prescription segmentation.

## Dataset note

IAM is the most relevant initial generic English handwriting baseline among
the integrated upstream sources because the loader supports its official
writer-independent line split. It was not downloaded: dataset access/licensing
must be confirmed separately, and no large dataset is required for setup proof.
