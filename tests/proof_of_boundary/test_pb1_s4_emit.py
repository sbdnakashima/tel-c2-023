# PB-1: S-4 emit_trace_event — execute() 内で少なくとも 1 回呼ばれること

import json
from unittest.mock import patch

import pytest

from framework.schemas.agent_status import AgentStatus


class MockLLM:
    def complete(self, messages):
        return json.dumps({
            "actions": [{"sequence": 1, "action_type": "install", "description": "x", "component": "", "result": "success"}],
            "measurements": {},
            "confidence": 0.9,
            "log_completeness": "complete",
        })


class MockSummaryLLM:
    def complete(self, messages):
        return json.dumps({
            "executive_summary": "Done.",
            "completion_status": "complete",
            "work_performed": ["x"],
            "open_items": [],
            "quality_assessment": "pass",
            "next_steps": "none",
        })


class TestS4EmitTraceEvent:
    """PB-1: 全 Inner ノードの execute() で emit_trace_event が呼ばれること。"""

    def test_field_log_parser_emits_on_success(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode(llm=MockLLM())
        state = {"user_input": "", "status": None, "field_log": "Installed antenna.", "work_type": "base_station_installation", "measurements": None, "error_code": None}
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            node.execute(state)
        assert mock_emit.call_count >= 1
        assert any("field_log_parsed" in str(c) for c in mock_emit.call_args_list)

    def test_completion_validator_emits_on_success(self):
        from src.nodes.completion_validator_node import CompletionValidatorNode
        node = CompletionValidatorNode()
        actions = json.dumps([{"action_type": "inspect"}, {"action_type": "install"}, {"action_type": "configure"}, {"action_type": "test"}])
        state = {"status": None, "work_type": "base_station_installation", "parsed_actions": actions, "parse_confidence": "0.9", "error_code": None}
        with patch("src.nodes.completion_validator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        assert mock_emit.call_count >= 1
        assert any("completion_validated" in str(c) for c in mock_emit.call_args_list)

    def test_open_item_flag_emits_on_success(self):
        from src.nodes.open_item_flag_node import OpenItemFlagNode
        node = OpenItemFlagNode()
        state = {"status": None, "validation_results": json.dumps({"site_survey": "fail"}), "completion_status": "incomplete", "error_code": None}
        with patch("src.nodes.open_item_flag_node.emit_trace_event") as mock_emit:
            node.execute(state)
        assert mock_emit.call_count >= 1
        assert any("open_items_flagged" in str(c) for c in mock_emit.call_args_list)

    def test_summary_generator_emits_on_success(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode(llm=MockSummaryLLM())
        actions = json.dumps([{"action_type": "install", "description": "x"}])
        state = {
            "status": None, "work_order_id": "WO-1", "work_type": "base_station_installation",
            "parsed_actions": actions, "validation_results": json.dumps({"x": "pass"}),
            "completion_status": "complete", "open_items": "[]", "error_code": None,
        }
        with patch("src.nodes.summary_generator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        assert mock_emit.call_count >= 1
        assert any("summary_generated" in str(c) for c in mock_emit.call_args_list)
