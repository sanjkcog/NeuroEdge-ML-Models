"""neuro_sim — NeuroEdge data-source simulator.

Replays records from ``sim_input/`` files and streams them over a chosen
transport (SSE, MQTT, webhook, or generic API call), optionally logging what
was sent to ``sim_output/`` as JSON or CSV.

Two input families (see ``loaders``):
  - timeseries : .csv, .xls/.xlsx, .json   -> one record per row/object
  - media      : images and video          -> one record per image/frame

This package is installed into a consuming project at
``agentforge_simulator/`` by the AgentForge installer. Run it with::

    python agentforge_simulator/simulator.py --help
"""

__version__ = "0.1.0"
