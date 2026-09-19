# -*- coding: utf-8 -*-
"""Shared data-loading and metrics code for cnc_drift_1dcnn-timeseries's 1DCNN and MiniRocket
packages (M8 round 3, code-review HIGH #C). Single source of truth for `ts_data` and `metrics` --
previously hand-duplicated between `1DCNN/` and `MiniRocket/`, which is how a fix could land in
one copy and not the other.

Imported by both packages via a `sys.path` insert relative to the importing file
(`Path(__file__).resolve().parents[1]`), so it works regardless of the caller's cwd.
"""
