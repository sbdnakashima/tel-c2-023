"""Integration tests for TEL-C2-023 Graph — end-to-end pipeline verification."""

import json

import pytest

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel


# ---------------------------------------------------------------------------
# モック依存
# ---------------------------------------------------------------------------

class _MockLLM:
    """FieldLogParserNode / SummaryGeneratorNode に DI するモック LLM。"""

    def complete(self, messages):
        last_content = messages[-1].get("content", "") if messages else ""
        if "field_log" in last_content:
            # FieldLogParserNode からの呼び出し
            return json.dumps({
                "actions": [
                    {"sequence": 1, "action_type": "inspect", "description": "Site survey", "component": "", "result": "success"},
                    {"sequence": 2, "action_type": "install", "description": "Antenna installation", "component": "antenna", "result": "success"},
                    {"sequence": 3, "action_type": "configure", "description": "Radio configuration", "component": "radio", "result": "success"},
                    {"sequence": 4, "action_type": "test", "description": "Signal test", "component": "antenna", "result": "success"},
                ],
                "measurements": {"vswr": {"value": 1.38, "unit": "", "status": "pass"}},
                "confidence": 0.92,
                "log_completeness": "complete",
            })
        else:
            # SummaryGeneratorNode からの呼び出し
            return json.dumps({
                "executive_summary": "Base station installation completed successfully. All required steps performed.",
                "completion_status": "complete",
                "work_performed": ["Site survey", "Antenna installation", "Radio configuration", "Signal test"],
                "open_items": [],
                "quality_assessment": "pass",
                "next_steps": "none",
            })


# ---------------------------------------------------------------------------
# Graph ファクトリ
# ---------------------------------------------------------------------------

def _make_graph(llm=None):
    """テスト用 Graph を構築する。LLM を DI して外部呼び出しを回避する。"""
    from src.graph.graph import Graph, FieldLogWorkflowGraphNode
    from src.graph.field_log_workflow_graph import FieldLogWorkflowGraph
    from src.nodes.field_log_parser_node import FieldLogParserNode
    from src.nodes.completion_validator_node import CompletionValidatorNode
    from src.nodes.open_item_flag_node import OpenItemFlagNode
    from src.nodes.summary_generator_node import SummaryGeneratorNode

    _llm = llm or _MockLLM()

    class _TestInnerGraph(FieldLogWorkflowGraph):
        def register_nodes(self) -> None:
            self._nodes["field_log_parser"]     = FieldLogParserNode(llm=_llm)
            self._nodes["completion_validator"] = CompletionValidatorNode()
            self._nodes["open_item_flag"]       = OpenItemFlagNode()
            self._nodes["summary_generator"]    = SummaryGeneratorNode(llm=_llm)

    class _TestGraphNode(FieldLogWorkflowGraphNode):
        def get_subgraph(self):
            return _TestInnerGraph(config=self._parent_config())

    class _TestGraph(Graph):
        def register_nodes(self) -> None:
            super().register_nodes()
            self._nodes["main"] = _TestGraphNode()

    return _TestGraph()


def _ctx() -> InvocationContext:
    return InvocationContext(
        correlation_id="test-int",
        session_id="test-session",
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
    )


def _invoke_with_payload(g, payload: dict) -> dict:
    """payload dict を JSON 文字列として invoke する（user_input 経由でノードが展開する）。"""
    return g.invoke(json.dumps(payload), ctx=_ctx())


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

class TestGraphIntegration:

    def test_complete_pipeline_returns_success(self):
        """正常系: 全ノード通過で status=success"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-12345",
            "work_type": "base_station_installation",
            "field_log": "Arrived at site 09:00. Site survey done. Installed antenna. Configured radio. VSWR=1.38. Signal test passed.",
        })
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_completion_report_in_output(self):
        """completion_report が output に含まれる"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-12345",
            "work_type": "base_station_installation",
            "field_log": "Arrived at site. Site survey done. Installed antenna. Configured radio. Signal test passed.",
        })
        assert result.get("completion_report") is not None
        report = json.loads(result["completion_report"])
        assert "executive_summary" in report

    def test_audit_log_in_output(self):
        """audit_log が output に含まれる"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-12345",
            "work_type": "base_station_installation",
            "field_log": "Arrived at site. Site survey done. Installed antenna. Configured radio. Signal test passed.",
        })
        assert result.get("audit_log") is not None
        audit = json.loads(result["audit_log"])
        assert "completion_status" in audit
        assert "timestamp" in audit

    def test_completion_status_in_output(self):
        """completion_status が output に含まれる"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-12345",
            "work_type": "base_station_installation",
            "field_log": "Arrived at site. Site survey done. Installed antenna. Configured radio. Signal test passed.",
        })
        assert result.get("completion_status") in ("complete", "partial", "incomplete")

    def test_node_history_contains_all_outer_nodes(self):
        """Outer graph の必須ノードが node_history に記録される"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-12345",
            "work_type": "base_station_installation",
            "field_log": "Arrived at site. Site survey done. Installed antenna. Configured radio. Signal test passed.",
        })
        history = result.get("node_history", [])
        assert "InitializeNode" in history
        assert "PassThroughNode" in history
        assert "FinalizeNode" in history

    def test_missing_field_log_returns_error(self):
        """field_log 欠損 → error"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-001",
            "work_type": "base_station_installation",
        })
        assert result["status"] == AgentStatus.ERROR.value

    def test_unknown_work_type_returns_error(self):
        """未知の work_type → error"""
        g = _make_graph()
        result = _invoke_with_payload(g, {
            "work_order_id": "WO-001",
            "work_type": "invalid_type_xyz",
            "field_log": "Some work was done.",
        })
        assert result["status"] == AgentStatus.ERROR.value
