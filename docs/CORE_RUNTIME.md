# HARD WORKERS — Core Runtime Specification

**Component:** Core Runtime Engine  
**Version:** 2.0 (spec)  
**Status:** Draft  
**Prerequisite:** ARCHITECTURE.md (system vision)

---

## 1. Agent Runtime

### 1.1 Lifecycle

Every agent instance progresses through a strict lifecycle. Transitions are always explicit — no implicit state changes.

```
                ┌──────────────┐
                │   CREATED    │  ← AgentFactory.create()
                └──────┬───────┘
                       │ assign_context(context)
                       ▼
                ┌──────────────┐
                │   HYDRATED   │  ← Context is immutable. Agent copies what it needs.
                └──────┬───────┘
                       │ execute()
                       ▼
                ┌──────────────┐
           ┌───▶│   RUNNING    │  ← LLM call in flight
           │    └──────┬───────┘
           │           │ LLM returns tool_calls or final_answer
           │           ▼
           │    ┌──────────────┐
           │    │  TOOL_LOOP   │  ← Executing tool calls
           │    └──────┬───────┘
           │           │ all tool results collected
           │           ├─────────────────┐
           │           │ has more tools  │ no more tools
           │           ▼                 ▼
           │    ┌──────────────┐  ┌──────────────┐
           └────│  RUNNING     │  │  COMPLETED   │  ← final_answer emitted
                └──────────────┘  └──────────────┘

                    Any state ──▶  CANCELLED     ← user cancel / timeout / error
                                    FAILED       ← unrecoverable error
```

| State | Meaning | Allowed Transitions |
|---|---|---|
| `CREATED` | Instance allocated, no context | → HYDRATED |
| `HYDRATED` | Context assigned, ready to run | → RUNNING, → CANCELLED |
| `RUNNING` | LLM call in progress | → TOOL_LOOP, → COMPLETED, → CANCELLED, → FAILED |
| `TOOL_LOOP` | Tool execution in progress | → RUNNING, → CANCELLED, → FAILED |
| `COMPLETED` | Agent produced final answer | Terminal |
| `CANCELLED` | Interrupted before completion | Terminal |
| `FAILED` | Unrecoverable error | Terminal |

### 1.2 Execution Model

```
execute(context: AgentContext) → AsyncGenerator[AgentEvent, None]
```

The agent runtime exposes a single async generator. Each yield is an `AgentEvent` — a discriminated union:

| Event | Payload | Description |
|---|---|---|
| `ThinkingUpdate` | `text: str` | Partial LLM output (streaming) |
| `ToolCallRequest` | `tool: str, params: dict, call_id: str` | Agent requests a tool execution |
| `ToolCallResult` | `call_id: str, result: ToolResult` | Tool execution result |
| `Progress` | `message: str, percentage: float` | Progress indication for UI |
| `ApprovalRequest` | `call_id: str, description: str` | Agent requests user approval |
| `FinalAnswer` | `text: str, artifacts: list[Artifact]` | Agent completed |
| `Error` | `code: str, message: str, recoverable: bool` | Error occurred |
| `Cancelled` | `reason: str` | Agent was cancelled |

The executor orchestrates: LLM call → parse tool_calls → execute tools → feed results back to LLM → repeat.

### 1.3 Cancellation

Cancellation must work at every lifecycle stage:

- **During RUNNING** — abort the pending LLM HTTP request (close aiohttp session)
- **During TOOL_LOOP** — cancel the running tool via `asyncio.Task.cancel()`
- **Between states** — check cancellation token before any transition

**Mechanism:**
- Each agent holds a `asyncio.Event` named `_cancel_requested`
- Every blocking call (LLM, tool, sleep) is wrapped with `asyncio.wait_for()` or passed the cancellation token
- When cancelled, the agent transitions to `CANCELLED`, emits a `Cancelled` event, and stops
- Cancelled agents do NOT clean up resources — they are garbage-collected by the pool

### 1.4 Retries

Retry policy is configurable per agent type and per tool call:

| Level | Config | Default |
|---|---|---|
| LLM call | `max_retries`, `backoff_base`, `backoff_max`, `retry_on` | 2, 1.0, 30.0, `[timeout, rate_limit, server_error]` |
| Tool call | `max_retries`, `backoff_base`, `retry_on` | 1, 1.0, `[timeout, transient_failure]` |
| Agent | `max_retries` (full restart) | 0 |

- LLM retries are transparent — the agent loop retries the call
- Tool retries only apply to idempotent tools (declared in tool manifest)
- Agent retries re-create the agent from scratch (state lost unless context is persisted)
- Retry budget is shared across the entire agent invocation: total retries across all LLM + tool calls ≤ `max_total_retries`

