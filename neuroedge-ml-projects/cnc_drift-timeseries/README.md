# cnc_drift-timeseries

- **Objective:** detect CNC machining drift from spindle-load, x_axis_error and vibration signals
- **Modality:** timeseries
- **Consumer:** NeuroEdge Agentic AI Studio use case
  `manufacturing/cnc-machine-performance-drift-leading-to-production-loss` (edge `drift_score` 0..1, threshold 0.7)

Layout per `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md` (ADR-0021):
`data/` for cards and recipes, `model-select.md`, and one `<architecture>/` subfolder per built model.

## Stage log

| Date | Command | Artifact | Note |
|---|---|---|---|
| 2026-09-15 | `/dataset-scout --timeseries` | `data/dataset-card.md` | Pick: KIT multimodal CNC milling (CC BY 4.0); moved here from the Studio use-case tree |
