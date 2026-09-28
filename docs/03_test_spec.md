# Test Specification — TEL-C2-023

## Overview

| Item | Value |
|---|---|
| Template | TEL-C2-023 |
| Agent Name | Telecom Field Engineer Work Log Summarization & Completion Validation Agent |
| Category | Cat 2 (Outer AgentBaseGraph + Inner BaseGraph 4-node pipeline) |
| Test Framework | pytest |

## Test Scope

| Layer | File | Count |
|---|---|---|
| Unit — State schema | `tests/unit/test_state.py` | 7 |
| Unit — FieldLogParserNode | `tests/unit/test_field_log_parser_node.py` | 19 |
| Unit — CompletionValidatorNode | `tests/unit/test_completion_validator_node.py` | 16 |
| Unit — OpenItemFlagNode | `tests/unit/test_open_item_flag_node.py` | 15 |
| Unit — SummaryGeneratorNode | `tests/unit/test_summary_generator_node.py` | 20 |
| Integration — Graph | `tests/integration/test_graph.py` | 7 |
| Proof-of-Boundary | `tests/proof_of_boundary/` | 11 (PB-1〜PB-7, 1 SKIP) |
| **Total** | | **95 (94 PASS + 1 SKIP expected)** |

---

## Unit Test Cases

### TC-01: State schema（test_state.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| TC-01-01 | State が AgentState を継承する | AST 解析で AgentState 継承を確認 |
| TC-01-02 | 入力フィールド（work_order_id, work_type, field_log, measurements）が宣言される | 全フィールド存在 |
| TC-01-03 | FieldLogParserNode 出力フィールドが宣言される | parsed_actions, extracted_measurements, parse_confidence 存在 |
| TC-01-04 | CompletionValidatorNode 出力フィールドが宣言される | validation_results, completion_status 存在 |
| TC-01-05 | OpenItemFlagNode・SummaryGeneratorNode 出力フィールドが宣言される | open_items, completion_report, audit_log 存在 |
| TC-01-06 | error_code フィールドが宣言される | error_code 存在 |
| TC-01-07 | 全フィールドが Optional[str] 型である | 非 Optional フィールドなし |

### TC-02: FieldLogParserNode（test_field_log_parser_node.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| TC-02-01 | 正常系: status=success | AgentStatus.SUCCESS |
| TC-02-02 | parsed_actions が JSON 文字列で返る | list 型 |
| TC-02-03 | extracted_measurements が JSON 文字列で返る | dict 型 |
| TC-02-04 | parse_confidence が float 文字列で返る | 0.0〜1.0 |
| TC-02-05 | 全 valid work_type で成功する | 全 10 種で SUCCESS |
| TC-02-06 | measurements JSON が LLM プロンプトに含まれる | captured messages に含まれる |
| TC-02-07 | field_log=None で MISSING_FIELD エラー | ERROR / MISSING_FIELD |
| TC-02-08 | field_log="" で MISSING_FIELD エラー | ERROR / MISSING_FIELD |
| TC-02-09 | work_type=None で MISSING_FIELD エラー | ERROR / MISSING_FIELD |
| TC-02-10 | 未知 work_type で UNKNOWN_WORK_TYPE エラー | ERROR / UNKNOWN_WORK_TYPE |
| TC-02-11 | LLM が非 JSON を返しても graceful fallback | SUCCESS / confidence=0.3 |
| TC-02-12 | success 時に emit_trace_event("field_log_parsed") が呼ばれる | S-4 確認 |
| TC-02-13 | MISSING_FIELD 時に emit_trace_event("field_log_parser_error") が呼ばれる | S-4 確認 |
| TC-02-14 | UNKNOWN_WORK_TYPE 時に emit_trace_event("field_log_parser_error") が呼ばれる | S-4 確認 |
| TC-02-15 | LLM 例外時に emit_trace_event("field_log_parser_error") が呼ばれる + ERROR | S-4 確認 |
| TC-02-16 | field_log に credential パターンで SecurityViolationError | S-2 確認 |
| TC-02-17 | field_log に JWT パターンで SecurityViolationError | S-2 確認 |
| TC-02-18 | measurements に AWS キーで SecurityViolationError | S-2 確認 |
| TC-02-19 | クリーンな入力で gate 通過 | state を返す |