### 1.5 Approval Gates

Approval gates are checkpoints where agent execution pauses until a human approves or rejects.

**Trigger conditions** (configurable per workspace):
- Tool category: any `dangerous` tool requires approval
- File path: writes outside workspace require approval
- Permission: tool requires `human_approval` permission level
- Cost: estimated cost exceeds threshold
- Custom: plugin-defined condition

**Protocol:**
1. Agent emits `ApprovalRequest` event
2. Runtime pauses agent (state preserved)
3. Human reviews and responds: `approve` / `reject` / `modify-and-approve`
4. Agent resumes with: approved params / rejection error / modified params
5. If rejected, agent receives a ToolError with `code="REJECTED"` and must handle it

**Timeout:** Approval gates have a configurable timeout (default 5 minutes). On timeout, the gate is treated as rejected.

### 1.6 Streaming

The runtime supports three streaming levels:

| Level | Latency | Use Case |
|---|---|---|
| **Token** | Per-LLM-token | Real-time chat UI |
| **Event** | Per-agent-event | Dashboard, monitoring |
| **Batch** | Whole result | API calls, batch processing |

Streaming is a property of the consumer, not the agent. The agent always yields events via `AsyncGenerator`. The consumer chooses how to receive them:

- **Token streaming:** Subscribe to `ThinkingUpdate` events and forward LLM token deltas to the UI
- **Event streaming:** Subscribe to all events for monitoring/logging
- **Batch:** Collect all events into a list, process when `FinalAnswer` or terminal event appears

---

## 2. Tool Registry

### 2.1 Registration

Tools are registered at plugin activation time via the Tool Registry:

```
register_tool(tool_definition: ToolDef) → str  # returns tool_id
```

A `ToolDef` contains:

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique identifier (namespaced: `plugin_id.tool_name`) |
| `name` | `str` | Human-readable name |
| `description` | `str` | LLM-facing description (used for tool selection) |
| `parameters` | `JsonSchema` | Input schema |
| `returns` | `JsonSchema` | Output schema |
| `categories` | `list[str]` | `["filesystem", "network", ...]` |
| `permissions` | `list[str]` | Required runtime permissions |
| `timeout` | `int` | Max execution time in seconds |
| `idempotent` | `bool` | Safe to retry |
| `dangerous` | `bool` | Requires human approval |
| `cost_estimate` | `callable` | Optional: estimate token/cost before execution |
| `handler` | `callable` | Async function: `(ctx: ToolContext, **params) → ToolResult` |

**Registration rules:**
- No two tools can share the same `id`
- Plugin namespace is enforced: `plugin_id` is part of the tool ID
- Schema must compile (valid JSON Schema, no `$ref` to external files)
- Permissions declared must be a subset of plugin's declared permissions
- Handler signature is validated against parameter schema on registration

### 2.2 Discovery

The Tool Registry exposes discovery APIs:

```
list_tools(category: str | None = None, 
           permission: str | None = None,
           dangerous_only: bool = False,
           plugin_id: str | None = None) → list[ToolDef]
           
get_tool(tool_id: str) → ToolDef
search_tools(query: str) → list[ToolDef]
```

- Discovery is read-only from the agent/invoker perspective
- Tools can be hidden from discovery (internal tools) — not listed but still callable by ID
- Category taxonomy is extensible via plugins (plugins can declare new categories)

### 2.3 Permissions

Every tool execution goes through a permission check:

```
┌──────────┐     ┌────────────────┐     ┌──────────┐
│  Request  │────▶│ Permission     │────▶│ Execute  │
│  Tool     │     │  Check         │     │          │
│  Call     │     │                │     │          │
└──────────┘     ├────────────────┤     └──────────┘
                 │ 1. Does agent   │
                 │    have perm?   │
                 │ 2. Does tool    │
                 │    require      │
                 │    approval?    │
                 │ 3. Does context │
                 │    allow?       │
                 └────────┬───────┘
                          │ DENIED
                          ▼
                   ┌──────────────┐
                   │  Emit Error  │
                   │  or Approval │
                   │  Request     │
                   └──────────────┘
```

Permission sources (checked in order, first match wins):
1. **Agent-level grants** — explicit permissions given to this agent instance
2. **Workspace-level grants** — permissions inherited from the workspace config
3. **User-level grants** — global user permissions
4. **Plugin manifest** — tool's declared minimum permissions

### 2.4 Schema Validation

All tool inputs and outputs are validated against JSON Schema:

```
validate_input(tool_id: str, params: dict) → ValidationResult
validate_output(tool_id: str, result: Any) → ValidationResult
```

- Validation is strict by default: unknown parameters are rejected
- Output validation catches contract violations early
- Schema can include `default` values for optional parameters
- Date-time strings are coerced to `datetime` objects
- File paths are resolved relative to workspace root and normalized (no path traversal)

### 2.5 Execution Contracts

Every tool execution follows a strict contract:

```python
ToolResult = TypedDict({
    "success": bool,
    "data": Any,           # typed per tool's `returns` schema
    "error": str | None,   # human-readable error message
    "error_code": str | None,  # machine-readable: "TIMEOUT", "PERMISSION_DENIED", etc.
    "duration_ms": int,
    "token_usage": int | None,  # optional, for cost tracking
})
```

**Guarantees:**
- Tool handler is called with validated parameters only
- Tool is terminated after `timeout` seconds (`asyncio.wait_for`)
- Tool result is validated against `returns` schema before being returned to the agent
- If tool raises an unhandled exception, runtime wraps it as a `ToolResult(success=False, error=...)`
- Tools can yield progress updates (for long-running operations) via a `progress` callback passed in ToolContext

---

## 3. Skill Registry

### 3.1 Composition Model

A skill is a **composition boundary** — it bundles tools, agents, workflows, and prompts into a single deployable unit. Skills are NOT executables; they are packages of capability definitions that are activated into the runtime registries.

```
Skill
├── Tools             → registered with Tool Registry
├── Agents            → registered with Agent Factory Registry
├── Workflows         → registered with Workflow Registry
├── Prompts           → stored in Prompt Store (keyed by name)
├── Dependencies      → resolved at activation time
└── Config Schema     → validated at activation time
```

### 3.2 Skill Directory Format

```
~/.hardworkers/skills/
├── my-skill/                    # Skill directory (name = directory name)
│   ├── manifest.yaml            # Required: name, version, description, author
│   ├── tools/                   # Optional: tool definitions
│   │   ├── my_tool.yaml         # ToolDef in YAML
│   │   └── my_tool.py           # Optional: handler implementation
│   ├── agents/                  # Optional: agent definitions
│   │   └── my_agent.yaml
│   ├── workflows/               # Optional: workflow definitions
│   │   └── my_workflow.yaml
│   ├── prompts/                 # Optional: prompt templates (Jinja2)
│   │   └── system.j2
│   └── assets/                  # Optional: static files
│       └── schema.sql
├── another-skill/
│   └── ...
└── skill-index.json             # Generated cache of all installed skills
```

### 3.3 Skill Manifest

```yaml
# manifest.yaml
name: code-review
version: 1.2.0
description: Automated code review with AI-powered suggestions
author: HardWorkers Ecosystem
license: MIT

requires:
  core_version: ">=4.0.0,<5.0.0"
  skills:
    - name: git-integration
      version: ">=1.0.0"
    - name: linting
      version: ">=2.0.0"
  tools: []        # tool IDs required (but not owned by this skill)
  
provides:
  tools:
    - review.diff
    - review.suggest
  agents:
    - code-reviewer
  workflows:
    - full-code-review

permissions:
  - filesystem.read
  - filesystem.write
  - network.github

config_schema:
  type: object
  properties:
    review_depth:
      type: string
      enum: [quick, full]
      default: quick
    auto_approve:
      type: boolean
      default: false
```

### 3.4 Reusable Skills

Skills can depend on other skills, forming a DAG:

```
code-review
├── git-integration v1+     ← reuse git tools without redefining them
├── linting v2+              ← reuse linting tools
└── reporting v1+            ← reuse report generation
```

- Dependencies are resolved at activation time (topological sort)
- Circular dependencies are detected and rejected
- Multiple versions of the same skill can be installed; only one is active at a time
- A skill's activation calls `activate()` on its dependencies first (if not already active)

### 3.5 Versioning

Skill versioning follows strict semver:

| Change | Type | Example |
|---|---|---|
| Backward-compatible bug fix | Patch | 1.0.0 → 1.0.1 |
| New tools/agents/workflows (backward-compatible) | Minor | 1.0.0 → 1.1.0 |
| Breaking tool contract, removed dependency | Major | 1.0.0 → 2.0.0 |

**Version resolution:**
- `>=1.0.0,<2.0.0` — accept any 1.x release
- `^1.0.0` — compatible with 1.0.0 and above (same major)
- `~1.0.0` — patch-level changes only
- `1.0.0` — exact match only

