"""AgentCore Platform v1.0"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event


class PassThroughNode(FunctionNode):
    """Outer backbone の pre_process / post_process スロット用パススルーノード。

    Cat 2 では domain logic を Inner graph に委譲するため、
    Outer の pre_process・post_process はステートをそのまま透過させる。
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        emit_trace_event("pass_through", {"node": self.__class__.__name__}, state)
        return {"status": state.get("status") or AgentStatus.SUCCESS.value}
