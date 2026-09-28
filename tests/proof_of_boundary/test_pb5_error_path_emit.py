# PB-5: S-4 エラーパス emit — エラー終了時にも emit_trace_event が呼ばれること

from unittest.mock import patch

from framework.schemas.agent_status import AgentStatus


class TestErrorPathEmit:
    """PB-5: エラーパスでも emit_trace_event が呼ばれること（S-4）。"""

    def test_field_log_parser_emits_on_missing_field_log(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {"user_input": "", "status": None, "field_log": None, "work_type": "base_station_installation", "measurements": None, "error_code": None}
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert mock_emit.call_count >= 1
        assert any("field_log_parser_error" in str(c) for c in mock_emit.call_args_list)

    def test_field_log_parser_emits_on_unknown_work_type(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {"user_input": "", "status": None, "field_log": "Some log.", "work_type": "invalid_xyz", "measurements": None, "error_code": None}
        with patch("src.nodes.field_log_parser_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert mock_emit.call_count >= 1

    def test_completion_validator_emits_on_missing_parsed_actions(self):
        from src.nodes.completion_validator_node import CompletionValidatorNode
        node = CompletionValidatorNode()
        state = {"status": None, "work_type": "base_station_installation", "parsed_actions": None, "parse_confidence": "0.9", "error_code": None}
        with patch("src.nodes.completion_validator_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert mock_emit.call_count >= 1
        assert any("completion_validator_error" in str(c) for c in mock_emit.call_args_list)

    def test_open_item_flag_emits_on_missing_validation_results(self):
        from src.nodes.open_item_flag_node import OpenItemFlagNode
        node = OpenItemFlagNode()
        state = {"status": None, "validation_results": None, "completion_status": "incomplete", "error_code": None}
        with patch("src.nodes.open_item_flag_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert mock_emit.call_count >= 1
        assert any("open_item_flag_error" in str(c) for c in mock_emit.call_args_list)

    def test_summary_generator_emits_on_missing_parsed_actions(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode()
        state = {
            "status": None, "work_order_id": "WO-1", "work_type": "base_station_installation",
            "parsed_actions": None, "validation_results": "{}", "completion_status": "complete",
            "open_items": "[]", "error_code": None,
        }
        with patch("src.nodes.summary_generator_node.emit_trace_event") as mock_emit:
            result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert mock_emit.call_count >= 1
        assert any("summary_generator_error" in str(c) for c in mock_emit.call_args_list)
