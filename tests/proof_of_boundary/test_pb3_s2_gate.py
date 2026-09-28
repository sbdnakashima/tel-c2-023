# PB-3: S-2 credential gate — credential パターンで SecurityViolationError が発生すること

import pytest

from framework.errors import SecurityViolationError


class TestS2CredentialGate:
    """PB-3: S-2 ゲートが credential パターンを検出して SecurityViolationError を raise する。"""

    def test_field_log_parser_s2_rejects_api_key(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {
            "field_log": "Found key sk-abcdefghijklmnopqrstuvwxyz1234 in log",
            "work_type": "base_station_installation",
            "measurements": None,
            "work_order_id": None,
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_field_log_parser_s2_rejects_jwt(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {
            "field_log": "token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
            "work_type": "base_station_installation",
            "measurements": None,
            "work_order_id": None,
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_field_log_parser_s2_rejects_aws_key_in_measurements(self):
        import json
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {
            "field_log": "Normal log entry.",
            "work_type": "base_station_installation",
            "measurements": json.dumps({"key": "AKIAIOSFODNN7EXAMPLE"}),
            "work_order_id": None,
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_input(state)

    def test_clean_input_passes_s2_gate(self):
        from src.nodes.field_log_parser_node import FieldLogParserNode
        node = FieldLogParserNode()
        state = {
            "field_log": "Installed antenna. Signal test passed.",
            "work_type": "base_station_installation",
            "measurements": None,
            "work_order_id": "WO-001",
        }
        result = node._extra_security_gate_input(state)
        assert result is state