### TC-03: CompletionValidatorNode（test_completion_validator_node.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| TC-03-01 | 全必須ステップ揃いで complete | completion_status=complete |
| TC-03-02 | 必須ステップ欠落で incomplete | completion_status=incomplete |
| TC-03-03 | 全ステップ揃い + confidence<0.5 で partial | completion_status=partial |
| TC-03-04 | validation_results が JSON 文字列 | dict 型 / pass・fail・review のみ |
| TC-03-05 | 合致ステップが pass になる | 各 key=pass |
| TC-03-06 | fiber_splicing 全必須ステップで complete | SUCCESS |
| TC-03-07 | work_type=other の単一アクションで complete | SUCCESS |
| TC-03-08 | parse_confidence が float に変換できない場合も動作する | SUCCESS |
| TC-03-09 | parsed_actions=None で MISSING_PARSED_ACTIONS | ERROR |
| TC-03-10 | parsed_actions="" で MISSING_PARSED_ACTIONS | ERROR |
| TC-03-11 | 不正 JSON で INVALID_PARSED_ACTIONS | ERROR |
| TC-03-12 | success 時に emit_trace_event("completion_validated") が呼ばれる | S-4 確認 |
| TC-03-13 | MISSING_PARSED_ACTIONS 時に emit_trace_event が呼ばれる | S-4 確認 |
| TC-03-14 | 不正 JSON 時に emit_trace_event が呼ばれる | S-4 確認 |
| TC-03-15 | credential パターンで SecurityViolationError | S-2 確認 |
| TC-03-16 | クリーンな入力で gate 通過 | state を返す |

### TC-04: OpenItemFlagNode（test_open_item_flag_node.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| TC-04-01 | 全 pass で open_items が空リスト | [] |
| TC-04-02 | fail 項目が open_items に含まれる | item_keys に fail 項目 |
| TC-04-03 | review 項目が open_items に含まれる | item_keys に review 項目 |
| TC-04-04 | signal_test fail は high urgency | urgency=high |
| TC-04-05 | completion_status=incomplete は base high urgency | urgency=high |
| TC-04-06 | complete + review で low urgency（非高緊急キーワード）| urgency=low |
| TC-04-07 | open_items が緊急度降順でソートされる | high→medium→low 順 |
| TC-04-08 | recommended_action が各 item に含まれる | 非空文字列 |
| TC-04-09 | complete + fail なし → empty open_items | [] |
| TC-04-10 | validation_results=None で MISSING_VALIDATION_RESULTS | ERROR |
| TC-04-11 | 不正 JSON で INVALID_VALIDATION_RESULTS | ERROR |
| TC-04-12 | success 時に emit_trace_event("open_items_flagged") が呼ばれる | S-4 確認 |
| TC-04-13 | MISSING 時に emit_trace_event("open_item_flag_error") が呼ばれる | S-4 確認 |
| TC-04-14 | credential パターンで SecurityViolationError | S-2 確認 |
| TC-04-15 | クリーンな入力で gate 通過 | state を返す |

### TC-05: SummaryGeneratorNode（test_summary_generator_node.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| TC-05-01 | 正常系: status=success | SUCCESS |
| TC-05-02 | completion_report が JSON 文字列 | dict 型 / executive_summary 含む |
| TC-05-03 | audit_log が JSON 文字列（work_order_id・timestamp 含む）| dict 型 |
| TC-05-04 | audit_log に open_item_count・action_count 含む | int 値 |
| TC-05-05 | LLM が非 JSON を返しても graceful fallback | SUCCESS / quality_assessment=requires_review |
| TC-05-06 | open_items 不正 JSON でもクラッシュしない | SUCCESS |
| TC-05-07 | parsed_actions=None で MISSING_PARSED_ACTIONS | ERROR |
| TC-05-08 | parsed_actions="" で MISSING_PARSED_ACTIONS | ERROR |
| TC-05-09 | validation_results=None で MISSING_VALIDATION_RESULTS | ERROR |
| TC-05-10 | 不正 JSON で INVALID_PARSED_ACTIONS | ERROR |
| TC-05-11 | LLM 例外で GENERATE_ERROR | ERROR |
| TC-05-12 | completion_report に TECH-XXX で SecurityViolationError | S-3 確認 |
| TC-05-13 | completion_report に郵便番号で SecurityViolationError | S-3 確認 |
| TC-05-14 | completion_report に SN-XXX で SecurityViolationError | S-3 確認 |
| TC-05-15 | クリーンな出力で S-3 gate 通過 | state を返す |
| TC-05-16 | success 時に emit_trace_event("summary_generated") が呼ばれる | S-4 確認 |
| TC-05-17 | MISSING_PARSED_ACTIONS 時に emit_trace_event が呼ばれる | S-4 確認 |
| TC-05-18 | LLM 例外時に emit_trace_event が呼ばれる | S-4 確認 |
| TC-05-19 | parsed_actions に credential で SecurityViolationError | S-2 確認 |
| TC-05-20 | クリーンな入力で S-2 gate 通過 | state を返す |

