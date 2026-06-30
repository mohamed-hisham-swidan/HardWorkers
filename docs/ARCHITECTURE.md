# HARD WORKERS — Architecture Roadmap

**Lead Systems Architect:** Autonomous Agent Platform  
**Date:** 2026-06-23  
**Version:** 3.3.0 → 5.0.0  

---

## 1. System Vision

**HARD WORKERS** evolves from a local AI desktop assistant into a **universal agent platform** — a local-first, extensible runtime that hosts autonomous AI agents, executes tools, orchestrates multi-agent workflows, and integrates with any LLM backend.

The platform targets three tiers:
| Edition | Scope |
|---|---|
| **Light** | Single-agent chat + tools + file ops. Local only. |
| **Pro** | Multi-agent orchestration, skills registry, plugin system, memory persistence. |
| **Core** | Headless API server, workflow automation, simulation engine, enterprise auth, cloud sync. |

**Design axioms:**
- Every component is a replaceable plugin
- No component imports another by name — only by contract (Protocol/ABC)
- The event bus is the nervous system
- The agent runtime never blocks the UI thread
- All state is versioned and replayable
- Security is layered, not bolted on

---

## 2. Core Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     Presentation Layer                       │
│  (Flet UI / Web UI / CLI / API Server / VS Code Extension)  │
└──────────────────────┬──────────────────────────────────────┘
                       │ IPC (Event Bus / WebSocket / REST)
┌──────────────────────┴──────────────────────────────────────┐
│                   Orchestration Layer                        │
│  Agent Runtime · Workflow Engine · Scheduler · Skill Runner │
├─────────────────────────────────────────────────────────────┤
│                      Agent Layer                             │
│  Agent Registry · Tool Executor · Context Builder · Memory   │
├─────────────────────────────────────────────────────────────┤
│                    Capability Layer                           │
│  Tools · Skills · Plugins · File System · Shell · Browser   │
├─────────────────────────────────────────────────────────────┤
│                     Model Layer                               │
│  LLM Router · Provider Abstraction · Tokenizer · Embeddings │
├─────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                         │
│  Event Bus · Persistence · Config · Auth · Logging · Metrics │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**Presentation** — zero business logic. Translates user intent into events. Multiple frontends share the same backend via a documented IPC protocol.

**Orchestration** — receives events from presentation, decomposes into agent tasks, schedules execution, monitors progress, returns results. The only layer that knows about workflows.

**Agent** — stateless agent instances created on demand. Each agent receives context + tools, calls the LLM, executes tool calls, and returns results. No workflow knowledge.

**Capability** — pure functions exposed as tools/skills. Each capability is self-documenting (JSON Schema for inputs/outputs), stateless, and sandboxed.

**Model** — abstraction over Ollama, OpenAI, Anthropic, etc. Router selects provider per-task. Plugins can add providers.

**Infrastructure** — services that everything depends on. Logging, config, event bus, database, auth.

---

## 3. Agent Architecture

### 3.1 Agent Abstraction

```python
# Protocol — not a base class
class Agent(Protocol):
    """An agent is a stateless function: context → result."""
    id: str
    capabilities: list[str]
    async def execute(self, context: AgentContext) -> AgentResult
```

**Key properties:**
- **Stateless** — all state lives in `AgentContext` (conversation history, tool results, memory snapshots). Agents are instantiated per-invocation.
- **Immutable context** — context is copied before mutation. Version counter prevents stale writes.
- **Capability-based routing** — agents declare what they can do. The orchestrator selects agents by matching task requirements to agent capabilities.
- **Recursion guard** — max depth, cycle detection, timeout per agent.

### 3.2 Agent Types

| Type | Base | Capabilities | Persistence |
|---|---|---|---|
| ChatAgent | General conversation | `chat`, `context` | None |
| CodingAgent | Code generation | `read`, `edit`, `search`, `execute` | None |
| ResearchAgent | Web/data research | `web_search`, `fetch`, `extract` | Optional |
| EditorAgent | File editing | `read`, `edit`, `diff`, `patch` | None |
| OrchestratorAgent | Delegation | `delegate`, `merge`, `summarize` | Required |
| SupervisorAgent | Multi-agent oversight | `plan`, `assign`, `review`, `approve` | Required |
| CustomAgent | Plugin-defined | Declared in manifest | Plugin-defined |

