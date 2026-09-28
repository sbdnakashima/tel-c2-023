# Template Design Specification — TEL-C2-023

## Position in AgentCore Architecture

- **Agent Class**: Graph (AgentBaseGraph L1直継承)
- **L1 Base**: AgentBaseGraph
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: Cat 2 Outer+Inner 2層構成（Outer=AgentBaseGraph, Inner=BaseGraph）

## Architecture Overview

### Node Configuration

#### Outer Graph（`src/graph/graph.py`）

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | スキーマバージョン設定・初期メタデータ | — | schema_version | InitializeNode (default) |
| pre_process | 入力パススルー（Inner graph で S-1 実施） | — | — | PassThroughNode (default) |
| main | Inner graph 呼び出し（パース→バリデーション→フラグ→サマリー生成） | field_log, work_type, work_order_id, measurements | parsed_actions, validation_results, completion_status, open_items, completion_report, audit_log | FieldLogWorkflowGraphNode (GraphNode) |
| post_process | 出力パススルー（S-3 は Inner graph 内で実施済み） | — | — | PassThroughNode (default) |
| finalize | レスポンスメタデータ組み立て | — | response_metadata | FinalizeNode (default) |

#### Inner Graph（`src/graph/field_log_workflow_graph.py`）

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| field_log_parser | S-1 入力バリデーション・LLM ログパース・計測値抽出・確信スコア算出 | field_log, work_type, measurements | parsed_actions, extracted_measurements, parse_confidence | FieldLogParserNode (FunctionNode) |
| completion_validator | 作業種別別完了基準チェック・閾値判定・欠落ステップ検出 | parsed_actions, extracted_measurements, work_type | validation_results, completion_status | CompletionValidatorNode (FunctionNode) |
| open_item_flag | Fail/要確認集約・緊急度分類・推奨アクション生成 | validation_results, completion_status | open_items | OpenItemFlagNode (FunctionNode) |
| summary_generator | ITSM 向けサマリー生成・S-3 ゲート・監査ログ記録 | parsed_actions, validation_results, completion_status, open_items, work_order_id | completion_report, audit_log | SummaryGeneratorNode (FunctionNode) |

### Data Flow

