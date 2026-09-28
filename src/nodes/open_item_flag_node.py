"""OpenItemFlagNode — Fail/要確認集約・緊急度分類・推奨アクション生成"""

import json
import re
from typing import Any

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_CREDENTIAL_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|eyJ[a-zA-Z0-9._-]{10,}|AKIA[A-Z0-9]{16})",
)

# completion_status → 緊急度マッピング
_STATUS_URGENCY: dict[str, str] = {
    "incomplete": "high",
    "partial": "medium",
    "complete": "low",
}

# チェック項目の key に含まれるキーワードで緊急度を上書きする
_HIGH_URGENCY_KEYWORDS = {"safety", "power", "signal_test", "loss_test", "restoration"}

# 緊急度 → 推奨アクション定義
_URGENCY_ACTIONS: dict[str, str] = {
    "high": "現地エンジニアによる即時フォローアップが必要です。NOC に通知してください。",
    "medium": "次回メンテナンス訪問時に確認・対応してください。",
    "low": "作業記録を確認し、必要に応じて補足情報を追記してください。",
}


class OpenItemFlagNode(FunctionNode):
    """Inner graph open_item_flag スロット: Fail/要確認集約・緊急度分類。

    validation_results の fail/review 項目を集約し、
    completion_status に基づいた緊急度ラベルを付与する。
    LLM 不使用のルールベース実装。

    S-4: open_items_flagged イベントを emit
    """

    required_trust_level = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        for field in ("validation_results", "completion_status"):
            val = state.get(field, "") or ""
            if _CREDENTIAL_PATTERN.search(val):
                raise SecurityViolationError(
                    "OpenItemFlagNode", "no credentials", f"credential pattern detected in {field}"
                )
        return state

    def execute(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        validation_results_raw = (state.get("validation_results", "") or "").strip()
        completion_status = (state.get("completion_status", "") or "").strip()

        if not validation_results_raw:
            emit_trace_event(
                "open_item_flag_error",
                {
                    "node": "OpenItemFlagNode",
                    "error_code": "MISSING_VALIDATION_RESULTS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_VALIDATION_RESULTS"}

        try:
            validation_results = json.loads(validation_results_raw)
        except json.JSONDecodeError:
            emit_trace_event(
                "open_item_flag_error",
                {
                    "node": "OpenItemFlagNode",
                    "error_code": "INVALID_VALIDATION_RESULTS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "INVALID_VALIDATION_RESULTS"}

        base_urgency = _STATUS_URGENCY.get(completion_status, "medium")

        open_items = []
        for key, status in validation_results.items():
            if status not in ("fail", "review"):
                continue

            # 安全・信号等のキーワードを含む場合は緊急度を high に引き上げ
            urgency = "high" if any(kw in key for kw in _HIGH_URGENCY_KEYWORDS) else base_urgency
            if status == "fail" and urgency == "low":
                urgency = "medium"

            open_items.append(
                {
                    "item": key,
                    "status": status,
                    "urgency": urgency,
                    "recommended_action": _URGENCY_ACTIONS[urgency],
                }
            )

        # urgency 降順でソート
        _urgency_order = {"high": 0, "medium": 1, "low": 2}
        open_items.sort(key=lambda x: _urgency_order.get(x["urgency"], 1))

        emit_trace_event(
            "open_items_flagged",
            {
                "node": "OpenItemFlagNode",
                "completion_status": completion_status,
                "open_item_count": len(open_items),
                "high_urgency_count": sum(1 for i in open_items if i["urgency"] == "high"),
            },
            state,
        )

        return {
            **state,
            "open_items": json.dumps(open_items, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }
