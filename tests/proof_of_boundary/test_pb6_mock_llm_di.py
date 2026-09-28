# PB-6: モック LLM DI — API キーなしで execute() が成功すること

import json

from framework.schemas.agent_status import AgentStatus


class _MockParserLLM:
    def complete(self, messages):
        return json.dumps({
            "actions": [{"sequence": 1, "action_type": "install", "description": "Installed", "component": "", "result": "success"}],
            "measurements": {},
            "confidence": 0.85,
            "log_completeness": "complete",
        })


class _MockSummaryLLM:
    def complete(self, messages):
        return json.dumps({
            "executive_summary": "Work completed.",
            "completion_status": "complete",
            "work_performed": ["Installed"],
            "open_items": [],
            "quality_assessment": "pass",
            "next_steps": "none",
        })


class TestMockLLMDI:
    """PB-6: LLM をモック注入して API キーなしで実行できること。"""

    def test_field_log_parser_with_mock_llm(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode(llm=_MockParserLLM())
        state = {
            "user_input": "", "status": None,
            "field_log": "Installed antenna.",
            "work_type": "base_station_installation",
            "measurements": None, "error_code": None,
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["parsed_actions"] is not None
        assert result["parse_confidence"] == "0.85"

    def test_summary_generator_with_mock_llm(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode(llm=_MockSummaryLLM())
        actions = json.dumps([{"action_type": "install", "description": "Installed"}])
        state = {
            "status": None, "work_order_id": "WO-1", "work_type": "base_station_installation",
            "parsed_actions": actions,
            "validation_results": json.dumps({"installation": "pass"}),
            "completion_status": "complete", "open_items": "[]", "error_code": None,
        }
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        report = json.loads(result["completion_report"])
        assert report["quality_assessment"] == "pass"
