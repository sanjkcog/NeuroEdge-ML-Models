# Progress

## AgentForge bootstrap
- **Done:** Installed AgentForge assets and initialized the memory bank.
- **In progress:** Customize project-specific instructions.
- **Blocked:** None.
- **Next:** Run a health check and first route preflight.

## Performance expectations (Web ADR-0007)
- **Done (2026-09-17):** design accepted; this repo's obligations are T-6/E-5 (operating point in `meta.json`, read by `eval.py`) and T-7 (`RLMetrics` from simulation before any RL KPI is mapped).
- **In progress:** none.
- **Done (2026-09-17):** `/model-build` command and `ml-model-package` skill specify `meta.json.at_fpr` + `decision_threshold` and `eval.py` reading them (mirrored from Assets).
- **Next:** regenerate `cnc_drift-timeseries/<arch>/eval.py` so the operating point is actually read from `meta.json`.
