# Active Context

## Focus
cnc_drift-timeseries at M1 (dataset-card done). Web ADR-0007 T-6 / E-5 (implemented in Web 2026-09-17; the command and skill text here now specify it, no generated code regenerated yet): `/model-build` must write `at_fpr` + `decision_threshold` into `meta.json`, `eval.py` must read the operating point from there (never the Web schema) and record the measured `fpr` in `metrics.json`; one shared `DEFAULT_AT_FPR = 0.05`. M8's KPI comparison is a documented miss + acknowledgement, never a stop. Guide: NeuroEdge-Device `docs/reference/how_to_capture_measure_report_model_performance.md`.

## Recently changed
- Initial AgentForge memory bank created.

## Next 3 actions
1. Fill in project overview in CLAUDE.md.
2. Add canonical build and test commands to AGENTS.md and CLAUDE.md.
3. Run `python health_check/cli.py --verbose`.

## Blocked-on
- None.

## Last updated
2026-09-17
