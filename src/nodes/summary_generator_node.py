"""SummaryGeneratorNode — ITSM 向けサマリー生成・S-3 出力ゲート・監査ログ記録"""

import json
import re
from datetime import datetime, timezone
from typing import Any

from framework.errors import SecurityViolationError
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_CREDENTIAL_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|eyJ[a-zA-Z0-9._-]{10,}|AKIA[A-Z0-9]{16})",
)

# S-3: 出力禁止パターン（技術者個人情報・顧客住所・設備 ID）
_TECHNICIAN_PII_PATTERN = re.compile(
    r"\b(TECH-[A-Z0-9]{3,}|EMP-\d+|\bemployee_id\b)",
    re.IGNORECASE,
)
_CUSTOMER_ADDRESS_PATTERN = re.compile(
    r"(\d{3}-\d{4}|\b[都道府県市区町村]\S{2,}[0-9-]+丁目|住所[:：]\s*\S)",
)
_EQUIPMENT_SERIAL_PATTERN = re.compile(
    r"\bSN-[A-Z0-9]{6,}\b",
)

_SUMMARY_PROMPT = """\
You are a telecom field engineering ITSM system.
Generate a structured completion report for the work order based on the field log analysis.
Return ONLY valid JSON with this exact structure:
{
  "executive_summary": "<2-3 sentence summary of work performed and outcome>",
  "completion_status": "<complete|partial|incomplete>",
  "work_performed": ["<action 1>", "<action 2>", ...],
  "open_items": ["<item 1>", "<item 2>", ...],
  "quality_assessment": "<pass|requires_review|fail>",
  "next_steps": "<recommended next action, or 'none' if complete>"
}
Do NOT include: technician IDs, customer addresses, equipment serial numbers, internal credentials.
Keep language professional and suitable for ITSM ticketing systems.
Write all free-text values (executive_summary, work_performed, open_items, next_steps) in Japanese.
The enum values (completion_status, quality_assessment) must stay in English exactly as specified above.
"""


class SummaryGeneratorNode(FunctionNode):
    """Inner graph summary_generator スロット: ITSM 向け完了サマリー生成・S-3 ゲート・監査ログ。

    S-3: `_extra_security_gate_output()` — 出力に技術者個人情報・顧客住所・設備 ID が含まれないか検証
    S-4: summary_generated イベントを emit
    """

    required_trust_level = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        for field in ("parsed_actions", "validation_results", "open_items", "work_order_id"):
            val = state.get(field, "") or ""
            if _CREDENTIAL_PATTERN.search(val):
                raise SecurityViolationError(
                    "SummaryGeneratorNode", "no credentials", f"credential pattern detected in {field}"
                )
        return state

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        report_raw = state.get("completion_report", "") or ""
        if _TECHNICIAN_PII_PATTERN.search(report_raw):
            raise SecurityViolationError(
                "SummaryGeneratorNode",
                "no technician PII in output",
                "technician PII pattern found in completion_report",
            )
        if _CUSTOMER_ADDRESS_PATTERN.search(report_raw):
            raise SecurityViolationError(
                "SummaryGeneratorNode",
                "no customer address in output",
                "customer address pattern found in completion_report",
            )
        if _EQUIPMENT_SERIAL_PATTERN.search(report_raw):
            raise SecurityViolationError(
                "SummaryGeneratorNode",
                "no equipment serial in output",
                "equipment serial number found in completion_report",
            )
        return state

    def execute(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed_actions_raw = (state.get("parsed_actions", "") or "").strip()
        validation_results_raw = (state.get("validation_results", "") or "").strip()
        completion_status = (state.get("completion_status", "") or "").strip()
        open_items_raw = (state.get("open_items", "") or "[]").strip()
        work_order_id = (state.get("work_order_id", "") or "").strip()
        work_type = (state.get("work_type", "") or "").strip()

        if not parsed_actions_raw:
            emit_trace_event(
                "summary_generator_error",
                {
                    "node": "SummaryGeneratorNode",
                    "error_code": "MISSING_PARSED_ACTIONS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_PARSED_ACTIONS"}

        if not validation_results_raw:
            emit_trace_event(
                "summary_generator_error",
                {
                    "node": "SummaryGeneratorNode",
                    "error_code": "MISSING_VALIDATION_RESULTS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_VALIDATION_RESULTS"}

        try:
            parsed_actions = json.loads(parsed_actions_raw)
        except json.JSONDecodeError:
            emit_trace_event(
                "summary_generator_error",
                {
                    "node": "SummaryGeneratorNode",
                    "error_code": "INVALID_PARSED_ACTIONS",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "INVALID_PARSED_ACTIONS"}

        try:
            open_items = json.loads(open_items_raw)
        except json.JSONDecodeError:
            open_items = []

        try:
            report_content = self._generate_summary(
                state, parsed_actions, validation_results_raw, completion_status, open_items, work_type
            )
        except Exception as exc:
            emit_trace_event(
                "summary_generator_error",
                {
                    "node": "SummaryGeneratorNode",
                    "error_code": "GENERATE_ERROR",
                    "detail": str(exc),
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "GENERATE_ERROR"}

        audit_log = {
            "work_order_id": work_order_id,
            "work_type": work_type,
            "completion_status": completion_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open_item_count": len(open_items),
            "action_count": len(parsed_actions),
        }

        emit_trace_event(
            "summary_generated",
            {
                "node": "SummaryGeneratorNode",
                "work_order_id": work_order_id,
                "work_type": work_type,
                "completion_status": completion_status,
            },
            state,
        )

        return {
            **state,
            "completion_report": json.dumps(report_content, ensure_ascii=False),
            "audit_log": json.dumps(audit_log, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }

    def _generate_summary(
        self,
        state: dict[str, Any],
        parsed_actions: list[Any],
        validation_results_raw: str,
        completion_status: str,
        open_items: list[Any],
        work_type: str,
    ) -> dict[str, Any]:
        open_item_keys = [i.get("item", "") for i in open_items if isinstance(i, dict)]
        user_content = (
            f"work_type: {work_type}\n"
            f"completion_status: {completion_status}\n"
            f"action_count: {len(parsed_actions)}\n"
            f"validation_results: {validation_results_raw}\n"
            f"open_items: {json.dumps(open_item_keys)}\n"
            f"actions_summary: {json.dumps([a.get('description', '') for a in parsed_actions[:5]])}"
        )

        if self._llm is not None:
            raw = self._llm.complete([{"role": "user", "content": user_content}])
            response_text = raw if isinstance(raw, str) else raw.get("content", "")
        else:
            ctx = InvocationContext.from_state(state)
            from shared.services.llm.azure_openai_client import AzureOpenAIClient

            llm = AzureOpenAIClient(
                config={
                    "api_key": ctx.secrets.require("AZURE_OPENAI_API_KEY"),
                    "azure_endpoint": ctx.secrets.require("AZURE_OPENAI_ENDPOINT"),
                    "azure_deployment": ctx.secrets.require("AZURE_OPENAI_DEPLOYMENT"),
                }
            )
            result = llm.complete(
                [
                    {"role": "system", "content": _SUMMARY_PROMPT},
                    {"role": "user", "content": user_content},
                ]
            )
            response_text = result.get("content", "")

        try:
            parsed: dict[str, Any] = json.loads(response_text)
            return parsed
        except Exception:
            return {
                "executive_summary": f"Work completed with status: {completion_status}.",
                "completion_status": completion_status,
                "work_performed": [a.get("description", "") for a in parsed_actions],
                "open_items": open_item_keys,
                "quality_assessment": "requires_review",
                "next_steps": "Manual review required due to parse failure.",
            }