### 3.3 Agent Lifecycle

```
Create → AssignContext → Execute → [ToolLoop] → Finalize → EmitResult
                              ↑__________|
```

1. **Create** — `AgentFactory` instantiates agent from registry
2. **AssignContext** — builds `AgentContext` with conversation, memory, workspace
3. **Execute** — agent calls LLM, processes tool calls
4. **ToolLoop** — agent may iterate: tool result → LLM → next tool call → repeat
5. **Finalize** — agent emits result event, returns to pool
6. **Timeout/Error** — agent emits error event, orchestrator handles retry or fallback

### 3.4 Agent Registry

Central registry mapping `str → AgentFactory`. Factories are registered by plugins on startup.

```python
# Contract
class AgentFactory(Protocol):
    agent_id: str
    capabilities: list[str]
    async def create(self, config: dict) -> Agent
    def manifest(self) -> AgentManifest  # name, description, config schema
```

---

## 4. Tool Architecture

### 4.1 Tool Definition

Every tool is a self-describing function with a JSON Schema contract:

```python
class Tool:
    name: str
    description: str
    parameters: JsonSchema  # input schema
    returns: JsonSchema      # output schema
    categories: list[str]    # for routing and discovery
    timeout: int             # max execution time (seconds)
    requires: list[str]      # required permissions
    async def __call__(self, ctx: ToolContext, **params) -> ToolResult
```

### 4.2 Built-in Tool Categories

| Category | Examples |
|---|---|
| `filesystem` | `read`, `write`, `edit`, `glob`, `grep`, `diff`, `patch` |
| `shell` | `run_command`, `run_script` (sandboxed) |
| `web` | `web_fetch`, `web_search`, `web_scrape` |
| `code` | `lint`, `format`, `compile`, `test` |
| `git` | `status`, `diff`, `commit`, `log` |
| `memory` | `search_memory`, `store_fact`, `recall` |
| `agent` | `delegate`, `merge_results` |
| `knowledge` | `search_knowledge`, `ask_rag` |
| `browser` | `navigate`, `click`, `type`, `screenshot` |
| `simulation` | `simulate`, `validate`, `report` |

### 4.3 Tool Execution Pipeline

```
validate permissions → validate input schema → execute with timeout → capture output → validate output schema → return
```

- **Permission check** — tool inspects ToolContext for granted permissions
- **Schema validation** — input/output validated against JSON Schema
- **Timeout** — each tool has a max execution time; `asyncio.wait_for`
- **Sandboxing** — shell/file tools execute in a restricted directory or container
- **Audit trail** — every tool call is logged: who, what, params, result, duration

### 4.4 Tool Registry

Plugins register tool factories:

```python
class ToolFactory(Protocol):
    tool_name: str
    async def create(self, config: dict) -> Tool
    def manifest(self) -> ToolManifest
```

Registry supports:
- **Discovery** — list all tools, filter by category/permission
- **Validation** — JSON Schema validation of tool definitions
- **Override** — plugins can replace built-in tools (with versioning)

---

## 5. Skills Architecture

### 5.1 Concept

A **skill** is a composable, shareable, versioned unit of agent capability. Skills are to agents what plugins are to IDEs.

### 5.2 Skill Structure

A skill is a directory or package containing:

```
skill/
├── manifest.yaml          # name, version, author, dependencies
├── tools/                 # optional: new tools this skill provides
│   └── my_tool.py
├── agents/                # optional: new agent types
│   └── my_agent.py
├── workflows/             # optional: predefined workflows
│   └── my_workflow.yaml
├── prompts/               # optional: prompt templates
│   └── system.j2
├── assets/                # optional: static files
└── config_schema.yaml     # JSON Schema for skill configuration
```

### 5.3 Skill Registry

- **Local** — `~/.hardworkers/skills/` directory scanned at startup
- **Marketplace** — remote registry (optional, Pro/Core)
- **Versioning** — semver, dependency resolution
- **Isolation** — skills run in their own namespace; cannot import each other's internals

### 5.4 Skill Lifecycle

```
Discover → Validate → Activate → [Update] → Deactivate
```

