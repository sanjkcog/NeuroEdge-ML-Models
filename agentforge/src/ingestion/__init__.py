"""ingestion/ — inbound AI-assisted ingestion (ADR-0012 Direction 2, EP-01...EP-07).

Additive package: everything here composes with the existing `exchange/` and
`state/` modules (Protocol +1 verb, config/ledger/gate/audit reuse) rather than
forking any of them (M4). See neuroedge/docs/project_related/ai-assisted-ingestion/ for the
HLD/LLD this package implements.
"""

from __future__ import annotations
