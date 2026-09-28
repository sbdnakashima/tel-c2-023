# PB-4: S-3 output gate — 禁止パターンを含む出力で SecurityViolationError が発生すること

import pytest

from framework.errors import SecurityViolationError


class TestS3OutputGate:
    """PB-4: SummaryGeneratorNode の S-3 ゲートが PII・住所・設備シリアルを検出する。"""

    def test_technician_pii_rejected(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode()
        state = {
            "completion_report": '{"executive_summary": "Work done by TECH-ABC123."}',
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_customer_address_rejected(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode()
        state = {
            "completion_report": '{"executive_summary": "Site at 100-0001 completed."}',
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_equipment_serial_rejected(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode()
        state = {
            "completion_report": '{"note": "Replaced unit SN-ABCDEF123."}',
        }
        with pytest.raises(SecurityViolationError):
            node._extra_security_gate_output(state)

    def test_clean_output_passes_s3_gate(self):
        from src.nodes.summary_generator_node import SummaryGeneratorNode
        node = SummaryGeneratorNode()
        state = {
            "completion_report": '{"executive_summary": "Installation completed successfully."}',
        }
        result = node._extra_security_gate_output(state)
        assert result is state
