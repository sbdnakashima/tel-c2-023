"""CompletionValidatorNode — 作業種別別完了基準チェック・閾値判定・欠落ステップ検出"""

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

# 作業種別別完了チェックリスト
# 各エントリは {"key": str, "description": str, "required": bool, "action_types": list[str]}
# action_types に合致するアクションが parsed_actions に存在すれば Pass
_WORK_TYPE_CHECKLIST: dict[str, list[dict[str, Any]]] = {
    "base_station_installation": [
        {
            "key": "site_survey",
            "description": "Site survey / 現地確認",
            "required": True,
            "action_types": ["inspect", "survey"],
        },
        {"key": "installation", "description": "物理設置", "required": True, "action_types": ["install"]},
        {"key": "configuration", "description": "設定投入", "required": True, "action_types": ["configure"]},
        {"key": "signal_test", "description": "信号・疎通テスト", "required": True, "action_types": ["test"]},
        {"key": "documentation", "description": "作業完了記録", "required": False, "action_types": ["other"]},
    ],
    "fiber_splicing": [
        {"key": "cable_prep", "description": "ケーブル前処理", "required": True, "action_types": ["inspect", "other"]},
        {"key": "splicing", "description": "融着接続", "required": True, "action_types": ["install", "repair"]},
        {"key": "loss_test", "description": "損失測定", "required": True, "action_types": ["test"]},
        {"key": "protection", "description": "スリーブ保護", "required": True, "action_types": ["install", "other"]},
    ],
    "cpe_provisioning": [
        {"key": "unboxing", "description": "開梱・外観確認", "required": True, "action_types": ["inspect"]},
        {"key": "physical_install", "description": "物理接続", "required": True, "action_types": ["install"]},
        {"key": "provisioning", "description": "プロビジョニング", "required": True, "action_types": ["configure"]},
        {"key": "connectivity_test", "description": "接続確認", "required": True, "action_types": ["test"]},
        {"key": "customer_handover", "description": "顧客説明・引渡し", "required": False, "action_types": ["other"]},
    ],
    "antenna_alignment": [
        {"key": "initial_check", "description": "初期状態確認", "required": True, "action_types": ["inspect"]},
        {"key": "alignment", "description": "方向調整", "required": True, "action_types": ["configure", "repair"]},
        {"key": "signal_verification", "description": "信号品質確認", "required": True, "action_types": ["test"]},
    ],
    "power_system_maintenance": [
        {"key": "safety_check", "description": "安全確認・停電作業", "required": True, "action_types": ["inspect"]},
        {
            "key": "maintenance",
            "description": "保守・交換作業",
            "required": True,
            "action_types": ["repair", "replace"],
        },
        {"key": "restoration", "description": "電源復旧確認", "required": True, "action_types": ["test"]},
    ],
    "cable_routing": [
        {"key": "route_plan", "description": "ルート確認", "required": True, "action_types": ["inspect"]},
        {"key": "routing", "description": "ケーブル布設", "required": True, "action_types": ["install"]},
        {"key": "labeling", "description": "ラベリング・整理", "required": False, "action_types": ["other"]},
        {"key": "continuity_test", "description": "導通確認", "required": True, "action_types": ["test"]},
    ],
    "equipment_replacement": [
        {"key": "fault_confirm", "description": "故障確認", "required": True, "action_types": ["inspect"]},
        {"key": "removal", "description": "旧機器撤去", "required": True, "action_types": ["other", "replace"]},
        {"key": "replacement", "description": "新機器設置", "required": True, "action_types": ["install", "replace"]},
        {"key": "functional_test", "description": "動作確認", "required": True, "action_types": ["test"]},
    ],
    "signal_testing": [
        {"key": "pre_check", "description": "事前状態確認", "required": True, "action_types": ["inspect"]},
        {"key": "measurement", "description": "計測実施", "required": True, "action_types": ["test"]},
        {"key": "analysis", "description": "結果分析", "required": False, "action_types": ["other"]},
    ],
    "site_survey": [
        {"key": "physical_survey", "description": "現地踏査", "required": True, "action_types": ["inspect"]},
        {"key": "measurements_taken", "description": "計測データ取得", "required": True, "action_types": ["test"]},
        {"key": "report", "description": "調査報告", "required": False, "action_types": ["other"]},
    ],
    "other": [
        {
            "key": "work_performed",
            "description": "何らかの作業実施",
            "required": True,
            "action_types": ["install", "inspect", "configure", "test", "repair", "replace", "other"],
        },
    ],
}

# 確信スコア閾値: これ未満なら completion_status に requires_review フラグを付与
_LOW_CONFIDENCE_THRESHOLD = 0.5


class CompletionValidatorNode(FunctionNode):
    """Inner graph completion_validator スロット: 作業種別別完了基準チェック。

    ルールベース（LLM 不使用）。parsed_actions のアクション種別と
    work_type 別チェックリストを照合して completion_status を決定する。

    S-1: 必須フィールド（parsed_actions, work_type）の欠損確認（フレームワーク gate で実施）
    S-4: completion_validated イベントを emit
    """

    required_trust_level = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        for field in ("parsed_actions", "work_type"):
            val = state.get(field, "") or ""
            if _CREDENTIAL_PATTERN.search(val):
                raise SecurityViolationError(
                    "CompletionValidatorNode", "no credentials", f"credential pattern detected in {field}"
                )
        return state

    def execute(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_actions_raw = (state.get("parsed_actions", "") or "").strip()
        work_type = (state.get("work_type", "") or "").strip()
        parse_confidence_raw = (state.get("parse_confidence", "") or "0.5").strip()

        if not parsed_actions_raw:
            emit_trace_event(
                "completion_validator_error",
                {
                    "node": "CompletionValidatorNode",
                    "error_code": "MISSING_PARSED_ACTIONS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_PARSED_ACTIONS"}

        try:
            actions = json.loads(parsed_actions_raw)
        except json.JSONDecodeError:
            emit_trace_event(
                "completion_validator_error",
                {
                    "node": "CompletionValidatorNode",
                    "error_code": "INVALID_PARSED_ACTIONS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "INVALID_PARSED_ACTIONS"}

        try:
            confidence = float(parse_confidence_raw)
        except (ValueError, TypeError):
            confidence = 0.5

        checklist = _WORK_TYPE_CHECKLIST.get(work_type, _WORK_TYPE_CHECKLIST["other"])
        observed_types = {a.get("action_type", "") for a in actions if isinstance(a, dict)}

        results = {}
        for item in checklist:
            matched = bool(observed_types & set(item["action_types"]))
            results[item["key"]] = "pass" if matched else ("fail" if item["required"] else "review")

        required_fails = [k for k, v in results.items() if v == "fail"]

        if required_fails:
            completion_status = "incomplete"
        elif confidence < _LOW_CONFIDENCE_THRESHOLD:
            completion_status = "partial"
        else:
            completion_status = "complete"

        emit_trace_event(
            "completion_validated",
            {
                "node": "CompletionValidatorNode",
                "work_type": work_type,
                "completion_status": completion_status,
                "required_fails": required_fails,
                "confidence": confidence,
            },
            state,
        )

        return {
            **state,
            "validation_results": json.dumps(results, ensure_ascii=False),
            "completion_status": completion_status,
            "status": AgentStatus.SUCCESS.value,
        }
