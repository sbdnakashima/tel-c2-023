"""Unit tests for CompletionValidatorNode"""

import json
from unittest.mock import patch

import pytest

from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus
from src.nodes.completion_validator_node import CompletionValidatorNode


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "",
        "status": None,
        "work_type": "base_station_installation",
        "parsed_actions": None,
        "extracted_measurements": None,
        "parse_confidence": "0.9",
        "validation_results": None,
        "completion_status": None,
        "error_code": None,
        **kwargs,
    }


def _actions(*action_types) -> str:
    """指定した action_type のアクションリストを JSON 文字列で返す。"""
    return json.dumps([
        {"sequence": i + 1, "action_type": t, "description": t, "component": "", "result": "success"}
        for i, t in enumerate(action_types)
    ])


class TestCompletionValidatorNodeSuccess:

    def test_complete_base_station_installation(self):
        """必須ステップがすべて揃えば complete"""
        node = CompletionValidatorNode()
        state = _base_state(
            parsed_actions=_actions("inspect", "install", "configure", "test"),
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["completion_status"] == "complete"

    def test_incomplete_missing_required_step(self):
        """必須ステップ欠落で incomplete"""
        node = CompletionValidatorNode()
        # install と test のみ — inspect(site_survey) と configure が欠落
        state = _base_state(parsed_actions=_actions("install", "test"))
        result = node.execute(state)
        assert result["completion_status"] == "incomplete"

    def test_partial_low_confidence(self):
        """全ステップ揃っても confidence が低ければ partial"""
        node = CompletionValidatorNode()
        state = _base_state(
            parsed_actions=_actions("inspect", "install", "configure", "test"),
            parse_confidence="0.3",
        )
        result = node.execute(state)
        assert result["completion_status"] == "partial"

    def test_validation_results_is_json_string(self):
        """validation_results が JSON 文字列であること"""
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=_actions("inspect", "install", "configure", "test"))
        result = node.execute(state)
        vr = json.loads(result["validation_results"])
        assert isinstance(vr, dict)
        assert all(v in ("pass", "fail", "review") for v in vr.values())

    def test_validation_results_pass_for_matched_steps(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=_actions("inspect", "install", "configure", "test"))
        result = node.execute(state)
        vr = json.loads(result["validation_results"])
        assert vr["site_survey"] == "pass"
        assert vr["installation"] == "pass"
        assert vr["configuration"] == "pass"
        assert vr["signal_test"] == "pass"

    def test_fiber_splicing_all_required_pass(self):
        node = CompletionValidatorNode()
        state = _base_state(
            work_type="fiber_splicing",
            parsed_actions=_actions("inspect", "install", "test"),
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["completion_status"] == "complete"

    def test_other_work_type_single_action_complete(self):
        node = CompletionValidatorNode()
        state = _base_state(
            work_type="other",
            parsed_actions=_actions("inspect"),
        )
        result = node.execute(state)
        assert result["completion_status"] == "complete"

    def test_invalid_confidence_defaults_to_half(self):
        """parse_confidence が float に変換できない場合でもクラッシュしない"""
        node = CompletionValidatorNode()
        state = _base_state(
            parsed_actions=_actions("inspect", "install", "configure", "test"),
            parse_confidence="not_a_float",
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value


class TestCompletionValidatorNodeErrors:

    def test_missing_parsed_actions_returns_error(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_PARSED_ACTIONS"

    def test_empty_parsed_actions_returns_error(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions="")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_PARSED_ACTIONS"

    def test_invalid_json_parsed_actions_returns_error(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions="{not valid json")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "INVALID_PARSED_ACTIONS"


class TestCompletionValidatorNodeS4Emit:

    def test_emit_called_on_success(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=_actions("inspect", "install", "configure", "test"))
        with patch("src.nodes.completion_validator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "completion_validated" in event_names

    def test_emit_called_on_missing_parsed_actions(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=None)
        with patch("src.nodes.completion_validator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "completion_validator_error" in event_names

    def test_emit_called_on_invalid_json(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions="{bad json")
        with patch("src.nodes.completion_validator_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "completion_validator_error" in event_names


class TestCompletionValidatorNodeS2Gate:

    def test_credential_in_parsed_actions_raises(self):
        node = CompletionValidatorNode()
        state = _base_state(
            parsed_actions='[{"action_type": "sk-abcdefghijklmnopqrstuvwxyz1234"}]'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_clean_input_passes_gate(self):
        node = CompletionValidatorNode()
        state = _base_state(parsed_actions=_actions("inspect"))
        result = node._extra_security_gate_input(state)
        assert result is state