---

## Integration Test Cases（test_graph.py）

| ID | 内容 | 期待結果 |
|---|---|---|
| IT-01 | 正常系フル invoke → status=success | SUCCESS |
| IT-02 | completion_report が output に含まれる | dict / executive_summary 含む |
| IT-03 | audit_log が output に含まれる | dict / completion_status・timestamp 含む |
| IT-04 | completion_status が output に含まれる | complete / partial / incomplete のいずれか |
| IT-05 | node_history に全 Outer ノードが記録される | InitializeNode・PassThroughNode・FinalizeNode |
| IT-06 | field_log 欠損 → error | ERROR |
| IT-07 | 未知 work_type → error | ERROR |

---

## Proof-of-Boundary Test Cases

| PB | 内容 | ファイル | 対象ノード | 期待結果 |
|---|---|---|---|---|
| PB-1 | S-4: execute() 内で emit_trace_event が 1 回以上呼ばれる | `test_pb1_s4_emit.py` | 全 Inner ノード | emit 呼び出しを mock.patch で確認 |
| PB-2 | S-1: required_trust_level = VERIFIED_EXTERNAL が宣言される | `test_pb2_trust_level.py` | 全ノード | 属性値を AST または実行時チェック |
| PB-2/PB-5 | State が msgpack 安全（PII・禁止型なし） | `test_state_safety.py` | State schema | credential フィールド・BaseModel 型なし |
| PB-3 | S-2: credential パターンで SecurityViolationError | `test_pb3_s2_gate.py` | FieldLogParserNode | pytest.raises(SecurityViolationError) |
| PB-4 | S-3: 禁止パターンを含む出力で SecurityViolationError | `test_pb4_s3_gate.py` | SummaryGeneratorNode | pytest.raises(SecurityViolationError) |
| PB-4 | L0 import 禁止: src/ が agenticstar を直接 import しない | `test_import_isolation.py` | src/ 全体 | AST スキャンで violations=0 |
| PB-5 | エラーパスでも emit_trace_event が呼ばれる | `test_pb5_error_path_emit.py` | 全 Inner ノード | MISSING_FIELD 等エラー時に emit を確認 |
| PB-6 | モック LLM を DI して execute() が呼べる | `test_pb6_mock_llm_di.py` | FieldLogParserNode・SummaryGeneratorNode | API キーなしで SUCCESS |
| PB-6 | __call__() が S-1→S-4→S-2→execute→S-3→S-4 の順で実行される | `test_pb_invoke_order.py` | 全 src/nodes/ ノード | monkeypatch で呼び出し順を確認 |
| PB-7 | HITL interrupt propagation（スキップ） | `test_pb7_hitl_interrupt_propagation.py` | 全体 | HITL 無効（HITL_ENABLED 未設定）のため pytest.skip |

---

## Security Gate Coverage Summary

| Gate | Node | Test Coverage |
|---|---|---|
| S-1 | 全ノード | TC-02-07〜10, TC-03-09〜11, TC-04-10〜11, TC-05-07〜10, PB-2 |
| S-2 | FieldLogParserNode, CompletionValidatorNode, OpenItemFlagNode, SummaryGeneratorNode | TC-02-16〜18, TC-03-15, TC-04-14, TC-05-19, PB-3 |
| S-3 | SummaryGeneratorNode | TC-05-12〜15, PB-4 |
| S-4 | 全 Inner ノード | TC-02-12〜15, TC-03-12〜14, TC-04-12〜13, TC-05-16〜18, PB-1, PB-5 |
