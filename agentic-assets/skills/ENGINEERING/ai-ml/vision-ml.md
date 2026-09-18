---
name: vision-ml
description: Vision ML for the ai-ml discipline — detection, classification and visual anomaly detection on images. Leakage-safe splitting (group by source image and capture session, never by output file), near-duplicate detection, vision dataset licence verdicts, metric selection (mAP@50 vs mAP@50-95, per-class recall), and the acquisition profile for image archives. Use for any objective over images or video.
origin: ADR-0024 (acquisition profile), ADR-0023 (families and visual anomaly detection)
---

# Vision ML

The counterpart to [`time-series-ml`](time-series-ml.md). Labeling lives in
[`data-labeling`](data-labeling.md), synthesis in [`synthetic-data`](synthetic-data.md),
backbones in [`pretrained-and-transfer`](pretrained-and-transfer.md), and the deployable
contract in [`ml-model-package`](ml-model-package.md). **This file owns what none of those do:
splitting, metric choice, and acquisition.**

## When to Activate

- The objective is over images or video: detection, segmentation, classification, visual anomaly
- `/dataset-scout --vision`, `/dataset-download`, `/dataset-verify`, `/model-select` for a CV task
- Reviewing a vision dataset's splits — especially one exported from a labelling portal

## Leakage-safe splitting — the #1 vision failure mode

The time-series analogue is overlapping windows. **The vision version is augmented or
near-duplicate variants of one source image landing in more than one split**, and it is more
dangerous because it arrives pre-packaged: portal exports commonly apply augmentation *before*
splitting, so `train/` and `valid/` contain rotations, crops and brightness variants of the same
photograph. mAP then measures memorisation, reports a strong number, and shows no symptom.

1. **Group by source image, then by capture session.** The unit is the thing the camera saw
   once, not the file on disk. One physical part photographed five times is **one** unit; five
   augmented copies of one photo are **one** unit.
2. **Split first, augment second.** Always. Augmentation is a training-time operation; a
   dataset that ships augmented and pre-split has already made this mistake for you.
3. **Never trust a portal's split.** Check it: hash the source images, and compare near-
   duplicates across split boundaries before accepting. FiftyOne's uniqueness/duplicates
   pipeline is the standard tool; the archive's own CRCs (see Acquisition) catch exact copies
   for free.
4. **Frames from one video are one unit.** Adjacent frames are near-identical; splitting by
   frame puts the same instant on both sides.
5. **Group by capture condition when it correlates with the label** — same line, same lighting
   rig, same shift. A model that learns "this lighting means defect" scores well and transfers
   to nothing.
6. **Fit any normalisation on the train split only**, and ship the statistics with the model.

> Sanity check that costs a minute: if validation mAP is far above what the task plausibly
> supports, suspect the split before celebrating the model.

## Metrics — pick before training, not after

- **Detection:** `map50_95` is the headline; `map50` alone rewards loose boxes. Report both,
  plus **per-class recall** — a mean hides a class that is never detected.
- **Classification:** top-1 only when classes are balanced. Otherwise per-class recall and the
  confusion matrix; accuracy on a 95/5 split is a number that means nothing.
- **Visual anomaly detection:** the rare-event rules of `time-series-ml` apply unchanged —
  **PR-AUC primary**, recall at a fixed FPR for the operational framing, ROC-AUC secondary and
  never alone.
- **Small objects:** report mAP by object-size band; a single figure hides that small instances
  fail, which is usually the whole problem.
- Every published number carries its `eval_split` (`ml-model-package`), or it is not published.

## Datasets — with licence verdicts

Licences churn; verify at download and treat this as orientation, not legal review.

| Source | Best for | Licence posture |
|---|---|---|
| **Roboflow Universe** | ready-to-train industrial detection sets | **per dataset** — many CC BY 4.0, some non-commercial. Check each; a portal's convenience is not a licence |
| **VISION-Datasets** (HF) | 14 curated manufacturing-inspection sets | per dataset; a strong first stop for defect detection |
| **COCO** | pretraining, general detection | CC BY 4.0 (annotations); images are Flickr-licensed — **check before redistributing** |
| **Open Images** | large-scale detection | CC BY 4.0 annotations; images per-image licensed |
| **MVTec AD** | the visual-anomaly benchmark | 🔴 **CC BY-NC-SA 4.0 — non-commercial.** The default choice in every tutorial; keep it out of product builds |
| **VisA** | visual anomaly | CC BY 4.0 — the commercially usable alternative to MVTec |
| ImageNet | classification pretraining | research terms; weights trained on it are generally fine, redistribution of images is not |

Licence-fit is the **blocking** gate (`dataset-sourcing` gate 2, ADR-0014 OQ-2).

## Acquisition profile (ADR-0024 D-6)

Transport rules are in [`dataset-acquisition`](../_mechanism/dataset-acquisition.md); this is
the vision-specific selection layer.

- **Unit:** source image, or capture session where one exists.
- **Valid selection:** stratified by class; **class-scoped** — for an objective over 2 of 80
  classes, fetch only images containing those classes. This is normally the largest single cut
  available, the vision analogue of scoping to 7 of 33 experiments.
- **Invalid selection:** a prefix of a file listing. Image archives are ordered by class or by
  capture batch, so the first *n*% is one class or one session — the failure mode the
  time-series prefix rule exists to prevent, arriving by a different route.
- **Redundancy to look for by file type:** the same annotations shipped as COCO JSON *and* YOLO
  txt *and* VOC XML (take one); multiple resolutions of the same images; video alongside
  extracted frames; thumbnail/preview directories.
- **Free win:** the archive index's CRC finds exact duplicate images with no payload fetched —
  and duplicates are endemic in scraped and portal-assembled vision sets.

## Deployment shape

Per `ml-model-package`: ONNX at the pinned opset (**13** for NeuroEdge), `input.layout`,
`input.resolution` and `color_order` in `meta.json` — **RGB vs BGR is a silent accuracy loss**,
exactly as channel order is for sensors. Letterbox parameters belong in `meta.json` too when the
runtime must reverse them, and `output_schema` names the post-processor (`yolo_boxes_v8`, …)
rather than leaving a runtime to infer it.

## Do NOT

- Do not split after augmenting, or trust a split you did not verify.
- Do not let one source image, one video, or one capture session span splits.
- Do not report mAP@50 alone, or accuracy on imbalanced classes.
- Do not train on MVTec AD (non-commercial) for anything shipped.
- Do not prefix-fetch an image archive — stratify or class-scope instead.
