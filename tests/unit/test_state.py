"""Unit tests for TEL-C2-023 State schema."""

import ast
import os


STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "src", "schemas", "state.py")


class TestStateSchema:
    """State must inherit AgentState and declare all required fields."""

    def test_state_inherits_agent_state(self):
        """State class must inherit AgentState (verified via AST)."""
        with open(STATE_FILE) as f:
            tree = ast.parse(f.read())

        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != "State":
                continue
            for base in node.bases:
                name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                if name == "AgentState":
                    found = True
        assert found, "State must inherit AgentState"

    def test_required_input_fields_declared(self):
        """All required input fields must be declared in State."""
        required = {"work_order_id", "work_type", "field_log", "measurements"}
        declared = _get_state_fields()
        missing = required - declared
        assert not missing, f"Missing input fields in State: {missing}"

    def test_parser_output_fields_declared(self):
        """FieldLogParserNode output fields must be declared."""
        required = {"parsed_actions", "extracted_measurements", "parse_confidence"}
        declared = _get_state_fields()
        missing = required - declared
        assert not missing, f"Missing parser output fields: {missing}"

    def test_validator_output_fields_declared(self):
        """CompletionValidatorNode output fields must be declared."""
        required = {"validation_results", "completion_status"}
        declared = _get_state_fields()
        missing = required - declared
        assert not missing, f"Missing validator output fields: {missing}"

    def test_downstream_output_fields_declared(self):
        """OpenItemFlagNode and SummaryGeneratorNode output fields must be declared."""
        required = {"open_items", "completion_report", "audit_log"}
        declared = _get_state_fields()
        missing = required - declared
        assert not missing, f"Missing downstream output fields: {missing}"

    def test_error_code_field_declared(self):
        """error_code must be declared."""
        assert "error_code" in _get_state_fields()

    def test_no_non_optional_fields(self):
        """All agent-specific fields must be Optional to allow partial state."""
        with open(STATE_FILE) as f:
            tree = ast.parse(f.read())

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != "State":
                continue
            for item in node.body:
                if not isinstance(item, ast.AnnAssign):
                    continue
                ann = item.annotation
                # Check if annotation is Optional (Subscript with Optional)
                is_optional = (
                    isinstance(ann, ast.Subscript)
                    and isinstance(ann.value, ast.Name)
                    and ann.value.id == "Optional"
                )
                if not is_optional:
                    field = item.target.id if isinstance(item.target, ast.Name) else "?"
                    violations.append(field)
        assert not violations, f"Non-Optional fields found in State: {violations}"


def _get_state_fields() -> set:
    with open(STATE_FILE) as f:
        tree = ast.parse(f.read())
    fields = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "State":
            continue
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.add(item.target.id)
    return fields
