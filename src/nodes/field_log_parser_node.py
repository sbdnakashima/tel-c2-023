"""FieldLogParserNode — フィールドエンジニア作業ログ S-1/S-2 検証・LLM パース・確信スコア算出"""

import json
import re
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

_VALID_WORK_TYPES = {
    "base_station_installation",
    "fiber_splicing",
    "cpe_provisioning",
    "antenna_alignment",
    "power_system_maintenance",
    "cable_routing",
    "equipment_replacement",
    "signal_testing",
    "site_survey",
    "other",
}

_PARSE_PROMPT = """\
You are a telecom field engineering log parser.
Parse the field engineer's free-text work log and extract structured information.
Return ONLY valid JSON with this exact structure:
{
  "actions": [
    {
      "sequence": <int, order of action>,
      "action_type": "<type: install|test|configure|inspect|repair|replace|other>",
      "description": "<concise description of what was done>",
      "component": "<component involved, if any>",
      "result": "<outcome: success|fail|partial|unknown>"
    }
  ],
  "measurements": {
    "<metric_name>": {
      "value": <numeric value>,
      "unit": "<unit string>",
      "status": "<pass|fail|review>"
    }
  },
  "confidence": <float 0.0-1.0, parsing confidence score>,
  "log_completeness": "<complete|partial|fragmentary>"
}
If measurements are embedded in the log text, extract and standardize them.
If measurements JSON is also provided separately, merge and deduplicate.
Confidence = 1.0 means the log is clear and complete. 0.5 means ambiguous. 0.2 means very fragmentary.
"""


class FieldLogParserNode(FunctionNode):
    """Inner graph field_log_parser スロット: ログ S-1 検証・LLM パース・計測値抽出。

    S-1: 必須フィールド（field_log, work_type）欠損検出・work_type 妥当性確認
    S-2: credential パターン検出（field_log, measurements フィールド）
    S-4: field_log_parsed イベントを emit
    """

    required_trust_level = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        for field in ("field_log", "measurements", "work_order_id"):
            val = state.get(field, "") or ""
            if _CREDENTIAL_PATTERN.search(val):
                raise SecurityViolationError(
                    "FieldLogParserNode", "no credentials", f"credential pattern detected in {field}"
                )
        return state

    def execute(self, state: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        # user_input が JSON ペイロードの場合、フィールドを state に展開する
        user_input = (state.get("user_input", "") or "").strip()
        if user_input.startswith("{"):
            try:
                parsed_input = json.loads(user_input)
                state = {**state, **{k: v for k, v in parsed_input.items() if v is not None}}
            except json.JSONDecodeError:
                pass

        field_log = (state.get("field_log", "") or "").strip()
        work_type = (state.get("work_type", "") or "").strip()
        measurements_raw = (state.get("measurements", "") or "").strip()

        # S-1: 必須フィールド確認
        if not field_log:
            emit_trace_event(
                "field_log_parser_error",
                {
                    "node": "FieldLogParserNode",
                    "error_code": "MISSING_FIELD",
                    "missing": "field_log",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_FIELD"}

        if not work_type:
            emit_trace_event(
                "field_log_parser_error",
                {
                    "node": "FieldLogParserNode",
                    "error_code": "MISSING_FIELD",
                    "missing": "work_type",
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "MISSING_FIELD"}

        if work_type not in _VALID_WORK_TYPES:
            emit_trace_event(
                "field_log_parser_error",
                {
                    "node": "FieldLogParserNode",
                    "error_code": "UNKNOWN_WORK_TYPE",
                    "work_type": work_type,
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "UNKNOWN_WORK_TYPE"}

        # LLM でログをパース
        try:
            parsed = self._parse_log(state, field_log, measurements_raw, work_type)
        except Exception as exc:
            emit_trace_event(
                "field_log_parser_error",
                {
                    "node": "FieldLogParserNode",
                    "error_code": "PARSE_ERROR",
                    "detail": str(exc),
                },
                state,
            )
            return {**state, "status": AgentStatus.ERROR.value, "error_code": "PARSE_ERROR"}

        actions = parsed.get("actions", [])
        measurements = parsed.get("measurements", {})
        confidence = float(parsed.get("confidence", 0.5))

        emit_trace_event(
            "field_log_parsed",
            {
                "node": "FieldLogParserNode",
                "work_type": work_type,
                "action_count": len(actions),
                "confidence": confidence,
                "log_completeness": parsed.get("log_completeness", "unknown"),
            },
            state,
        )

        return {
            **state,
            "parsed_actions": json.dumps(actions, ensure_ascii=False),
            "extracted_measurements": json.dumps(measurements, ensure_ascii=False),
            "parse_confidence": str(confidence),
            "status": AgentStatus.SUCCESS.value,
        }

    def _parse_log(
        self, state: dict[str, Any], field_log: str, measurements_raw: str, work_type: str
    ) -> dict[str, Any]:
        user_content = f"work_type: {work_type}\n\nfield_log:\n{field_log}"
        if measurements_raw:
            user_content += f"\n\nmeasurements (JSON):\n{measurements_raw}"

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
                    {"role": "system", "content": _PARSE_PROMPT},
                    {"role": "user", "content": user_content},
                ]
            )
            response_text = result.get("content", "")

        try:
            parsed: dict[str, Any] = json.loads(response_text)
            return parsed
        except Exception:
            return {
                "actions": [],
                "measurements": {},
                "confidence": 0.3,
                "log_completeness": "fragmentary",
            }