- **Discover** — scan enabled skill directories
- **Validate** — check manifest, dependencies, config schema
- **Activate** — register tools, agents, workflows with the appropriate registries
- **Update** — hot-reload on file change (development mode)
- **Deactivate** — unregister all contributions

---

## 6. Workflow Architecture

### 6.1 Workflow Engine

Workflows are directed acyclic graphs (DAGs) of agent tasks. The engine:

1. Parses a workflow definition (YAML/Python DSL)
2. Resolves agent and tool dependencies
3. Executes nodes in topological order
4. Handles branching, parallel execution, error recovery
5. Produces a trace for debugging and replay

### 6.2 Workflow Definition

```yaml
workflow:
  id: code-review
  version: 1.0
  description: Analyze code, suggest fixes, create PR

  inputs:
    repo_path: string
    branch: string

  steps:
    - id: lint
      agent: coding-agent
      prompt: "Run linting on {{ repo_path }}"
      tools: [shell, filesystem]
    
    - id: analyze
      agent: research-agent  
      prompt: "Analyze lint results and suggest fixes"
      depends_on: [lint]
      tools: [memory, knowledge]

    - id: fix
      agent: editor-agent
      prompt: "Apply suggested fixes"
      depends_on: [analyze]
      tools: [filesystem, git]
      condition: "{{ analyze.has_issues }}"
```

### 6.3 Workflow Features

| Feature | Description |
|---|---|
| **Parallelism** | Nodes without dependencies run concurrently |
| **Conditionals** | Nodes can have `condition` expressions |
| **Retry** | Configurable retry with backoff per node |
| **Timeouts** | Per-node and global workflow timeout |
| **Approval gates** | Human-in-the-loop checkpoints (Pro/Core) |
| **Observability** | Every node produces structured logs + metrics |
| **Replay** | Workflow can be replayed from any node for debugging |

---

## 7. Memory Architecture

### 7.1 Layered Memory System

```
┌────────────────────────────────────────────┐
│            Working Memory (Agent)           │  ← conversation, tool results, ephemeral
├────────────────────────────────────────────┤
│          Episodic Memory (Session)          │  ← past sessions, decisions, outcomes
├────────────────────────────────────────────┤
│           Semantic Memory (Profile)         │  ← facts, preferences, learned patterns
├────────────────────────────────────────────┤
│          Procedural Memory (Skills)         │  ← skill definitions, workflows, prompts
├────────────────────────────────────────────┤
│             Archival Memory (DB)            │  ← long-term vector + relational store
└────────────────────────────────────────────┘
```

### 7.2 Memory Store Interface

```python
class MemoryStore(Protocol):
    async def store(self, key: str, value: Any, metadata: dict) -> None
    async def retrieve(self, key: str) -> Any | None
    async def search(self, query: str, limit: int = 10) -> list[MemoryItem]
    async def delete(self, key: str) -> None
    async def list_keys(self, prefix: str) -> list[str]
```

### 7.3 Memory Profiles

Profiles determine which memory layers are active and their retention policy:

- **Coding** — strong semantic + procedural memory, archival enabled
- **Research** — strong episodic + semantic memory, web-enriched
- **No Memory** — working memory only
- **Custom** — user-configurable layers and retention

### 7.4 Agent Context Building

Memory is injected into agent context at invocation:

1. Working memory → conversation history
2. Episodic memory → relevant past sessions
3. Semantic memory → user facts, preferences
4. Procedural memory → available skills, tool documentation
5. Archival memory → vector search results (RAG)

Each layer is tagged with its source so the agent can cite provenance.

---

## 8. Plugin Architecture

### 8.1 Plugin Contract

```python
class Plugin(Protocol):
    id: str
    version: str
    async def activate(self, ctx: PluginContext) -> None
    async def deactivate(self) -> None
```

### 8.2 Plugin Registration Points

| Hook | When | What plugins can do |
|---|---|---|
| `on_startup` | App boot | Register agents, tools, skills, workflows |
| `on_shutdown` | App close | Clean up resources |
| `on_settings_changed` | Settings save | React to config changes |
| `on_event` | Any event bus event | Intercept or extend behavior |
| `on_tool_call` | Before/after tool | Wrap, log, modify, block |
| `on_agent_result` | Agent completes | Post-process, store, alert |
| `on_workflow_step` | Workflow node | Custom node types, side effects |

### 8.3 Plugin Declaration

