"""exchange — the Git exchange substrate (ADR-0012 POC): a neutral manifest of
AgentForge's run-state/gates, a pluggable bidirectional adapter (Git/GitHub Issues
first), and the hard-gate fence that keeps external drive safe (ADR-0009 invariant).

A real package (not a flat sys.path module like state/qa) so that `exchange.adapter`
never collides with `agentforge/src/qa/adapter.py`, which is also on sys.path via
agentforge/tests/conftest.py.
"""
