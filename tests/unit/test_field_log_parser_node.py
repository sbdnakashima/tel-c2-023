"""Unit tests for FieldLogParserNode"""

import json
from unittest.mock import patch

import pytest

from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus
from src.nodes.field_log_parser_node import FieldLogParserNode


class MockLLM:
    """テスト用 LLM スタブ。事前設定したレスポンスを返す。"""

    def __init__(self, response: str):
        self._response = response

    def complete(self, messages):
        return self._response


def _valid_parse_response() -> str:
    return json.dumps({
        "actions": [
            {
                "sequence": 1,
                "action_type": "install",
                "description": "Installed base station antenna at rooftop",
                "component": "antenna",
                "result": "success",
            },
            {
                "sequence": 2,
                "action_type": "test",
                "description": "Checked VSWR value",
                "component": "antenna",
                "result": "success",
            },
        ],
        "measurements": {
            "vswr": {"value": 1.38, "unit": "", "status": "pass"},
            "signal_strength": {"value": -65, "unit": "dBm", "status": "pass"},
        },
        "confidence": 0.92,
        "log_completeness": "complete",
    })


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "",
        "status": None,
        "work_order_id": "WO-12345",
        "work_type": "base_station_installation",
        "field_log": None,
        "measurements": None,
        "parsed_actions": None,
        "extracted_measurements": None,
        "parse_confidence": None,
        "error_code": None,
        **kwargs,
    }


def _valid_log() -> str:
    return (
        "Arrived at site 09:00. Installed antenna on rooftop. "
        "VSWR=1.38, signal strength=-65dBm. All checks passed. "
        "Work completed 11:30."
    )


class TestFieldLogParserNodeSuccess:

    def test_parse_returns_success_status(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log())
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value

    def test_parsed_actions_is_json_string(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log())
        result = node.execute(state)
        actions = json.loads(result["parsed_actions"])
        assert isinstance(actions, list)
        assert len(actions) == 2
        assert actions[0]["action_type"] == "install"

    def test_extracted_measurements_is_json_string(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log())
        result = node.execute(state)
        measurements = json.loads(result["extracted_measurements"])
        assert isinstance(measurements, dict)
        assert "vswr" in measurements
        assert measurements["vswr"]["value"] == 1.38

    def test_parse_confidence_is_string(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log())
        result = node.execute(state)
        confidence = float(result["parse_confidence"])
        assert 0.0 <= confidence <= 1.0
        assert confidence == 0.92

    def test_all_valid_work_types_accepted(self):
        from src.nodes.field_log_parser_node import _VALID_WORK_TYPES
        for wt in _VALID_WORK_TYPES:
            node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
            state = _base_state(field_log=_valid_log(), work_type=wt)
            result = node.execute(state)
            assert result["status"] == AgentStatus.SUCCESS.value, f"work_type={wt} failed"

    def test_measurements_json_passed_to_llm(self):
        """measurements フィールドが LLM プロンプトに含まれることを確認（スタブで検証）"""
        captured = []

        class CapturingLLM:
            def complete(self, messages):
                captured.extend(messages)
                return _valid_parse_response()

        measurements = json.dumps({"vswr": 1.38})
        node = FieldLogParserNode(llm=CapturingLLM())
        state = _base_state(field_log=_valid_log(), measurements=measurements)
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        combined = " ".join(m.get("content", "") for m in captured)
        assert "measurements" in combined


class TestFieldLogParserNodeErrors:

    def test_missing_field_log_returns_error(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_FIELD"

    def test_empty_field_log_returns_error(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log="")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_FIELD"

    def test_missing_work_type_returns_error(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log(), work_type=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_FIELD"

    def test_unknown_work_type_returns_error(self):
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log(), work_type="unknown_xyz_type")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "UNKNOWN_WORK_TYPE"

    def test_llm_invalid_json_falls_back_gracefully(self):
        """LLM が JSON ではない応答を返してもクラッシュしない"""
        node = FieldLogParserNode(llm=MockLLM("This is not JSON at all"))
        state = _base_state(field_log=_valid_log())
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["parsed_actions"] == "[]"
        assert float(result["parse_confidence"]) == 0.3


class TestFieldLogParserNodeS4Emit:

    def test_emit_called_on_success(self):
        """execute() が成功時に emit_trace_event を呼ぶこと（S-4）"""
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log())
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "field_log_parsed" in event_names

    def test_emit_called_on_missing_field_log(self):
        """必須フィールド欠損エラー時にも emit_trace_event を呼ぶこと（S-4）"""
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=None)
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "field_log_parser_error" in event_names

    def test_emit_called_on_unknown_work_type(self):
        """未知の work_type エラー時にも emit_trace_event を呼ぶこと（S-4）"""
        node = FieldLogParserNode(llm=MockLLM(_valid_parse_response()))
        state = _base_state(field_log=_valid_log(), work_type="invalid_type")
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "field_log_parser_error" in event_names

    def test_emit_called_on_llm_exception(self):
        """LLM 例外発生時にも emit_trace_event を呼ぶこと（S-4）"""
        class ExplodingLLM:
            def complete(self, messages):
                raise RuntimeError("LLM API timeout")

        node = FieldLogParserNode(llm=ExplodingLLM())
        state = _base_state(field_log=_valid_log())
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "PARSE_ERROR"
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "field_log_parser_error" in event_names


class TestFieldLogParserNodeS2Gate:

    def test_credential_in_field_log_raises(self):
        node = FieldLogParserNode()
        state = _base_state(
            field_log="API key: sk-abcdefghijklmnopqrstuvwxyz1234 found in log"
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_jwt_in_field_log_raises(self):
        node = FieldLogParserNode()
        state = _base_state(
            field_log="token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_aws_key_in_measurements_raises(self):
        node = FieldLogParserNode()
        state = _base_state(
            field_log=_valid_log(),
            measurements='{"key": "AKIAIOSFODNN7EXAMPLE"}',
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_clean_input_passes_gate(self):
        node = FieldLogParserNode()
        state = _base_state(field_log=_valid_log())
        result = node._extra_security_gate_input(state)
        assert result is state
