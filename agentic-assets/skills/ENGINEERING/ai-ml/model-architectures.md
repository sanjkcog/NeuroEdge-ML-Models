---
name: model-architectures
description: Architecture patterns for the four model families AgentForge builds — CNN (vision), time-series/sensor models (1D-CNN, ROCKET, TSFM), DNN/MLP (tabular & general), and recommender systems — including when to use each, standard heads, and the sizing/regularization defaults that make generated code correct. Use when selecting or generating a model architecture.
origin: NeuroEdge AgentForge
---

# Model Architectures (CNN · Time-Series · DNN · Recommender)

The reference patterns behind [`model-codegen`](model-codegen.md): what a *correct* model of each
family looks like, so the generated `.py`/`.tf` isn't a plausible-looking net that quietly
under-performs. Pair with [`pretrained-and-transfer`](pretrained-and-transfer.md) for backbone choice.

## When to Activate

- `/model-select` or `/model-build` for a CNN, DNN/MLP, or recommender
- Reviewing a generated architecture (`ml-eval-reviewer`)

## CNN — vision

- **Default: transfer-learn a pretrained backbone** (timm/torchvision), don't hand-roll conv stacks.
- **Task heads:** classification (global-pool → linear); detection (e.g. a detection head / YOLO-style
  or torchvision detection); segmentation (FCN/U-Net/DeepLab-style decoder or SAM-distilled).
- **Regularization:** data augmentation first, then dropout / weight decay; BatchNorm in train vs eval
  mode handled correctly.
- **Input hygiene:** normalization must match the pretrained backbone's expected mean/std; resolution
  matched to the backbone.

## Time-series / sensor — anomaly detection, fault classification, RUL

- **Ladder, in order** ([`time-series-ml`](time-series-ml.md) is the full reference, ADR-0015):
  **MiniRocket/MultiRocket + ridge** first (the honesty floor — seconds to train, near-SOTA);
  then **1D-CNN / InceptionTime** (the deep control arm, clean ONNX export); a **frozen TSFM
  encoder + head** (MOMENT, MIT) only when labels are scarce.
- **Input shape:** channels-first `(batch, n_features, window)`; window/stride and **channel
  order** are part of the model contract — persist them in `meta.json` beside the weights.
- **Splits before architecture, and never random:** chronological or per-unit (`GroupKFold`) —
  overlapping windows shuffled across splits invalidate every number.
- **Metrics are different:** PR-AUC + recall@fixed-FPR + event-level F1 for anomaly detection —
  never raw accuracy, never point-adjust F1 alone. The spec MUST name them so the eval gate is
  correct (same rule as recommenders below).

## DNN / MLP — tabular & general

- **Tabular caution:** for pure tabular data, gradient-boosted trees (XGBoost/LightGBM) often beat an
  MLP — say so when the objective is tabular; only choose a DNN when it clearly fits (embeddings,
  multi-modal, very large data).
- **MLP patterns:** sensible width/depth, BatchNorm/LayerNorm, dropout, ReLU/GELU; embed categorical
  features rather than one-hot when cardinality is high.
- **Outputs:** classification vs regression head + the matching loss (CE vs MSE/Huber).

## Recommender systems

- **Families:** collaborative filtering (matrix factorization), **two-tower** retrieval (user tower +
  item tower, dot-product), and sequential/deep models (e.g. embeddings + MLP ranking).
- **Standard shape:** embedding tables for users/items + features → interaction → ranking head.
- **Metrics are different:** ranking metrics (Recall@K, **nDCG**, MAP), not accuracy — the eval gate
  must use these. Cold-start and popularity bias are first-class concerns.
- **Data:** implicit vs explicit feedback changes the loss (BPR / sampled softmax vs regression).

## Sizing & defaults (so generated code trains)

- Choose model size against **data size and deployment target** — an over-parameterized net on small
  data overfits; an under-parameterized one underfits.
- Always define train/val/test **before** architecture; the architecture serves the data, not vice
  versa.

## Output

An architecture spec (family, backbone/head, sizes, loss, metric set) consumed by
[`model-codegen`](model-codegen.md). For recommenders, the spec MUST name the ranking metric set so the
eval gate is correct.

## Do NOT

- Do not default to a DNN for tabular data without noting the tree-model alternative.
- Do not evaluate a recommender with classification accuracy — use ranking metrics.