```yaml
# manifest.yaml
plugin:
  id: github-integration
  version: 1.0.0
  author: HardWorkers
  min_core_version: 4.0.0
  hooks:
    - on_startup
    - on_tool_call
  provides:
    tools: [github.pr, github.issue, github.review]
    agents: [code-reviewer]
    skills: [code-review]
  requires:
    permissions: [network, filesystem]
    config_schema: 
      token: { type: string, secret: true }
```

### 8.4 Plugin Isolation

- **Namespace** — plugins cannot import each other
- **Permissions** — plugins declare required permissions; user approves at install time
- **Resource limits** — CPU, memory, network per plugin
- **Fault isolation** — one plugin crashing cannot take down the platform

---

## 9. Simulation Integration Architecture

### 9.1 Purpose

The simulation engine enables agents to:
- Test code changes in isolated environments
- Evaluate tool calls before executing them on real data
- Train/improve agent performance via reinforcement learning
- Run "what-if" scenarios for workflow planning

### 9.2 Architecture

```
┌─────────────┐     ┌─────────────┐
│  Agent       │────▶│  Simulator   │
│  Runtime     │     │  Sandbox     │
└─────────────┘     └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ File     │ │ Network  │ │ Time     │
       │ Sim      │ │ Sim      │ │ Sim      │
       └──────────┘ └──────────┘ └──────────┘
```

### 9.3 Simulation Features

- **Deterministic replay** — same inputs → same outputs
- **Time scaling** — simulate hours of real time in seconds
- **Network mock** — record/replay HTTP, or simulate failure modes
- **File system snapshot** — before/after diff for every file operation
- **Cost projection** — estimate token usage before real execution

### 9.4 Integration Points

| Component | Integration |
|---|---|
| Agent Runtime | Agents can be launched in "simulation mode" |
| Tool Executor | Tools check for simulated environment flag |
| Workflow Engine | Workflows can be "dry-run" in simulation |
| Evaluator | Simulation results feed into agent training |

---

## 10. Security Model

### 10.1 Principles

- **Least privilege** — every agent, tool, and plugin gets only the permissions it declares
- **Defense in depth** — runtime checks + OS-level sandboxing + user approval
- **Audit everything** — all tool calls, agent decisions, and file changes are logged
- **No ambient authority** — capabilities must be explicitly granted

### 10.2 Permission System

```yaml
# Permission categories
permissions:
  filesystem:
    - read: [paths]
    - write: [paths]
    - execute: [paths]
  network:
    - http: [hosts]
    - websocket: [hosts]
  shell:
    - run: [command_patterns]
  system:
    - clipboard
    - notification
    - credential_access
  agent:
    - delegate_to: [agent_ids]
    - create_agent: [agent_types]
```

### 10.3 Trust Levels

| Level | Description | Access |
|---|---|---|
| `system` | Core platform | All permissions |
| `installed` | User-installed plugins | As granted at install time |
| `workspace` | Workspace-level skills | Workspace-scoped filesystem |
| `session` | Ephemeral agents | Temporary, no persistence |
| `sandboxed` | Untrusted code | Containerized, no network |

### 10.4 Human Approval Gates

- **File edits** — configurable: auto-approve / diff review / block
- **Shell commands** — command pattern allowlist/blocklist
- **Network access** — host allowlist
- **Agent delegation** — confirmation before spawning sub-agents
- **Cost thresholds** — warn before exceeding token/API cost limits

---

## 11. Scalability Roadmap

### 11.1 Phase 1: Single Process (Current → v4.0)

**Capacity:** 1 user, 1 session, single agent  
**Limits:** Memory, CPU-bound LLM calls block UI  
**Improvements in v4.0:**
- Async agent execution (never blocks UI)
- Plugins load from isolated namespaces
- Tool execution timeouts
- Memory layering (working → episodic → semantic → archival)

### 11.2 Phase 2: Multi-Agent (v4.0 → v4.5)

**Capacity:** 1 user, concurrent agents, workflow DAGs  
**Architecture:**
- Agent pool with configurable concurrency
- Workflow engine (DAG scheduler)
- Tool sandboxing (per-tool directory jailing)
- Event bus as the only cross-component communication channel

### 11.3 Phase 3: Headless API Server (v4.5 → v5.0)

