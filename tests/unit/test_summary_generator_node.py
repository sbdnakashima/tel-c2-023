"""Unit tests for SummaryGeneratorNode"""

import json
from unittest.mock import patch

import pytest

from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus
from src.nodes.summary_generator_node import SummaryGeneratorNode


class MockLLM:
    def __init__(self, response: str):
        self._response = response

    def complete(self, messages):
        return self._response


def _valid_report_response() -> str:
    return json.dumps({
        "executive_summary": "Base station installation completed successfully. All required steps were performed and signal tests passed.",
        "completion_status": "complete",
        "work_performed": ["Installed antenna", "Configured settings", "Tested signal"],
        "open_items": [],
        "quality_assessment": "pass",
        "next_steps": "none",
    })


def _base_actions() -> str:
    return json.dumps([
        {"sequence": 1, "action_type": "install", "description": "Installed antenna", "component": "antenna", "result": "success"},
        {"sequence": 2, "action_type": "configure", "description": "Configured settings", "component": "radio", "result": "success"},
        {"sequence": 3, "action_type": "test", "description": "Tested signal", "component": "antenna", "result": "success"},
    ])


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "",
        "status": None,
        "work_order_id": "WO-12345",
        "work_type": "base_station_installation",
        "parsed_actions": _base_actions(),
        "validation_results": json.dumps({"site_survey": "pass", "installation": "pass", "signal_test": "pass"}),
        "completion_status": "complete",
        "open_items": "[]",
        "completion_report": None,
        "audit_log": None,
        "error_code": None,
        **kwargs,
    }


class TestSummaryGeneratorNodeSuccess:

    def test_returns_success_status(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_completion_report_is_json_string(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        result = node.execute(_base_state())
        report = json.loads(result["completion_report"])
        assert isinstance(report, dict)
        assert "executive_summary" in report
        assert "completion_status" in report

    def test_audit_log_is_json_string(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        result = node.execute(_base_state())
        audit = json.loads(result["audit_log"])
        assert audit["work_order_id"] == "WO-12345"
        assert audit["work_type"] == "base_station_installation"
        assert audit["completion_status"] == "complete"
        assert "timestamp" in audit

    def test_audit_log_includes_counts(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(open_items=json.dumps([{"item": "documentation", "status": "review"}]))
        result = node.execute(state)
        audit = json.loads(result["audit_log"])
        assert audit["open_item_count"] == 1
        assert audit["action_count"] == 3

    def test_llm_invalid_json_falls_back_gracefully(self):
        node = SummaryGeneratorNode(llm=MockLLM("Not JSON at all"))
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        report = json.loads(result["completion_report"])
        assert report["quality_assessment"] == "requires_review"

    def test_invalid_open_items_json_uses_empty_list(self):
        """open_items が不正 JSON でもクラッシュしない"""
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(open_items="{bad json")
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value


class TestSummaryGeneratorNodeErrors:

    def test_missing_parsed_actions_returns_error(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(parsed_actions=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_PARSED_ACTIONS"

    def test_empty_parsed_actions_returns_error(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(parsed_actions="")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_PARSED_ACTIONS"

    def test_missing_validation_results_returns_error(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(validation_results=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_VALIDATION_RESULTS"

    def test_invalid_parsed_actions_json_returns_error(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(parsed_actions="{bad json")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "INVALID_PARSED_ACTIONS"

    def test_llm_exception_returns_error(self):
        class ExplodingLLM:
            def complete(self, messages):
                raise RuntimeError("LLM timeout")

        node = SummaryGeneratorNode(llm=ExplodingLLM())
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "GENERATE_ERROR"


class TestSummaryGeneratorNodeS3Gate:

    def test_technician_pii_in_report_raises(self):
        node = SummaryGeneratorNode()
        state = _base_state(
            completion_report='{"executive_summary": "Engineer TECH-ABC123 completed work."}'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_customer_address_in_report_raises(self):
        node = SummaryGeneratorNode()
        state = _base_state(
            completion_report='{"executive_summary": "Work at 100-0001 completed."}'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_equipment_serial_in_report_raises(self):
        node = SummaryGeneratorNode()
        state = _base_state(
            completion_report='{"note": "Replaced unit SN-ABCDEF123"}'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_clean_output_passes_gate(self):
        node = SummaryGeneratorNode()
        state = _base_state(
            completion_report='{"executive_summary": "Installation completed successfully."}'
        )
        result = node._extra_security_gate_output(state)
        assert result is state


class TestSummaryGeneratorNodeS4Emit:

    def test_emit_called_on_success(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        with patch("src.nodes.summary_generator_node.emit_trace_event") as mock_emit:
            node.execute(_base_state())
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "summary_generated" in event_names

    def test_emit_called_on_missing_parsed_actions(self):
        node = SummaryGeneratorNode(llm=MockLLM(_valid_report_response()))
        state = _base_state(parsed_actions=None)
        with patch("src.nodes.summary_generator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "summary_generator_error" in event_names

    def test_emit_called_on_llm_exception(self):
        class ExplodingLLM:
            def complete(self, messages):
                raise RuntimeError("timeout")

        node = SummaryGeneratorNode(llm=ExplodingLLM())
        with patch("src.nodes.summary_generator_node.emit_trace_event") as mock_emit:
            node.execute(_base_state())
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "summary_generator_error" in event_names


class TestSummaryGeneratorNodeS2Gate:

    def test_credential_in_parsed_actions_raises(self):
        node = SummaryGeneratorNode()
        state = _base_state(
            parsed_actions='[{"action_type": "sk-abcdefghijklmnopqrstuvwxyz1234"}]'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_clean_input_passes_gate(self):
        node = SummaryGeneratorNode()
        state = _base_state()
        result = node._extra_security_gate_input(state)
        assert result is state
