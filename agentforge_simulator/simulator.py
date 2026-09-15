#!/usr/bin/env python3
"""simulator.py — entry point for the NeuroEdge data-source simulator.

Thin wrapper: all logic lives in the ``neuro_sim`` package next to this file.
Run ``python simulator.py --help`` for options.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling package importable when run as a bare script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from neuro_sim.cli import main  # noqa: E402  — must follow sys.path insert

if __name__ == "__main__":
    raise SystemExit(main())
