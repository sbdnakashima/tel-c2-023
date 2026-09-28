"""AgentCore Platform v1.0 — TEL-C2-023 Telecom Field Engineer Work Log Summarization & Completion Validation Agent

Cat 2 Outer graph (AgentBaseGraph) + Inner graph (FieldLogWorkflowGraph via GraphNode).

Outer pipeline:
  START → initialize → pre_process → main → {route} → post_process → finalize → END
                                          ↓ (ERROR)
                                        finalize

Inside main (FieldLogWorkflowGraphNode):
  START → field_log_parser → completion_validator → open_item_flag → summary_generator → END
"""

from typing import Any, ClassVar

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from src.nodes.pass_through_node import PassThroughNode
from src.schemas.state import State


class FieldLogWorkflowGraphNode(GraphNode):
    """GraphNode wrapping FieldLogWorkflowGraph; assigned to the `main` slot.

    Inner graph: field_log_parser → completion_validator → open_item_flag → summary_generator
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def get_subgraph(self) -> Any:
        from src.graph.field_log_workflow_graph import FieldLogWorkflowGraph

        return FieldLogWorkflowGraph(config=self._parent_config())

    def extract_input(self, state: AgentState) -> str:
        return state.get("field_log", "") or state.get("user_input", "") or ""

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "parsed_actions": sub_result.get("parsed_actions"),
            "extracted_measurements": sub_result.get("extracted_measurements"),
            "parse_confidence": sub_result.get("parse_confidence"),
            "validation_results": sub_result.get("validation_results"),
            "completion_status": sub_result.get("completion_status"),
            "open_items": sub_result.get("open_items"),
            "completion_report": sub_result.get("completion_report"),
            "audit_log": sub_result.get("audit_log"),
            "status": sub_result.get("status"),
            "error_code": sub_result.get("error_code"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {}


class Graph(AgentBaseGraph):
    """TEL-C2-023 outer graph. Cat 2 fixed-pipeline (AgentBaseGraph).

    Backbone: initialize → pre_process(PassThrough) → main(FieldLogWorkflowGraphNode)
              → post_process(PassThrough) → finalize
    """

    @property
    def name(self) -> str:
        return "tel_c2_023"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()
        self._nodes["pre_process"] = PassThroughNode()
        self._nodes["main"] = FieldLogWorkflowGraphNode()
        self._nodes["post_process"] = PassThroughNode()

    def _extra_initial_state(self) -> dict[str, Any]:
        # input_context は invoke() 実行時に渡される。
        # _extra_initial_state() はフレームワークが initial_state を組み立てた後に
        # update() で呼ばれるため、ここでは None で初期化するだけでよい。
        # 実際のフィールド注入は InvocationContext / input_context 経由で行われる。
        return {
            "work_order_id": None,
            "work_type": None,
            "field_log": None,
            "measurements": None,
            "parsed_actions": None,
            "extracted_measurements": None,
            "parse_confidence": None,
            "validation_results": None,
            "completion_status": None,
            "open_items": None,
            "completion_report": None,
            "audit_log": None,
            "error_code": None,
        }

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "output": state.get("completion_report"),
            "completion_report": state.get("completion_report"),
            "audit_log": state.get("audit_log"),
            "completion_status": state.get("completion_status"),
            "open_items": state.get("open_items"),
            "validation_results": state.get("validation_results"),
            "parse_confidence": state.get("parse_confidence"),
            "status": state.get("status"),
            "error_code": state.get("error_code"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
