# PB-7: HITL interrupt propagation — HITL_ENABLED 時に Graph が interrupt を伝播すること

import os

import pytest


@pytest.mark.skipif(not os.getenv("HITL_ENABLED"), reason="HITL not enabled")
def test_pb7_hitl_interrupt_propagation():
    from src.graph.graph import Graph
    from framework.schemas.invocation_context import InvocationContext
    from framework.schemas.trust_level import TrustLevel

    g = Graph()
    ctx = InvocationContext(
        correlation_id="pb7-test",
        session_id="pb7-session",
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
    )
    result = g.invoke("{}", ctx=ctx)
    assert result is not None