**Capacity:** N users, multi-session, headless operation  
**Architecture:**
- WebSocket JSON-RPC API (presentation-agnostic)
- Session isolation (each user gets an independent agent runtime)
- Optional cloud sync for memory + workspace (Pro/Core)

### 11.4 Phase 4: Distributed (v5.0+)

**Capacity:** N users, distributed agent workers, cloud-backed  
**Architecture:**
- Agent workers as separate processes/machines
- Message queue (Redis/NATS) for inter-worker communication
- Shared vector store (Qdrant/Pinecone)
- Horizontal scaling of model inference via vLLM/TGI

---

## 12. Migration Roadmap from Current Codebase

### 12.1 What Stays

| Component | Status | Action |
|---|---|---|
| Event Bus | Strong | Keep, document contracts |
| Settings Service | Strong | Keep, add plugin settings namespace |
| Memory Service | Strong | Extract to MemoryStore protocol |
| Workspace Service | Strong | Keep, add workspace-scoped permissions |
| Router | Strong | Keep as Model Layer, add provider plugins |
| Vector Store | Strong | Keep as archival memory backend |
| Database Layer | Strong | Keep, add migrations for new tables |
| STT/TTS | Moderate | Keep as voice plugin |
| Flet UI | Moderate | Keep as Presentation Layer, extract to plugin |

### 12.2 What Changes

| Component | Current | Target |
|---|---|---|
| Agent Framework | Exists, unused | Connected to chat flow, Agent Registry |
| Tool System | Hardcoded functions | Plugin-registered Tool Registry |
| Skills System | None | Directory-based skill loading |
| Workflow Engine | None | DAG executor |
| Chat Execution | Direct LLM call | Agent → ToolLoop → LLM |
| Plugin System | None | Plugin lifecycle + hooks |
| Permissions | None | Layered permission system |

### 12.3 Migration Phases

**v3.3 → v4.0 (Incremental):**
1. Extract Tool protocol from current hardcoded helpers
2. Connect existing Agent framework to chat execution path
3. Add Plugin lifecycle (on_startup, on_shutdown hooks)
4. Add agent-tool loop (LLM generates tool calls, agent executes them)
5. Migrate memory to layered protocol

**v4.0 → v4.5 (Architecture):**
6. Extract Workflow Engine
7. Add Skills directory scanning
8. Add sandboxed tool execution
9. Implement permission system
10. WebSocket API server

**v4.5 → v5.0 (Platform):**
11. Multi-session isolation
12. Marketplace skill registry
13. Simulation engine
14. Cloud sync (Pro/Core)

### 12.4 Avoiding Architectural Debt

| Practice | Enforcement |
|---|---|
| All cross-component communication through event bus | Lint rule |
| Every public API has a Protocol | Type-checked at import |
| Plugin hooks are versioned | Manifest declares `min_core_version` |
| Deprecation policy | 2-major-version window for removed APIs |
| Integration tests per plugin hook | CI pipeline |
| Schema-first tool definitions | JSON Schema validation on registration |

---

## 13. MVP Milestones

### Milestone M1: Agent-Enabled Chat
**Goal:** Replace direct LLM call with agent loop  
**Deliverables:**
- [x] Agent framework instantiation (exists dormant)
- [ ] Wire agent into chat execution path
- [ ] Agent makes tool calls in loop during conversation
- [ ] 3 built-in tools: `read_file`, `run_command`, `web_search`
- [ ] Agent timeout and error handling
- [ ] Migration of current chat functionality under Agent protocol
- [ ] Tests for agent-tool loop

### Milestone M2: Plugin System
**Goal:** Tools can be registered by plugins  
**Deliverables:**
- [ ] Plugin lifecycle (activate/deactivate)
- [ ] Plugin directory scanning
- [ ] Tool Registry with JSON Schema validation
- [ ] Permission declaration per plugin
- [ ] 1 reference plugin (e.g., file-editor)
- [ ] Plugin manifest schema

### Milestone M3: Skills System
**Goal:** Skills can be installed and activated  
**Deliverables:**
- [ ] Skill directory format specification
- [ ] Skill Registry (discover, validate, activate)
- [ ] Skill marketplace (local-first; remote optional)
- [ ] Skill dependencies and version resolution
- [ ] Skill isolation