**Conflict resolution:**
- If two skills depend on incompatible versions of the same dependency, activation fails with a clear error message
- A `skill.lock` file pins exact versions after first successful resolution

---

## 4. Workflow Engine

### 4.1 DAG Execution

A workflow is a directed acyclic graph of steps. The engine:

1. Parses the workflow definition into an in-memory DAG
2. Validates the DAG (no cycles, all references exist)
3. Topologically sorts the nodes
4. Executes ready nodes (no unexecuted dependencies) in parallel up to `max_concurrency`

**State machine per node:**

```
PENDING → READY → RUNNING → COMPLETED
                   ↓
               FAILED
                   ↓
               SKIPPED
```

- **PENDING** — not yet evaluated
- **READY** — all dependencies are COMPLETED (or have no dependencies)
- **RUNNING** — executing via agent or direct tool call
- **COMPLETED** — execution finished successfully, outputs stored
- **FAILED** — execution finished with error
- **SKIPPED** — node's `condition` evaluated to false

### 4.2 Workflow Definition

```yaml
workflow:
  id: example-workflow
  version: 1.0
  description: Multi-step task with branching
  
  config:
    max_concurrency: 3
    timeout: 300
    error_handling: stop_all  # stop_all | continue | retry_node

  inputs:
    repo_path:
      type: string
      description: Path to the repository
    branch:
      type: string
      default: main

  steps:
    - id: lint
      type: tool
      tool: code.lint
      params:
        path: "{{ inputs.repo_path }}"
      timeout: 60

    - id: test
      type: tool
      tool: code.test
      params:
        path: "{{ inputs.repo_path }}"
      timeout: 120
      depends_on: [lint]

    - id: analyze
      type: agent
      agent: code-reviewer
      prompt: "Review the code at {{ inputs.repo_path }}"
      depends_on: [lint, test]
      timeout: 300

    - id: report
      type: workflow
      workflow: generate-report
      depends_on: [analyze]
      condition: "{{ analyze.result.has_issues }}"
```

**Node types:**
| Type | Executor | Description |
|---|---|---|
| `tool` | Tool Registry | Direct tool call |
| `agent` | Agent Runtime | Full agent invocation |
| `workflow` | Workflow Engine | Sub-workflow (reuse) |
| `approval` | — | Human approval gate |
| `condition` | Expression engine | Evaluate condition, route execution |
| `transform` | Expression engine | Transform data between steps |

### 4.3 Branching

Branching is achieved through `condition` expressions and multiple `depends_on`:

- **If/else** — two nodes with complementary conditions, same dependencies
- **Switch** — N nodes with mutually exclusive conditions
- **Parallel fan-out** — one node fans out to N children with different params
- **Join** — node with N dependencies waits for all to complete before executing

Condition expressions use JQ-like syntax (`jsonpath-ng`):
```
"{{ analyze.result.has_issues == true }}"
"{{ inputs.repo_path | startswith('/tmp') }}"
"{{ test.result.passed == false && lint.result.score < 50 }}"
```

### 4.4 Parallelism

The engine maintains a ready queue. All READY nodes run concurrently up to `max_concurrency`:

```
PENDING: [lint, test, analyze, report]
                ↓ topo sort
READY: [lint, test]          ← no dependencies, both can run
                ↓ execute both
READY: [analyze]              ← depends on lint AND test (both done)
                ↓ execute
READY: [report]               ← depends on analyze
```

- `max_concurrency` is configurable per workflow and per node
- Each node runs in its own `asyncio.Task`
- A node waiting on human approval (type `approval`) does NOT count toward concurrency
- Resource limits can be applied: max_concurrency per tool category, per plugin

### 4.5 Checkpoints

Checkpoints allow a workflow to be paused and resumed:

```
checkpoint:
  - every_node: false       # save state after every node
  - on_approval: true       # save before approval gates
  - on_failure: true        # save on failure for later debugging
  - periodic_seconds: 0     # 0 = disabled
```

