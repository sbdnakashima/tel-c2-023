"""FieldLogWorkflowGraph — Inner graph (4ノード線形パイプライン)"""

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from src.nodes.completion_validator_node import CompletionValidatorNode
from src.nodes.field_log_parser_node import FieldLogParserNode
from src.nodes.open_item_flag_node import OpenItemFlagNode
from src.nodes.summary_generator_node import SummaryGeneratorNode
from src.schemas.state import State


class FieldLogWorkflowGraph(BaseGraph):
    """Inner graph for Cat 2 Field Log Workflow.

    Pipeline:
        START → field_log_parser → completion_validator
              → open_item_flag → summary_generator → END

    Called by FieldLogWorkflowGraphNode.get_subgraph() in graph.py.
    """

    @property
    def name(self) -> str:
        return "field_log_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        self._nodes["field_log_parser"] = FieldLogParserNode()
        self._nodes["completion_validator"] = CompletionValidatorNode()
        self._nodes["open_item_flag"] = OpenItemFlagNode()
        self._nodes["summary_generator"] = SummaryGeneratorNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "field_log_parser")
        self._sg.add_edge("field_log_parser", "completion_validator")
        self._sg.add_edge("completion_validator", "open_item_flag")
        self._sg.add_edge("open_item_flag", "summary_generator")
        self._sg.add_edge("summary_generator", END)

    def route(self, state: AgentState) -> str:
        return END

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "parsed_actions": state.get("parsed_actions"),
            "extracted_measurements": state.get("extracted_measurements"),
            "parse_confidence": state.get("parse_confidence"),
            "validation_results": state.get("validation_results"),
            "completion_status": state.get("completion_status"),
            "open_items": state.get("open_items"),
            "completion_report": state.get("completion_report"),
            "audit_log": state.get("audit_log"),
            "status": state.get("status"),
            "error_code": state.get("error_code"),
        }
