"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects
# cause silent corruption.  Extend AgentState with agent-specific
# fields only.  Do NOT add credentials, secrets, or Pydantic models.

from typing import Optional

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for TEL-C2-023 field log summarization and completion validation.

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState.
    Lists/dicts are stored as JSON strings (msgpack incompatibility).
    """

    # ── Inputs ────────────────────────────────────────────────
    work_order_id: Optional[str]
    work_type: Optional[str]
    field_log: Optional[str]
    measurements: Optional[str]  # JSON string: {"vswr": 1.38, ...}

    # ── FieldLogParserNode outputs ────────────────────────────
    parsed_actions: Optional[str]  # JSON string: list of structured actions
    extracted_measurements: Optional[str]  # JSON string: standardized measurements
    parse_confidence: Optional[str]  # float as string (e.g. "0.85")

    # ── CompletionValidatorNode outputs ──────────────────────
    validation_results: Optional[str]  # JSON string: {item: "pass"|"fail"|"review"}
    completion_status: Optional[str]  # "complete" | "partial" | "incomplete"

    # ── OpenItemFlagNode outputs ──────────────────────────────
    open_items: Optional[str]  # JSON string: [{item, urgency, action}, ...]

    # ── SummaryGeneratorNode outputs ─────────────────────────
    completion_report: Optional[str]  # JSON string: ITSM-ready summary
    audit_log: Optional[str]  # JSON string: {work_order_id, timestamp, ...}

    # ── Error handling ────────────────────────────────────────
    error_code: Optional[str]
    # MISSING_FIELD / UNKNOWN_WORK_TYPE / LOW_CONFIDENCE / S3_BLOCKED