```
[Outer graph]
START → initialize → pre_process → main → {route} → post_process → finalize → END
                                      ↓ (ERROR)
                                    finalize

[Inside main — FieldLogWorkflowGraphNode]
  inner_graph.invoke()
    START → field_log_parser → completion_validator → open_item_flag → summary_generator → END
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| work_order_id | Optional[str] | 作業指示書 ID | ✅ (入力) |
| work_type | Optional[str] | 作業種別（base_station_installation / fiber_splicing / cpe_provisioning 等） | ✅ (入力) |
| field_log | Optional[str] | フィールドエンジニアの自由テキストログ | ✅ (入力) |
| measurements | Optional[str] | 計測値 JSON 文字列（VSWR・光損失・信号強度等）| — (任意入力) |
| parsed_actions | Optional[str] | 構造化アクションリスト JSON 文字列 | FieldLogParserNode が書く |
| extracted_measurements | Optional[str] | 抽出・標準化済み計測値 JSON 文字列 | FieldLogParserNode が書く |
| parse_confidence | Optional[str] | パース確信スコア（float を文字列化）| FieldLogParserNode が書く |
| validation_results | Optional[str] | 各チェック項目の Pass/Fail JSON 文字列 | CompletionValidatorNode が書く |
| completion_status | Optional[str] | `complete` / `partial` / `incomplete` | CompletionValidatorNode が書く |
| open_items | Optional[str] | 緊急度ラベル付きオープン課題リスト JSON 文字列 | OpenItemFlagNode が書く |
| completion_report | Optional[str] | ITSM 向けサマリー（JSON 文字列）| SummaryGeneratorNode が書く |
| audit_log | Optional[str] | 監査ログ JSON 文字列（work_order_id・timestamp・completion_status）| SummaryGeneratorNode が書く |
| error_code | Optional[str] | エラーコード（MISSING_FIELD / UNKNOWN_WORK_TYPE / LOW_CONFIDENCE / S3_BLOCKED 等）| 各ノードが書く |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- リスト・辞書は JSON 文字列（str）として保持（msgpack 非互換のため）

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [x] ConnectionPolicy (retry/timeout strategy)
- [x] SecurityViolationError
- [x] S-2: `_extra_security_gate_input()` — FieldLogParserNode: credential パターン検出・必須フィールド（field_log・work_type）欠損検出
- [x] S-3: `_extra_security_gate_output()` — SummaryGeneratorNode: 顧客住所・設備 ID・技術者個人情報の除去確認
- [x] S-4: `emit_trace_event()` — 各ノードの execute() 内でドメインイベントを 1 件以上 emit

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - FieldLogParserNode / CompletionValidatorNode / OpenItemFlagNode / SummaryGeneratorNode は全て `FunctionNode` 継承
> - → framework `@final` gate が自動実行；追加チェックは `_extra_security_gate_input()` / `_extra_security_gate_output()` のみ
> - FieldLogWorkflowGraphNode は `GraphNode` 継承 → gate は deliberate no-op（Inner graph 側で適用済み）

### Composition Pattern

- **Pattern**: Cat 2 Outer + Inner（GraphNode を `main` スロットに配置）
- **Outer graph**: `src/graph/graph.py` — AgentBaseGraph 継承
- **Inner graph**: `src/graph/field_log_workflow_graph.py` — BaseGraph 継承（完全カスタムトポロジー）
- **GraphNode**: `FieldLogWorkflowGraphNode` — `main` スロットに配置
- **Error propagation strategy**: propagate（Inner graph の例外を SubgraphError として再 raise）

### Security Design

| Gate | Node | 実装内容 |
|------|------|---------|
| S-1 | 全ノード | `required_trust_level = TrustLevel.VERIFIED_EXTERNAL` を宣言 |
| S-2 | FieldLogParserNode | `_extra_security_gate_input()`: credential パターン検出（APIキー・JWT・AWSキー）・必須フィールド（field_log・work_type）欠損検出 |
| S-3 | SummaryGeneratorNode | `_extra_security_gate_output()`: 出力に顧客住所・設備 ID・技術者個人情報が残っていないか検証 |
| S-4 | 全ノード | `emit_trace_event()` でドメインイベントを emit（`field_log_parsed` / `completion_validated` / `open_items_flagged` / `summary_generated`）|

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | 固定パイプライン（Cat 2）; LLM ループ不要 |
| Composition pattern | Flat 3-node (pre/main/post) | Cat 2 Outer+Inner (GraphNode in main) | Cat 2 Outer+Inner | 4ノード（Parser/Validator/Flagger/Generator）を収容するため Inner graph に集約 |
| Inner graph base | BaseGraph (fully custom) | AgentBaseGraph (5-node backbone) | BaseGraph | `field_log_parser → completion_validator → open_item_flag → summary_generator` の線形4ノードは AgentBaseGraph の pre/main/post 強制に合わせる必要がない |
| LLM 利用箇所 | FieldLogParserNode のみ | Parser + Generator 両方 | Parser + Generator | ログパース（自然言語理解が必須）と完了サマリー生成（ITSM 向け自然文が必須）で LLM が必要。Validator はルールベース（config-driven チェックリスト）で十分 |
| S-3 適用ノード | SummaryGeneratorNode のみ | 全出力ノード | SummaryGeneratorNode のみ | 外部出力は SummaryGeneratorNode が唯一の出口。中間ノードの出力は State 内部に留まるため S-3 除外フィールド管理不要 |
| 低確信スコア時の挙動 | エラー終了 | `requires_human_review` フラグ付きで継続 | フラグ付きで継続 | パース精度が低い場合でも NOC への通知が必要なため、エラー終了は避けて `parse_confidence` フラグを付与してサマリーを出力する |
