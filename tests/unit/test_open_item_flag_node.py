"""Unit tests for OpenItemFlagNode"""

import json
from unittest.mock import patch

import pytest

from framework.errors import SecurityViolationError
from framework.schemas.agent_status import AgentStatus
from src.nodes.open_item_flag_node import OpenItemFlagNode


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "",
        "status": None,
        "validation_results": None,
        "completion_status": "incomplete",
        "open_items": None,
        "error_code": None,
        **kwargs,
    }


def _vr(**statuses) -> str:
    """検証結果の JSON 文字列を生成。キーワード引数で各チェック項目のステータスを指定。"""
    return json.dumps(statuses)


class TestOpenItemFlagNodeSuccess:

    def test_no_open_items_when_all_pass(self):
        """全項目 pass の場合、open_items は空リスト"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(site_survey="pass", installation="pass", configuration="pass"),
            completion_status="complete",
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        items = json.loads(result["open_items"])
        assert items == []

    def test_fail_items_included_in_open_items(self):
        """fail 項目が open_items に含まれる"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(site_survey="pass", installation="fail", signal_test="fail"),
            completion_status="incomplete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        item_keys = {i["item"] for i in items}
        assert "installation" in item_keys
        assert "signal_test" in item_keys
        assert "site_survey" not in item_keys

    def test_review_items_included_in_open_items(self):
        """review 項目も open_items に含まれる"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(documentation="review"),
            completion_status="complete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        assert any(i["item"] == "documentation" for i in items)

    def test_signal_test_fail_gets_high_urgency(self):
        """signal_test の fail は高緊急度"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(signal_test="fail"),
            completion_status="incomplete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        signal_item = next(i for i in items if i["item"] == "signal_test")
        assert signal_item["urgency"] == "high"

    def test_incomplete_status_sets_high_base_urgency(self):
        """completion_status=incomplete は base_urgency=high"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(installation="fail"),
            completion_status="incomplete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        assert items[0]["urgency"] == "high"

    def test_complete_status_sets_low_base_urgency_for_review(self):
        """complete + review 項目は low 緊急度（高緊急キーワードなし）"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(documentation="review"),
            completion_status="complete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        assert items[0]["urgency"] == "low"

    def test_open_items_sorted_by_urgency_desc(self):
        """open_items は緊急度降順でソートされる"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(signal_test="fail", documentation="review"),
            completion_status="partial",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        urgencies = [i["urgency"] for i in items]
        order = {"high": 0, "medium": 1, "low": 2}
        assert urgencies == sorted(urgencies, key=lambda u: order[u])

    def test_open_items_has_recommended_action(self):
        """各 open_item に recommended_action が含まれる"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(installation="fail"),
            completion_status="incomplete",
        )
        result = node.execute(state)
        items = json.loads(result["open_items"])
        assert all("recommended_action" in i for i in items)
        assert all(len(i["recommended_action"]) > 0 for i in items)

    def test_complete_with_no_failures_returns_empty_open_items(self):
        """complete で fail/review なし → open_items が空"""
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results=_vr(site_survey="pass", installation="pass"),
            completion_status="complete",
        )
        result = node.execute(state)
        assert json.loads(result["open_items"]) == []


class TestOpenItemFlagNodeErrors:

    def test_missing_validation_results_returns_error(self):
        node = OpenItemFlagNode()
        state = _base_state(validation_results=None)
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "MISSING_VALIDATION_RESULTS"

    def test_invalid_json_validation_results_returns_error(self):
        node = OpenItemFlagNode()
        state = _base_state(validation_results="{bad json")
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert result["error_code"] == "INVALID_VALIDATION_RESULTS"


class TestOpenItemFlagNodeS4Emit:

    def test_emit_called_on_success(self):
        node = OpenItemFlagNode()
        state = _base_state(validation_results=_vr(installation="fail"))
        with patch("src.nodes.open_item_flag_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "open_items_flagged" in event_names

    def test_emit_called_on_missing_validation_results(self):
        node = OpenItemFlagNode()
        state = _base_state(validation_results=None)
        with patch("src.nodes.open_item_flag_node.emit_trace_event") as mock_emit:
            node.execute(state)
        event_names = [call.args[0] for call in mock_emit.call_args_list]
        assert "open_item_flag_error" in event_names


class TestOpenItemFlagNodeS2Gate:

    def test_credential_in_validation_results_raises(self):
        node = OpenItemFlagNode()
        state = _base_state(
            validation_results='{"key": "AKIAIOSFODNN7EXAMPLE"}'
        )
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_clean_input_passes_gate(self):
        node = OpenItemFlagNode()
        state = _base_state(validation_results=_vr(installation="pass"))
        result = node._extra_security_gate_input(state)
        assert result is state