**Checkpoint storage:**
- Serialized DAG state (each node's status, inputs, outputs)
- Agent context snapshots (if agent was mid-execution)
- Stored in local database (SQLite) or on disk (JSON)

**Resume:**
- Reload checkpoint
- Rehydrate COMPLETED nodes (no re-execution)
- Place failed nodes back in READY
- Continue execution from checkpoint

### 4.6 Replay

Replay re-executes a workflow from a specific node while keeping prior results:

```
replay(workflow_id, run_id, from_node="lint", with_overrides={"inputs.branch": "feature-x"})
```

- Node results before `from_node` are loaded from checkpoint (not re-executed)
- Node `from_node` and all descendants are re-executed
- All descendant checkpoints are invalidated
- Replay produces a new `run_id` and a reference to the source `run_id`

---

## 5. Context Manager

### 5.1 Context Types

The Context Manager builds and manages the `AgentContext` — the immutable input to every agent invocation:

```python
class AgentContext:
    id: str                       # unique invocation ID
    conversation: ConversationContext
    workspace: WorkspaceContext
    memory: MemoryContext
    files: FileContext
    token_budget: TokenBudget
    permissions: list[str]
    environment: dict              # env vars, feature flags, experiment config
    metadata: dict                 # correlation IDs, tracing, timing
```

### 5.2 Conversation Context

Carries the current and historical conversation turns:

```python
class ConversationContext:
    messages: list[Message]
    max_turns: int                # configurable, default 50
    truncation_strategy: str      # "drop_oldest" | "summary" | "none"
    
    def snapshot(self) -> ConversationContext:  # immutable copy
    def append(self, message: Message) -> None  # only allowed by runtime
```

Each `Message` has:
```
role: "user" | "assistant" | "system" | "tool"
content: str | list[ContentBlock]
tool_calls: list[ToolCall] | None
tool_call_id: str | None
timestamp: datetime
```

**Truncation:**
- When `len(messages) > max_turns`, the oldest user+assistant pair is replaced with a summary
- Summary is generated by a separate summarization agent or LLM call
- System messages and tool results are never truncated (tool results may be summarized)

### 5.3 Workspace Context

Provides information about the current workspace:

```python
class WorkspaceContext:
    id: str
    name: str
    root_path: Path               # absolute path to workspace root
    allowed_paths: list[Path]     # paths tools may read/write
    model: str                    # active model for this workspace
    router_mode: str
    settings: dict                # workspace-specific config
```

### 5.4 Memory Context

Provides relevant memory for the agent's task:

```python
class MemoryContext:
    facts: list[MemoryItem]       # semantic memory (user facts, preferences)
    episodes: list[MemoryItem]    # episodic memory (past sessions)
    procedures: list[MemoryItem]  # procedural memory (skill docs)
    archival: list[MemoryItem]    # vector search results
    
    class MemoryItem:
        key: str
        value: str
        source: str               # "semantic" | "episodic" | "procedural" | "archival"
        timestamp: datetime
        relevance_score: float    # 0.0 - 1.0
```

**Building:** The Context Manager queries all active memory layers (see Memory Architecture in ARCHITECTURE.md) and injects the top-K results sorted by relevance.

### 5.5 File Context

Provides file-level context for code-related tasks:

```python
class FileContext:
    open_files: dict[str, FileSnapshot]   # actively being edited
    recent_changes: list[FileChange]      # git diff or undo history
    project_structure: ProjectTree | None # parsed directory tree
    
    class FileSnapshot:
        path: Path
        content: str
        language: str | None  # detected language
        size_bytes: int
        modified_at: datetime
    
    class FileChange:
        path: Path
        diff: str
        timestamp: datetime
        tool_id: str  # which tool made the change
```

### 5.6 Token Budgeting

Token budgets prevent runaway context costs. Every agent invocation has a budget:

```python
class TokenBudget:
    max_input_tokens: int          # upper bound, default 32K
    max_output_tokens: int         # default 4K
    max_total_tokens: int          # max_input + max_output, default 36K
    reserve_for_tools: int         # tokens reserved for tool descriptions, default 4K
    reserve_for_history: int       # tokens reserved for conversation context, default 8K
    
    # Computed values (set by Context Manager during assembly)
    actual_input_tokens: int | None
    actual_output_tokens: int | None
    actual_total_tokens: int | None
```

**Budget enforcement:**
1. Context Manager estimates token count of each context component
2. If estimated total > `max_input_tokens`:
   - Truncate archival memory items (drop lowest relevance)
   - Truncate conversation history (drop oldest turns or summarize)
   - Truncate project structure (shallow tree only)
   - If still over budget, refuse to invoke agent
3. Agent monitors output tokens during streaming
4. If output approaches `max_output_tokens`, agent receives a `token_exhausted` signal and should produce a final answer
5. After execution, actual token usage is reported back to the budget tracker

**Edge case - overflow:**
If the LLM continues generating past the budget, the runtime truncates the output at the budget boundary and appends a `[output truncated due to token limit]` marker.

---

*End of specification. This document defines the contracts and behaviors of the Core Runtime. Implementations must satisfy these specifications but are free to choose internal data structures as long as the external contracts are met.*