### Milestone M4: Workflow Engine
**Goal:** Multi-step workflows execute as DAGs  
**Deliverables:**
- [ ] Workflow definition format (YAML/Python DSL)
- [ ] DAG executor with topological sort
- [ ] Parallel step execution
- [ ] Condition step skipping
- [ ] Workflow observability (logs, traces)
- [ ] GUI workflow editor (low priority, Pro)

### Milestone M5: Multi-Agent Orchestration
**Goal:** Supervisor agent delegates to specialist agents  
**Deliverables:**
- [ ] Supervisor agent type
- [ ] Agent capability matching
- [ ] Delegation protocol
- [ ] Result merging
- [ ] Recursion guard
- [ ] Parallel sub-agent execution

### Milestone M6: Production Hardening
**Goal:** Stable, secure, observable platform  
**Deliverables:**
- [ ] Permission approval UI
- [ ] Tool execution sandbox
- [ ] Audit log
- [ ] Performance benchmarks
- [ ] Documentation: API, plugin dev, skill dev

---

## 14. GitHub Release Milestones

| Release | Version | Focus | Tagline |
|---|---|---|---|
| **Current** | v3.3.0 | Stable desktop assistant | — |
| **Agent Connect** | v4.0.0 | Agent loop + Tool protocol + Plugin lifecycle | "Agents Wake Up" |
| **Skill Era** | v4.1.0 | Skills directory + Skill Registry | "Teach New Tricks" |
| **Workflow** | v4.2.0 | DAG engine + Workflow YAML | "Automate Everything" |
| **Multi-Mind** | v4.3.0 | Supervisor agent + Delegation + Parallel agents | "Many Minds, One Goal" |
| **Secure** | v4.4.0 | Permission system + Sandbox + Approval gates | "Trust but Verify" |
| **API** | v4.5.0 | WebSocket API + Headless mode | "No UI Required" |
| **Simulate** | v4.6.0 | Simulation engine + Dry-run mode | "Safe Exploration" |
| **HardWorkres Core** | v5.0.0 | Distributed agents + Cloud sync | "The Platform" |

---

## 15. Long-Term Architecture Risks

### Risk 1: Plugin API Instability

**Problem:** As the platform evolves, plugin APIs change. Breaking plugins erodes trust.

**Mitigation:**
- Manifest declares `min_core_version` and `max_core_version`
- API deprecation with 2-major-version window
- Automated compatibility testing for marketplace plugins
- Plugin runtime shim for backward compatibility

### Risk 2: Agent Reliability

**Problem:** LLM agents are non-deterministic. A single bad agent decision can corrupt files or leak data.

**Mitigation:**
- Tool-level permissions with user approval
- File system snapshots before destructive operations
- Agent decision audit log (full traceability)
- "Undo" capability via filesystem versioning
- Agent behavior tests in simulation before real execution

### Risk 3: Performance at Scale

**Problem:** Multi-agent workflows with many tool calls can saturate the event loop.

**Mitigation:**
- Agent execution is `asyncio`-based from day one
- Each agent gets its own asyncio task
- Agent pool with configurable max concurrency
- Tool execution has strict timeouts
- Profiling built into the observability layer

### Risk 4: State Consistency in Distributed Mode

**Problem:** With multiple agent workers, memory and workspace state can diverge.

**Mitigation:**
- Command-query separation (CQRS) for state mutations
- Version vectors for conflict detection
- Event sourcing for agent decisions
- Optimistic concurrency with rollback on conflict

### Risk 5: LLM Vendor Lock-in

**Problem:** Agents become dependent on specific provider features (tool calling format, context window size, etc.).

**Mitigation:**
- Provider abstraction layer normalizes differences
- Tool calling is schema-defined, not model-specific
- Agent prompts are provider-agnostic
- Multi-provider eval suite catches regressions
- Community provider plugins reduce dependency on core team

### Risk 6: Security Surface Area

**Problem:** Each plugin, tool, and agent expands the attack surface.

**Mitigation:**
- Plugin approval at install time (user must review permissions)
- Tool execution in restricted environment (container or process jail)
- Network access deny-by-default
- Credential storage in OS keychain, never in config files
- Regular security audit of plugin API surface

---

*End of document. This roadmap is a living design — revisit after each major release to incorporate lessons learned.*
