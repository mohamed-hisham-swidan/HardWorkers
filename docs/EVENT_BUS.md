# HARD WORKERS — Event Bus Specification

**Document:** EVENT_BUS.md  
**Version:** 1.0 (spec)  
**Status:** Draft  
**Supersedes:** ARCHITECTURE.md §4 (Event-Driven Architecture)

---

## Table of Contents

1. [Event Architecture](#1-event-architecture)
2. [Event Lifecycle](#2-event-lifecycle)
3. [Event Schema](#3-event-schema)
4. [Event Metadata](#4-event-metadata)
5. [Event Envelope](#5-event-envelope)
6. [Event Registry](#6-event-registry)
7. [Event Categories](#7-event-categories)
8. [Event Namespaces](#8-event-namespaces)
9. [Event Versioning Strategy](#9-event-versioning-strategy)
10. [Event Routing](#10-event-routing)
11. [Publish/Subscribe Model](#11-publishsubscribe-model)
12. [Channel Model](#12-channel-model)
13. [Topic Hierarchy](#13-topic-hierarchy)
14. [Delivery Guarantees](#14-delivery-guarantees)
15. [Ordering Guarantees](#15-ordering-guarantees)
16. [Event Persistence](#16-event-persistence)
17. [Event Replay](#17-event-replay)
18. [Event Retention](#18-event-retention)
19. [Dead Letter Handling](#19-dead-letter-handling)
20. [Event Filtering](#20-event-filtering)
21. [Event Authorization](#21-event-authorization)
22. [Event Tracing](#22-event-tracing)
23. [Event Metrics](#23-event-metrics)
24. [Plugin Event Hooks](#24-plugin-event-hooks)
25. [Workflow Event Integration](#25-workflow-event-integration)
26. [Agent Event Integration](#26-agent-event-integration)
27. [Future Distributed Migration Path](#27-future-distributed-migration-path)

---

## 1. Event Architecture

### 1.1 Conceptual Model

The Event Bus is a **topic-based pub/sub system** with a **persistent append-only log** at its core. Every event is published to a topic, persisted to the log, then fanned out to subscribers.

```
                    ┌──────────────────────────────────────────┐
                    │               PUBLISHERS                  │
                    │  (Agent Runtime, Workflow Engine,        │
                    │   Plugin System, Tool Registry, UI)      │
                    └────────────────┬─────────────────────────┘
                                     │
                                     │ publish(event)
                                     ▼
                    ┌──────────────────────────────────────────┐
                    │              EVENT BUS                    │
                    │                                          │
                    │  ┌──────────┐  ┌──────────────────────┐  │
                    │  │  Channel   │  │  Event Registry      │  │
                    │  │  Router   │  │  (schema validation)  │  │
                    │  └────┬─────┘  └──────────────────────┘  │
                    │       │                                    │
                    │       ▼                                    │
                    │  ┌──────────────────────┐                 │
                    │  │  Event Store          │                 │
                    │  │  (append-only log)    │                 │
                    │  └──────────────────────┘                 │
                    │       │                                    │
                    │       ▼                                    │
                    │  ┌──────────────────────┐                 │
                    │  │  Fan-Out Engine       │                 │
                    │  │  (match subscribers)  │                 │
                    │  └──────┬───────────────┘                 │
                    └─────────┼─────────────────────────────────┘
                              │
                              │ deliver(event)
                              ▼
                    ┌──────────────────────────────────────────┐
                    │              SUBSCRIBERS                  │
                    │  (Agent Runtime, Workflow Engine,        │
                    │   Plugin Hooks, Observability, UI)       │
                    └──────────────────────────────────────────┘
```

### 1.2 Local Architecture (Phase 1)

```
┌─────────────────────────────────────────────────────────┐
│                     PROCESS BOUNDARY                      │
│                                                           │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────┐    │
│  │ Publisher │───▶│InMemoryChannel│───▶│ Subscriber  │    │
│  │ (sync)    │    │ (asyncio.Queue)│    │ (async cb)  │    │
│  └──────────┘    └──────────────┘    └─────────────┘    │
│                         │                                 │
│                         ▼                                 │
│                  ┌──────────────┐                         │
│                  │ Event Store   │                         │
│                  │ (SQLite)      │                         │
│                  └──────────────┘                         │
└─────────────────────────────────────────────────────────┘
```

### 1.3 Distributed Architecture (Phase 3+)

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Node A    │   │ Node B    │   │ Node C    │
│ Publisher │   │ Publisher │   │ Subscriber│
└─────┬────┘   └─────┬────┘   └─────┬────┘
      │              │              │
      └──────────────┼──────────────┘
                     │
            ┌────────▼────────┐
            │  Message Queue   │
            │ (NATS / Kafka)   │
            │                  │
            │ ┌──────────────┐ │
            │ │  Topics       │ │
            │ │  Partitions   │ │
            │ │  Offsets      │ │
            │ └──────────────┘ │
            └─────────────────┘
```

### 1.4 Core Interfaces

```python
class EventBusProtocol(Protocol):
    """Primary interface for the entire Event Bus."""

    async def publish(
        self,
        topic: str,
        event: EventPayload,
        options: PublishOptions | None = None,
    ) -> EventId: ...

    def subscribe(
        self,
        topic: str,
        handler: EventHandler,
        options: SubscribeOptions | None = None,
    ) -> Subscription: ...

    def unsubscribe(self, subscription: Subscription) -> None: ...

    async def replay(
        self,
        topic: str,
        handler: EventHandler,
        options: ReplayOptions,
    ) -> int: ...  # returns count of replayed events

    async def get_event(
        self,
        event_id: EventId,
    ) -> StoredEvent | None: ...

    async def query_events(
        self,
        query: EventQuery,
    ) -> list[StoredEvent]: ...

    def register_schema(
        self,
        event_type: str,
        schema: EventSchema,
    ) -> None: ...

    def get_schema(
        self,
        event_type: str,
        version: int | None = None,
    ) -> EventSchema | None: ...

    def get_metrics(self) -> EventBusMetricsSnapshot: ...


class EventHandler(Protocol):
    async def __call__(
        self,
        event: EventEnvelope,
    ) -> None: ...


class Subscription:
    id: str
    topic: str
    filter: EventFilter | None
    options: SubscribeOptions
    active: bool

    async def cancel(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
```

---

## 2. Event Lifecycle

Every event progresses through a defined lifecycle:

```
                ┌────────────┐
                │  CREATED    │  ← Event payload assembled by publisher
                └──────┬─────┘
                       │ publish()
                       ▼
                ┌────────────┐
                │ VALIDATED  │  ← Schema validation against Event Registry
                └──────┬─────┘
                  │    │    │
         FAILED   │    │    │ OK
         ◄────────┘    │    │
                       │    ▼
                ┌──────────────┐
                │  ENRICHED    │  ← Envelope added (id, timestamp, trace_id)
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │  PERSISTED   │  ← Written to Event Store
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │   ROUTED     │  ← Topic resolved, channel selected
                └──────┬───────┘
                       ▼
                ┌──────────────┐
                │   FILTERED   │  ← Per-subscription filters applied
                ├──────────────┤
                │   MATCHED    │  ← Subscribers identified
                │   DELIVERED  │  ← Sent to subscriber handler
                └──────┬───────┘
                  │    │    │
         RETRY    │    │    │ SUCCESS
         ◄────────┘    │    │
                       │    ▼
                ┌──────────────┐
                │ ACKNOWLEDGED │  ← Subscriber confirmed processing
                └──────┬───────┘
                       │
                       ▼
                ┌──────────────┐
                │  COMPLETED   │  ← Terminal: event lifecycle done
                └──────────────┘


Dead letter path:
    MAX_RETRIES_EXCEEDED ──▶ DEAD_LETTER (quarantined)
    VALIDATION_FAILED    ──▶ DEAD_LETTER (quarantined)
    ROUTING_FAILED       ──▶ DEAD_LETTER (quarantined)
```

### 2.1 Lifecycle Times

| Phase | Typical Duration (Local) | Typical Duration (Distributed) |
|---|---|---|
| CREATED → VALIDATED | ~0.01ms | ~0.01ms |
| VALIDATED → PERSISTED | ~0.5ms | ~2ms (local SQLite) |
| PERSISTED → ROUTED | ~0.01ms | ~0.5ms |
| ROUTED → DELIVERED | ~0.1ms | ~2ms (network) |
| DELIVERED → ACKNOWLEDGED | async (depends on handler) | async |

### 2.2 Lifecycle Hooks (Plugin Extensibility)

```python
class EventLifecycleHook(Protocol):
    """Plugin can hook into any lifecycle phase."""

    async def on_before_publish(
        self, topic: str, payload: EventPayload
    ) -> EventPayload: ...    # mutate payload before validation

    async def on_after_persist(
        self, envelope: EventEnvelope
    ) -> None: ...             # observe after persistence

    async def on_before_deliver(
        self, envelope: EventEnvelope, subscriber_id: str
    ) -> EventEnvelope: ...    # mutate before delivery (e.g., redact)

    async def on_after_deliver(
        self, envelope: EventEnvelope, subscriber_id: str
    ) -> None: ...             # observe after delivery

    async def on_dead_letter(
        self, envelope: EventEnvelope, reason: str
    ) -> None: ...             # observe dead letter events
```

---

## 3. Event Schema

### 3.1 Event Type Definition

Every event type is registered in the Event Registry with a JSON Schema:

```python
class EventSchema:
    type: str                      # fully qualified: "agent.runtime.started"
    version: int                   # monotonic version number
    description: str
    schema: dict                   # JSON Schema (draft 2020-12)
    examples: list[dict] | None    # example payloads
    deprecated: bool = False
    superseded_by: str | None = None  # type string of newer version
```

### 3.2 Schema Example

```json
{
    "type": "agent.runtime.started",
    "version": 1,
    "description": "Emitted when the Agent Runtime transitions to READY state",
    "schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["agent_type", "invocation_id", "model"],
        "properties": {
            "agent_type": {
                "type": "string",
                "description": "Registered agent type identifier"
            },
            "invocation_id": {
                "type": "string",
                "format": "uuid",
                "description": "Unique invocation identifier"
            },
            "model": {
                "type": "string",
                "description": "LLM model in use"
            },
            "context_size": {
                "type": "integer",
                "minimum": 0,
                "description": "Token count of assembled context"
            }
        }
    },
    "examples": [
        {
            "agent_type": "core.code-reviewer",
            "invocation_id": "0191f5b2-3a7e-7b00-9c8d-ef0123456789",
            "model": "qwen2.5-coder:latest",
            "context_size": 12480
        }
    ]
}
```

### 3.3 Schema Validation Rules

| Rule | Enforcement | Action on Violation |
|---|---|---|
| Required fields present | At publish time | Event rejected → dead letter |
| Field types match schema | At publish time | Event rejected → dead letter |
| No unknown fields (strict mode) | Configurable per topic | Reject or strip |
| String max length | At publish time | Truncate or reject |
| Size limit (max 256KB payload) | At publish time | Event rejected → dead letter |
| Schema evolution rules (see §9) | At publish time | Warning or reject |

### 3.4 Schema Registry API

```python
class SchemaRegistryProtocol(Protocol):
    def register(self, schema: EventSchema) -> None:
        """Register an event type schema. Version must be new."""

    def get(self, event_type: str, version: int | None = None) -> EventSchema:
        """Get schema. If version is None, return latest."""

    def list_types(self, namespace: str | None = None) -> list[EventSchema]:
        """List all registered event types."""

    def validate(
        self, event_type: str, payload: dict, version: int | None = None
    ) -> ValidationResult:
        """Validate a payload against its schema."""

    def get_migration(
        self, event_type: str, from_version: int, to_version: int
    ) -> SchemaMigration | None:
        """Get migration transform between versions."""
```

---

## 4. Event Metadata

### 4.1 Metadata Fields

Every event carries metadata separate from its payload. Metadata is system-controlled (publisher cannot set arbitrary metadata fields, only `custom`).

```python
class EventMetadata:
    # Identity
    event_id: EventId              # globally unique (ULID or UUIDv7)
    event_type: str                # fully qualified type string
    version: int                   # schema version used

    # Causality
    parent_event_id: str | None    # event that caused this event (causal chain)
    correlation_id: str | None     # groups related events across boundaries
    causation_seq: int             # sequence number within causation chain

    # Origin
    source: str                    # component: "agent_runtime", "workflow_engine", etc.
    source_instance_id: str        # unique instance of the source component
    publisher_id: str              # plugin or system identifier
    workspace_id: str | None       # workspace context
    user_id: str | None            # user context

    # Timing
    created_at: datetime           # when the event was created (publisher wall clock)
    published_at: datetime | None  # when the event entered the bus

    # Distributed Tracing
    trace_id: str                  # root trace ID (W3C Trace Context)
    span_id: str                   # current span ID
    trace_flags: int               # W3C trace flags (0x01 = sampled)

    # Routing
    topic: str                     # resolved topic
    routing_key: str               # partition routing key
    priority: int = 0              # 0 (normal) to 10 (critical)

    # Custom (publisher-controlled)
    custom: dict[str, str]         # arbitrary key-value pairs (strings only)
```

### 4.2 Auto-Generated Fields

| Field | Generated By | When |
|---|---|---|
| `event_id` | Event Bus | After validation, before persistence |
| `trace_id` | Event Bus (or propagated from publisher) | At envelope creation |
| `span_id` | Event Bus | At envelope creation |
| `published_at` | Event Bus | At persistence |
| `causation_seq` | Event Bus | Auto-increment per causal chain |
| `source_instance_id` | Event Bus (from config) | On bus initialization |

---

## 5. Event Envelope

### 5.1 Envelope Structure

The envelope wraps the payload with metadata and provides transport-level information.

```python
class EventEnvelope:
    """The complete unit of event data flowing through the bus."""

    # System-controlled
    id: EventId                    # globally unique event ID
    metadata: EventMetadata

    # Payload (schema-validated event data)
    payload: dict                  # typed per event_type + version

    # Transport
    content_type: str = "application/json"  # serialization format
    content_encoding: str = "utf-8"
    size_bytes: int                # computed serialized size

    # Delivery tracking
    delivery_attempts: int = 0
    last_delivery_at: datetime | None = None
    delivery_errors: list[str] = []
```

### 5.2 Serialization Format

| Field | Local (Phase 1) | Distributed (Phase 3+) |
|---|---|---|
| Serialization | `orjson` (binary JSON) | `orjson` or Protocol Buffers |
| Envelope wrapper | Python dataclass + JSON | Protocol Buffers `EventEnvelope` message |
| Payload | Raw dict | JSON bytes or protobuf `Any` |
| Schema resolution | In-memory dict | Schema Registry service call |

### 5.3 Envelope Size Limits

| Limit | Value | Enforcement |
|---|---|---|
| Max payload size | 256 KB | Hard reject |
| Max metadata size | 4 KB | Hard reject |
| Max custom metadata keys | 16 | Hard reject |
| Max event size | 260 KB | Hard reject |

---

## 6. Event Registry

### 6.1 Registry Structure

The Event Registry is the central catalog of all event types in the system. It serves as schema authority, discovery service, and documentation source.

```python
class EventRegistry:
    schemas: dict[str, dict[int, EventSchema]]   # type → version → schema
    namespaces: dict[str, NamespaceInfo]          # registered namespaces
    type_index: dict[str, str]                    # type → namespace (reverse lookup)
```

### 6.2 Registration Flow

```
Plugin/core registers a schema:
         │
         ▼
┌─────────────────────────────────────┐
│  1. Validate schema (is valid JSON  │
│     Schema? Has all required fields?)│
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  2. Check namespace ownership       │
│     (plugin can only register in    │
│      its own namespace)             │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  3. Check version rules             │
│     a. First registration → v1      │
│     b. Backward-compatible → vN+1   │
│     c. Breaking change → new type   │
│        (not new version)            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  4. Store in registry               │
│  5. Emit `schema.registered` event  │
└─────────────────────────────────────┘
```

### 6.3 Schema Validation at Publish Time

```python
async def publish(self, topic: str, event: EventPayload, options=None) -> EventId:
    # 1. Resolve event type from payload (event["type"])
    event_type = event["type"]

    # 2. Lookup schema from registry
    schema = self._registry.get(event_type)

    # 3. Validate payload
    result = self._registry.validate(event_type, event)
    if not result.valid:
        self._dead_letter(EventEnvelope(...), reason=f"Validation failed: {result.errors}")
        raise ValidationError(result.errors)

    # 4. Proceed with enrichment, persistence, routing...
```

---

## 7. Event Categories

### 7.1 Category Taxonomy

Events are categorized to enable topic-based routing and subscriber filtering.

```python
class EventCategory:
    """Broad functional category of an event."""
    SYSTEM = "system"           # Runtime lifecycle events
    AGENT = "agent"             # Agent lifecycle and execution events
    TOOL = "tool"               # Tool execution events
    WORKFLOW = "workflow"       # Workflow engine events
    CONTEXT = "context"         # Context management events
    MEMORY = "memory"           # Memory operation events
    PLUGIN = "plugin"           # Plugin lifecycle events
    PERMISSION = "permission"   # Permission decision events
    FILE = "file"               # File system operation events
    LLM = "llm"                 # LLM call events
    USER = "user"               # User interaction events
    INTERNAL = "internal"       # Event bus internal events
    CUSTOM = "custom"           # Plugin-defined custom events
```

### 7.2 Category-to-Topic Mapping

| Category | Topic Pattern | Examples |
|---|---|---|
| `SYSTEM` | `system.>` | `system.runtime.ready`, `system.shutdown` |
| `AGENT` | `agent.>` | `agent.created`, `agent.started`, `agent.completed` |
| `TOOL` | `tool.>` | `tool.execution.started`, `tool.execution.completed` |
| `WORKFLOW` | `workflow.>` | `workflow.node.started`, `workflow.node.completed` |
| `LLM` | `llm.>` | `llm.call.started`, `llm.call.completed` |
| `PLUGIN` | `plugin.>` | `plugin.activated`, `plugin.deactivated` |
| `USER` | `user.>` | `user.message.sent`, `user.approval.granted` |

### 7.3 Category Governance

| Category | Who Can Publish | Who Can Subscribe | Requires Registration |
|---|---|---|---|
| `SYSTEM` | Core runtime only | Any | Yes (core) |
| `AGENT` | Agent Runtime, Plugins | Any | Yes |
| `TOOL` | Tool Registry, Plugins | Any | Yes |
| `WORKFLOW` | Workflow Engine | Any | Yes |
| `LLM` | Agent Runtime only | Any | Yes |
| `PLUGIN` | Plugin System, Plugins themselves | Any | Yes |
| `USER` | UI, API layer | Any | Yes |
| `CUSTOM` | Plugin only (own namespace) | Any | Yes |

---

## 8. Event Namespaces

### 8.1 Namespace Model

Namespaces provide isolation and ownership. Every event type must belong to exactly one namespace.

```python
class Namespace:
    id: str                       # e.g., "core", "plugin.git", "plugin.slack"
    owner: str                    # system component or plugin ID
    event_types: list[str]        # event types registered in this namespace
    created_at: datetime
    protected: bool               # core namespaces cannot be modified by plugins
```

### 8.2 Reserved Namespaces

| Namespace | Owner | Purpose |
|---|---|---|
| `core` | System | Core runtime events (agent, tool, workflow, system) |
| `user` | System | User interaction events |
| `internal` | System | Event bus internal events |
| `plugin.*` | Per plugin | Plugin-specific events (e.g., `plugin.git.pull_request.opened`) |

### 8.3 Namespace Resolution

Event types use dot notation: `{namespace}.{category}.{subcategory}.{action}`

```
core.system.runtime.ready
core.agent.started
core.tool.execution.completed
plugin.git.pull_request.opened
plugin.slack.message.received
```

Resolution rules:
1. First segment = namespace
2. If namespace is `core` or `user` or `internal`, it's system-managed
3. If namespace starts with `plugin.`, it's plugin-managed
4. Plugin must be active to register/modify its namespace
5. Plugin namespace matches plugin ID exactly (e.g., plugin ID `git` → namespace `plugin.git`)

---

## 9. Event Versioning Strategy

### 9.1 Versioning Rules

```python
class VersioningStrategy:
    """
    Rules for event schema evolution:

    BACKWARD-COMPATIBLE (new version):
    - Adding optional fields: SAFE
    - Adding required fields: BREAKING
    - Removing fields: BREAKING
    - Renaming fields: BREAKING
    - Relaxing constraints (wider enum, wider range): SAFE
    - Tightening constraints: BREAKING
    - Changing field type: BREAKING

    FORWARD-COMPATIBLE (new version):
    - Subscribers using older schema ignore unknown fields: SAFE
    """
```

### 9.2 Schema Evolution

```python
@dataclass
class SchemaMigration:
    from_version: int
    to_version: int
    transform: Callable[[dict], dict]   # payload transformation function
    backward_compatible: bool
    forward_compatible: bool
```

**Rules:**
1. **Backward-compatible changes** → increment version (v1 → v2)
   - New subscribers see v2, old subscribers ignore unknown fields
   - Old publishers continue producing v1 (bus auto-upgrades if possible)

2. **Breaking changes** → new event type (not new version)
   - `user.created.v1` → `user.created.v2` is NOT allowed for breaking changes
   - Instead: `user.created` (v1, deprecated) → `user.registered` (new type)

3. **Deprecation window:** 2 major versions or 6 months, whichever is longer
   - Deprecated events still route but emit warnings in logs

4. **Version in topic vs type:**
   - Topic name does NOT include version
   - Version is in the envelope metadata and schema registry
   - Subscribers declare which version they accept: `accepts: [1, 2]`

### 9.3 Publisher/Subscriber Version Negotiation

```python
class SubscribeOptions:
    topic: str
    handler: EventHandler
    accepts_versions: list[int] | None = None  # None = latest only
    accepts_since_version: int | None = None   # 1 = all versions
```

- If subscriber declares `accepts_versions: [1, 2]`, and an event with version 3 arrives, the bus converts it backward using the stored migration (if available)
- If no migration exists, the subscriber doesn't receive that event

---

## 10. Event Routing

### 10.1 Routing Model

```
publish(topic, payload)
    │
    ▼
┌─────────────────────────────────┐
│  Topic Resolution                │
│  ├── Parse topic string          │
│  ├── Resolve wildcard (if any)   │
│  └── Validate topic exists       │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  Partition Assignment            │
│  ├── Extract routing_key         │
│  │   from metadata               │
│  └── Determine partition:        │
│      hash(routing_key) % N       │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  Subscriber Resolution           │
│  ├── Find all subscriptions      │
│  │   matching topic + filter     │
│  └── Group by delivery_mode      │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  Distribution                    │
│  ├── Fan-out to all subscribers  │
│  └── Each subscriber gets own    │
│      delivery queue              │
└─────────────────────────────────┘
```

### 10.2 Routing Key

The routing key determines partition assignment and ordering:

| Use Case | Routing Key | Example |
|---|---|---|
| Agent events | `invocation_id` | All events for one agent go to same partition |
| Workflow events | `workflow_run_id` | All events for one workflow in order |
| User events | `user_id` | All events for one user in order |
| Tool events | `tool_id` | Per-tool ordering |
| System events | `"system"` | Single partition (global order) |

```python
class PublishOptions:
    routing_key: str | None = None  # if None, bus generates one
    partition: int | None = None    # explicit partition (advanced)
    priority: int = 0
```

---

## 11. Publish/Subscribe Model

### 11.1 Publish API

```python
class EventBusProtocol(Protocol):
    async def publish(
        self,
        topic: str,
        payload: EventPayload,
        options: PublishOptions | None = None,
    ) -> EventId:
        """
        Publish an event to a topic.

        Args:
            topic: Topic string (e.g., "agent.started")
            payload: Event payload dict (must include "type" field)
            options: Publishing options (routing_key, priority, etc.)

        Returns:
            EventId: Globally unique event identifier

        Raises:
            TopicNotFoundError: Topic does not exist
            ValidationError: Payload fails schema validation
            EventTooLargeError: Payload exceeds size limit
            PublishDeniedError: Publisher not authorized
        """
```

### 11.2 Subscribe API

```python
class EventBusProtocol(Protocol):
    def subscribe(
        self,
        topic: str,
        handler: EventHandler,
        options: SubscribeOptions | None = None,
    ) -> Subscription:
        """
        Subscribe to a topic.

        Args:
            topic: Topic string (exact or wildcard)
            handler: Async callable receiving EventEnvelope
            options: Subscription options (filter, buffer_size, etc.)

        Returns:
            Subscription: Handle for unsubscribing/pausing/resuming

        Raises:
            SubscribeDeniedError: Subscriber not authorized
        """

class SubscribeOptions:
    # Matching
    filter: EventFilter | None = None    # content-based filter

    # Delivery
    buffer_size: int = 100               # max queued events for this subscriber
    backpressure: str = "block"          # "block" | "drop_oldest" | "drop_newest"
    delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE

    # Version acceptance
    accepts_since_version: int = 1
    accepts_versions: list[int] | None = None  # exact list, None = all

    # Observability
    subscriber_name: str | None = None   # human-readable name
    metrics_enabled: bool = True
```

### 11.3 Subscription Matching

```
Topics are matched using MQTT-style wildcards:
  - "+" matches exactly one level: "agent.+" matches "agent.started" but not "agent.runtime.started"
  - ">" matches one or more levels: "agent.>" matches everything under "agent."

Examples:
  subscribe("agent.started")    → exact match
  subscribe("agent.+")          → matches "agent.started", "agent.completed", but not "agent.runtime.started"
  subscribe("agent.>")          → matches all agent events at any depth
  subscribe("core.>")           → matches all core events
  subscribe("plugin.git.>")     → matches all events from the git plugin
  subscribe(">")                → matches ALL events (use sparingly)
```

### 11.4 Subscription Lifecycle

```
CREATED (subscribe() called)
    │
    ▼
ACTIVE  ←────┐
    │         │
    │ pause() │ resume()
    ▼         │
PAUSED ───────┘
    │
    │ cancel()
    ▼
CANCELLED
```

---

## 12. Channel Model

### 12.1 Channel Definition

A channel is an isolated event pipeline with its own buffering, delivery guarantees, and lifecycle. Channels are the unit of resource management — each channel has a configurable buffer, concurrency, and backpressure policy.

```python
class Channel:
    id: str
    topic_pattern: str              # which topics route to this channel
    buffer_size: int                # max in-flight events
    concurrency: int                # max concurrent handler invocations
    delivery_mode: DeliveryMode
    backpressure: BackpressureStrategy
    subscribers: list[Subscription]

class BackpressureStrategy(Enum):
    BLOCK = "block"                 # block publisher until space available
    DROP_OLDEST = "drop_oldest"     # drop oldest undelivered event
    DROP_NEWEST = "drop_newest"     # drop newest incoming event
    DROP_DEAD_LETTER = "dead_letter" # send overflow to dead letter
```

### 12.2 Channel Types

| Channel Type | Use Case | Buffer | Concurrency | Delivery |
|---|---|---|---|---|
| **System** | Runtime lifecycle events | 1000 | 1 | At-least-once |
| **Agent Lifecycle** | Agent state transitions | 10000 | 4 | At-least-once |
| **Agent Execution** | Tool calls, LLM calls, thinking updates | 50000 | 8 | At-most-once (streaming OK to drop) |
| **Tool Execution** | Tool calls | 50000 | 16 | At-least-once |
| **Workflow** | Workflow state transitions | 10000 | 4 | At-least-once |
| **Observability** | Metrics, logs, traces | 50000 | 2 | At-most-once (observability can drop) |
| **Plugin** | Plugin-defined events | 5000 | 2 | Per-plugin config |

### 12.3 Channel Configuration

```yaml
channels:
  agent.system:
    topic_pattern: "system.>"
    buffer_size: 1000
    concurrency: 1
    delivery_mode: at_least_once
    backpressure: block

  agent.execution:
    topic_pattern: "agent.>"
    buffer_size: 50000
    concurrency: 8
    delivery_mode: at_most_once
    backpressure: drop_oldest

  tool.execution:
    topic_pattern: "tool.>"
    buffer_size: 50000
    concurrency: 16
    delivery_mode: at_least_once
    backpressure: block

  observability:
    topic_pattern: "llm.> internal.>"
    buffer_size: 50000
    concurrency: 2
    delivery_mode: at_most_once
    backpressure: drop_newest
```

---

## 13. Topic Hierarchy

### 13.1 Standard Topic Tree

```
core
├── system
│   ├── system.runtime
│   │   ├── system.runtime.ready
│   │   ├── system.runtime.paused
│   │   ├── system.runtime.shutting_down
│   │   └── system.runtime.stopped
│   └── system.config
│       └── system.config.changed
├── agent
│   ├── agent.lifecycle
│   │   ├── agent.created
│   │   ├── agent.hydrated
│   │   ├── agent.started
│   │   ├── agent.completed
│   │   ├── agent.cancelled
│   │   ├── agent.timed_out
│   │   └── agent.failed
│   ├── agent.execution
│   │   ├── agent.thinking                 # streaming LLM token
│   │   ├── agent.tool_request
│   │   ├── agent.tool_result
│   │   └── agent.final_answer
│   └── agent.approval
│       ├── agent.approval_required
│       ├── agent.approval_granted
│       └── agent.approval_denied
├── tool
│   ├── tool.execution
│   │   ├── tool.execution.started
│   │   ├── tool.execution.progress
│   │   ├── tool.execution.completed
│   │   └── tool.execution.failed
│   └── tool.registry
│       ├── tool.registered
│       └── tool.unregistered
├── workflow
│   ├── workflow.lifecycle
│   │   ├── workflow.started
│   │   ├── workflow.completed
│   │   ├── workflow.failed
│   │   └── workflow.cancelled
│   ├── workflow.node
│   │   ├── workflow.node.started
│   │   ├── workflow.node.completed
│   │   └── workflow.node.failed
│   └── workflow.checkpoint
│       └── workflow.checkpoint.saved
├── llm
│   ├── llm.call
│   │   ├── llm.call.started
│   │   ├── llm.call.completed
│   │   └── llm.call.failed
│   └── llm.token
│       └── llm.token.streamed              # high-volume, for UI
├── permission
│   ├── permission.check
│   │   ├── permission.granted
│   │   └── permission.denied
│   └── permission.policy
│       └── permission.policy.changed
├── context
│   ├── context.assembled
│   └── context.overflow
├── memory
│   ├── memory.read
│   └── memory.written
├── file
│   ├── file.read
│   ├── file.written
│   └── file.deleted
└── user
    ├── user.message
    │   ├── user.message.sent
    │   └── user.message.received
    └── user.action
        ├── user.action.approved
        └── user.action.rejected

plugin
└── {plugin_id}
    └── ...  (plugin-defined topic tree)

internal
├── internal.bus
│   ├── internal.bus.backpressure
│   ├── internal.bus.dead_letter
│   └── internal.bus.subscriber_error
└── internal.schema
    ├── internal.schema.registered
    └── internal.schema.deprecated
```

### 13.2 Topic Creation

Topics are created implicitly on first publish or explicitly via configuration:

```python
class TopicConfig:
    path: str                      # topic path
    description: str
    schema: str                    # event type for this topic (if single-type)
    retention: RetentionPolicy     # how long to keep
    max_size_bytes: int | None     # max event size for this topic
    required_authorization: bool   # require auth to publish/subscribe
```

- **Implicit creation:** First `publish()` to a topic creates it automatically
- **Explicit creation:** `register_topic(TopicConfig(...))` for governance
- **Implicit topics** inherit the channel's retention and delivery settings

---

## 14. Delivery Guarantees

### 14.1 Delivery Levels

```python
class DeliveryMode(Enum):
    AT_MOST_ONCE = "at_most_once"       # fire and forget
    AT_LEAST_ONCE = "at_least_once"     # retry on failure
    EXACTLY_ONCE = "exactly_once"       # deduplication + idempotent handler
```

| Mode | Guarantee | Use Case | Cost |
|---|---|---|---|
| `AT_MOST_ONCE` | Event delivered 0 or 1 times | Streaming tokens, metrics, logs | Lowest latency |
| `AT_LEAST_ONCE` | Event delivered 1+ times (retry on failure) | Agent lifecycle, tool results, workflow state | Moderate |
| `EXACTLY_ONCE` | Event delivered exactly 1 time | Payment/credit operations, critical state changes | Highest overhead |

### 14.2 Delivery Behavior

```python
async def _deliver_to_subscriber(
    self, envelope: EventEnvelope, subscription: Subscription
) -> DeliveryResult:
    """
    AT_MOST_ONCE:
        - Fire handler
        - If handler raises: log and ignore
        - No retry

    AT_LEAST_ONCE:
        - Fire handler
        - If handler raises: retry up to max_delivery_attempts
        - Retry with exponential backoff (100ms, 500ms, 2s, 10s)
        - If all retries exhausted: move to dead letter

    EXACTLY_ONCE:
        - Check deduplication cache (event_id + subscriber_id)
        - If already processed: acknowledge silently
        - If new: process handler
        - Store deduplication record after successful processing
        - On failure: retry same as AT_LEAST_ONCE
    """
```

### 14.3 Delivery Configuration

```python
class DeliveryConfig:
    mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    max_delivery_attempts: int = 3
    retry_backoff_base: float = 0.1        # seconds
    retry_backoff_max: float = 30.0
    retry_backoff_jitter: float = 0.1
    deduplication_ttl_seconds: int = 3600  # for EXACTLY_ONCE
```

---

## 15. Ordering Guarantees

### 15.1 Ordering Model

```python
class OrderingScope(Enum):
    NO_ORDERING = "no_ordering"                        # best-effort order
    PER_PARTITION = "per_partition"                    # ordered within partition
    PER_ROUTING_KEY = "per_routing_key"                # ordered per routing key
    GLOBAL = "global"                                  # total order (single partition)
```

| Scope | Guarantee | Throughput | Use Case |
|---|---|---|---|
| `NO_ORDERING` | No ordering guarantee | Highest | Metrics, logs, streaming tokens |
| `PER_PARTITION` | Ordered within partition | High | Agent events (per agent in order) |
| `PER_ROUTING_KEY` | Ordered per routing key | High (many keys) | User events (per user in order) |
| `GLOBAL` | Total order | Lowest | System events, audit trail |

### 15.2 Ordering Implementation (Local)

```python
class InMemoryOrderedChannel:
    """
    Uses an asyncio.Queue per partition key.
    Events with the same routing_key go to the same queue.
    Each queue is consumed sequentially by a single task.
    """

    _queues: dict[str, asyncio.Queue[EventEnvelope]]  # routing_key → queue
    _consumers: dict[str, asyncio.Task]                # routing_key → consumer task

    async def publish(self, envelope: EventEnvelope):
        key = envelope.metadata.routing_key or envelope.metadata.event_id
        queue = self._get_or_create_queue(key)
        await queue.put(envelope)

    async def _consume(self, routing_key: str):
        queue = self._queues[routing_key]
        while True:
            envelope = await queue.get()
            await self._deliver_to_subscribers(envelope)
```

### 15.3 Ordering Implementation (Distributed)

```python
class DistributedOrderedChannel:
    """
    Uses a partitioned topic in the message queue.
    routing_key hash determines partition.
    Subscribers consume partitions in order.
    Single subscriber per partition group (consumer group).
    """
    # Kafka: topic with N partitions, keyed by routing_key
    # NATS: subject with N queues, keyed by routing_key
```

---

## 16. Event Persistence

### 16.1 Event Store Schema

All events are persisted to the Event Store — an append-only log.

```sql
-- Local SQLite schema
CREATE TABLE event_store (
    event_id        TEXT PRIMARY KEY,       -- ULID
    event_type      TEXT NOT NULL,          -- fully qualified type
    event_version   INTEGER NOT NULL,
    topic           TEXT NOT NULL,
    routing_key     TEXT,
    source          TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    correlation_id  TEXT,
    parent_event_id TEXT,
    payload         TEXT NOT NULL,          -- JSON
    metadata_json   TEXT NOT NULL,          -- full metadata as JSON
    created_at      TEXT NOT NULL,          -- ISO 8601
    published_at    TEXT NOT NULL,          -- ISO 8601
    size_bytes      INTEGER NOT NULL
);

CREATE INDEX idx_event_store_topic ON event_store(topic, published_at);
CREATE INDEX idx_event_store_type ON event_store(event_type, published_at);
CREATE INDEX idx_event_store_trace ON event_store(trace_id);
CREATE INDEX idx_event_store_correlation ON event_store(correlation_id);
CREATE INDEX idx_event_store_routing ON event_store(routing_key, published_at);
```

### 16.2 Write Pattern

```
publish()
    │
    ├── Validate payload
    ├── Enrich envelope
    ├── INSERT INTO event_store (synchronous commit)
    ├── Route to channel
    └── Deliver to subscribers
```

**Important:** Persistence happens BEFORE delivery. This guarantees that even if delivery fails, the event is never lost.

### 16.3 Persistence Guarantees

| Setting | Behavior | Performance |
|---|---|---|
| `synchronous` | `fsync()` on every write | Slowest, safest |
| `async` | Write to OS buffer, `fsync()` every 100ms | Fast, 100ms window of data loss |
| `memory` | No persistence (in-memory only) | Fastest, no durability |

For local-first: `async` by default, `synchronous` for critical topics (`system.>`, `workflow.>`)

---

## 17. Event Replay

### 17.1 Replay API

```python
class EventBusProtocol(Protocol):
    async def replay(
        self,
        topic: str,
        handler: EventHandler,
        options: ReplayOptions,
    ) -> int:
        """
        Replay persisted events to a handler.

        Args:
            topic: Topic filter (exact or wildcard)
            handler: Handler receiving replayed events
            options: Replay range and behavior

        Returns:
            Number of events replayed
        """

class ReplayOptions:
    # Time range
    start_time: datetime | None
    end_time: datetime | None

    # Sequence range
    start_sequence: int | None       # global sequence number (future)
    end_sequence: int | None

    # Filtering
    event_types: list[str] | None    # only these event types
    routing_keys: list[str] | None   # only these routing keys
    correlation_id: str | None       # only this correlation chain

    # Behavioral
    replay_speed: float = 1.0        # 0 = as fast as possible
    delivery_mode: DeliveryMode = DeliveryMode.AT_LEAST_ONCE
    preserve_original_timestamps: bool = True

    # Completion
    on_complete: Callable[[int], Awaitable[None]] | None = None
```

### 17.2 Replay Use Cases

| Use Case | Topic | Replay Range | Notes |
|---|---|---|---|
| **Simulation** | `agent.>` | Full session | Deterministic replay of agent interactions |
| **Debugging** | Any | Time range | Reproduce issue from events |
| **Audit** | `permission.>` | Full range | Security audit trail |
| **Recovery** | `workflow.>` | After checkpoint | Resume failed workflow |
| **Catch-up** | `agent.execution.>` | Since last disconnect | New subscriber catches up |

### 17.3 Test Mode (Deterministic Replay)

```python
class TestModeEventBus:
    """
    For testing and simulation:
    - Records all published events in memory
    - Can replay at will
    - Deterministic: same events, same order, every time
    - No external dependencies (no SQLite, no network)
    """
    recorded_events: list[EventEnvelope]

    async def publish(self, topic, payload, options=None) -> EventId:
        envelope = self._build_envelope(topic, payload, options)
        self.recorded_events.append(envelope)
        return envelope.id

    async def replay(self, handler, options=None) -> int:
        count = 0
        for envelope in self.recorded_events:
            if self._matches(options, envelope):
                await handler(envelope)
                count += 1
        return count

    def clear(self) -> None:
        """Reset for next test."""
        self.recorded_events.clear()
```

---

## 18. Event Retention

### 18.1 Retention Policies

```python
class RetentionPolicy:
    max_age_seconds: int | None = 86400 * 7    # default: 7 days
    max_count: int | None = 1000000             # max events per topic
    max_size_bytes: int | None = 10 * 1024**3  # 10 GB per topic
    compression: bool = True                    # compress archived events
    archival: bool = False                      # move to cold storage instead of delete
```

### 18.2 Policy by Topic Category

| Topic Category | Retention | Rationale |
|---|---|---|
| `system.>` | 90 days | System events are rare but important for debugging |
| `agent.lifecycle.>` | 30 days | Agent state transitions |
| `agent.execution.>` | 7 days | Execution details for debugging |
| `agent.thinking` | 1 hour | Streaming tokens — ephemeral |
| `tool.execution.>` | 30 days | Tool execution audit |
| `llm.>` | 7 days | LLM call tracking |
| `permission.>` | 90 days | Security audit requirement |
| `workflow.>` | 90 days | Workflow execution history |
| `internal.>` | 7 days | Bus diagnostics |

### 18.3 Retention Enforcement

```
┌───────────────────────────────────┐
│  Periodic Retention Sweep          │
│  (runs every 5 minutes)            │
│                                    │
│  For each topic:                   │
│  1. Query events older than        │
│     max_age_seconds                │
│  2. If archival enabled: move to   │
│     cold storage (compressed JSON) │
│  3. If not: DELETE from event_store│
│  4. If max_count exceeded:         │
│     DELETE oldest events           │
│  5. If max_size exceeded:          │
│     DELETE oldest events           │
└───────────────────────────────────┘
```

---

## 19. Dead Letter Handling

### 19.1 Dead Letter Sources

```python
class DeadLetterReason(Enum):
    VALIDATION_FAILED = "validation_failed"
    DELIVERY_FAILED = "delivery_failed"           # max retries exceeded
    BACKPRESSURE_DROPPED = "backpressure_dropped"
    ROUTING_FAILED = "routing_failed"             # no matching channel
    AUTHORIZATION_DENIED = "authorization_denied"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    SCHEMA_NOT_FOUND = "schema_not_found"
    SUBSCRIPTION_NOT_FOUND = "subscription_not_found"
    HANDLER_ERROR = "handler_error"              # unhandled exception in handler
```

### 19.2 Dead Letter Store

```sql
CREATE TABLE dead_letter_queue (
    dlq_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL,
    reason          TEXT NOT NULL,           -- DeadLetterReason
    error_message   TEXT,
    error_trace     TEXT,
    failed_at       TEXT NOT NULL,           -- ISO 8601
    retry_count     INTEGER DEFAULT 0,
    envelope_json   TEXT NOT NULL,           -- full serialized envelope
    status          TEXT DEFAULT 'pending'   -- pending | reprocessed | ignored
);

CREATE INDEX idx_dlq_status ON dead_letter_queue(status, failed_at);
```

### 19.3 Dead Letter Lifecycle

```
Event → Dead Letter
    │
    ▼
┌──────────────────┐
│  DLQ (pending)    │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
  Manual     Auto-reprocess
  review     (configurable)
    │         │
    │         ▼
    │    ┌──────────────────┐
    │    │ Republish event   │
    │    │ (increment retry) │
    │    └────────┬─────────┘
    │             │
    ├── success → ✓ (delete from DLQ)
    └── fail    → return to DLQ (increment retry_count)
                    │
                    ▼
            Max auto-reprocesses exceeded → notification to admin
```

### 19.4 Dead Letter API

```python
class DeadLetterProtocol(Protocol):
    async def list(
        self,
        status: str | None = None,
        reason: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DeadLetterEntry]: ...

    async def reprocess(
        self, dlq_id: int
    ) -> bool: ...

    async def reprocess_all(
        self, filters: dict | None = None
    ) -> int: ...   # number reprocessed

    async def ignore(
        self, dlq_id: int
    ) -> None: ...

    async def get_stats(self) -> DeadLetterStats:
        """Return counts by reason and status."""
```

---

## 20. Event Filtering

### 20.1 Subscription Filters

Subscribers can apply content-based filters to reduce noise:

```python
class EventFilter:
    """Content-based filter applied before delivery."""

    # Simple equality filter
    eq: dict[str, Any] | None = None        # {"event_type": "agent.started"}

    # Pattern match filter
    pattern: dict[str, str] | None = None   # {"agent_type": "core.*"}

    # Numeric comparison filter
    range: dict[str, RangeFilter] | None = None  # {"context_size": {"gte": 1000, "lt": 50000}}

    # Set membership filter
    in_filter: dict[str, list[Any]] | None = None  # {"status": ["completed", "failed"]}

    # Existence filter
    exists: list[str] | None = None          # ["error.code"]

    # Compound logic
    logical: str | None = None               # "and" | "or"

    # Sub-filters for compound logic
    filters: list["EventFilter"] | None = None

    # Custom filter function (plugin-defined, local only)
    custom: Callable[[EventEnvelope], bool] | None = None
```

### 20.2 Filter Example

```python
# Subscribe to all agent failures for a specific agent type
bus.subscribe(
    topic="agent.>",
    handler=my_handler,
    options=SubscribeOptions(
        filter=EventFilter(
            logical="and",
            filters=[
                EventFilter(eq={"event_type": "agent.failed"}),
                EventFilter(pattern={"agent_type": "core.code-reviewer"}),
            ]
        )
    )
)
```

### 20.3 Filter Evaluation

Filters are evaluated server-side (in the bus) before delivery. This prevents subscribers from receiving events they don't need and reduces handler invocations.

**Performance guarantee:** Filter evaluation must complete in < 100μs for simple filters, < 1ms for compound filters. Filters that exceed this may be rejected.

---

## 21. Event Authorization

### 21.1 Authorization Model

Every publish and subscribe operation is subject to authorization:

```python
class EventAuthorization:
    """Who can publish/subscribe to which topics."""

    # Topic-level permissions
    publish_permissions: dict[str, list[str]]       # topic → [publisher_ids]
    subscribe_permissions: dict[str, list[str]]     # topic → [subscriber_ids]

    # Default policies
    default_publish: str = "deny"                   # "allow" | "deny"
    default_subscribe: str = "allow"                # "allow" | "deny"
```

### 21.2 Authorization Check

```python
async def _check_publish_authorization(
    self, topic: str, publisher_id: str
) -> bool:
    # 1. Check explicit permissions
    if topic in self._auth.publish_permissions:
        return publisher_id in self._auth.publish_permissions[topic]

    # 2. Check wildcard permissions
    for pattern, publishers in self._auth.publish_permissions.items():
        if self._topic_matches(pattern, topic):
            if publisher_id in publishers:
                return True

    # 3. Fall back to default
    return self._auth.default_publish == "allow"


async def _check_subscribe_authorization(
    self, topic: str, subscriber_id: str
) -> bool:
    # Same logic as publish
    ...
```

### 21.3 Authorization by Component

| Component | Can Publish To | Can Subscribe To |
|---|---|---|
| Agent Runtime | `system.>`, `agent.>`, `llm.>`, `tool.>` | `agent.>`, `user.>`, `internal.>` |
| Tool Registry | `tool.>`, `permission.>` | `agent.>`, `tool.>`, `internal.>` |
| Workflow Engine | `workflow.>` | `agent.>`, `tool.>`, `workflow.>`, `user.>` |
| Plugin | Own namespace (`plugin.{id}.>`), `agent.>` | Any non-`internal.>` topic |
| UI | `user.>` | `agent.>`, `workflow.>`, `tool.>`, `llm.token.>` |

### 21.4 System vs Plugin Trust Levels

| Level | Type | Authorization |
|---|---|---|
| `SYSTEM` | Core runtime components | Full access (all topics) |
| `TRUSTED` | First-party plugins | Own namespace + subscribed topics |
| `SANDBOXED` | Third-party plugins | Own namespace only, explicit grants |
| `OBSERVER` | Monitoring/UI | Subscribe-only, no publish |

---

## 22. Event Tracing

### 22.1 Trace Context Propagation

Every event carries W3C Trace Context:

```python
class TraceContext:
    trace_id: str        # 16-byte hex (32 hex chars)
    parent_span_id: str  # 8-byte hex (16 hex chars)
    span_id: str         # 8-byte hex (16 hex chars)
    trace_flags: int     # 0x01 = sampled
    tracestate: str      # vendor-specific trace data
```

### 22.2 Causality Chain

```
User clicks "Run Code Review"
    │
    ▼
event A: user.action.requested           ← span 1 (root)
trace_id = "abc...", span_id = "span1"
    │
    ├── event B: workflow.started        ← span 2 (child of A)
    │   trace_id = "abc...", parent_span_id = "span1", span_id = "span2"
    │
    ├── event C: agent.created           ← span 3 (child of A)
    │   trace_id = "abc...", parent_span_id = "span1", span_id = "span3"
    │
    │   ├── event D: agent.started       ← span 4 (child of C)
    │   │   trace_id = "abc...", parent_span_id = "span3", span_id = "span4"
    │   │
    │   ├── event E: tool.execution.started  ← span 5 (child of C)
    │   │   trace_id = "abc...", parent_span_id = "span3", span_id = "span5"
    │   │
    │   └── event F: agent.completed     ← span 6 (child of C)
    │       trace_id = "abc...", parent_span_id = "span3", span_id = "span6"
    │
    └── event G: workflow.completed      ← span 7 (child of A)
        trace_id = "abc...", parent_span_id = "span1", span_id = "span7"
```

### 22.3 Span Lifecycle

```python
class EventSpan:
    """OpenTelemetry-compatible span created per event."""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str                       # event_type
    start_time: datetime
    end_time: datetime | None
    attributes: dict[str, str]      # event metadata
    status: SpanStatus              # OK | ERROR
```

Spans are exported to OpenTelemetry-compatible backends (locally: span buffer; distributed: Jaeger/Zipkin).

---

## 23. Event Metrics

### 23.1 Core Metrics

```python
class EventBusMetrics:
    # Publish metrics
    events_published_total: Counter      # tags: topic, event_type, status
    publish_latency_seconds: Histogram  # tags: topic (buckets: 0.001, 0.01, 0.1, 1)

    # Delivery metrics
    events_delivered_total: Counter      # tags: topic, subscriber, status
    delivery_latency_seconds: Histogram # tags: topic, subscriber
    delivery_attempts: Histogram        # tags: topic (buckets: 1, 2, 3)

    # Queue metrics
    channel_queue_depth: Gauge          # tags: channel_id
    channel_queue_latency: Gauge        # tags: channel_id (oldest event age)

    # Dead letter metrics
    dead_letter_total: Counter          # tags: reason

    # Throughput metrics
    events_per_second: Gauge            # tags: topic
    bytes_per_second: Gauge             # tags: topic
```

### 23.2 Metric Collection

```python
class MetricsCollector:
    """Collects event bus metrics. Pluggable backend."""

    def record_publish(
        self, topic: str, event_type: str, status: str, latency: float
    ) -> None: ...

    def record_delivery(
        self, topic: str, subscriber: str, status: str, latency: float
    ) -> None: ...

    def record_dead_letter(self, reason: str) -> None: ...

    def record_queue_depth(self, channel_id: str, depth: int) -> None: ...

    def snapshot(self) -> EventBusMetricsSnapshot: ...

    def export_prometheus(self) -> str: ...     # Prometheus text format
```

### 23.3 Metric Export

| Backend | Local (Phase 1) | Distributed (Phase 3+) |
|---|---|---|
| In-memory | ✓ (last 5 min window) | — |
| Prometheus | ✓ (HTTP endpoint at localhost:9095) | ✓ |
| OpenTelemetry | ✓ | ✓ (OTLP exporter) |
| Log file | ✓ (structured JSON) | ✓ |

---

## 24. Plugin Event Hooks

### 24.1 Plugin Declaration

Plugins declare their event subscriptions in their manifest:

```yaml
# plugin.yaml
events:
  # Events this plugin publishes
  publishes:
    - type: plugin.git.pull_request.opened
      version: 1
      description: "Emitted when a pull request is opened"
      schema: schemas/pr_opened.json

    - type: plugin.git.pull_request.merged
      version: 1

  # Events this plugin subscribes to
  subscribes:
    - topic: tool.execution.completed
      filter:
        eq:
          tool_id: "core.file.write"

    - topic: agent.approval_required
      filter:
        pattern:
          agent_type: "plugin.git.*"

  # Event lifecycle hooks
  hooks:
    - on_before_publish
    - on_after_persist
```

### 24.2 Plugin Event Registration Flow

```
Plugin activated
    │
    ├── 1. Validate manifest event declarations
    ├── 2. Register event types in plugin namespace
    ├── 3. Create subscriptions for declared topics
    ├── 4. Register lifecycle hooks
    └── 5. Emit plugin.activated event

Plugin deactivated
    │
    ├── 1. Cancel all subscriptions owned by plugin
    ├── 2. Deprecate event types (graceful, drain in-flight)
    └── 3. Emit plugin.deactivated event
```

### 24.3 Plugin Event Isolation

| Concern | Mechanism |
|---|---|
| Namespace isolation | Plugin can only publish to `plugin.{id}.>` |
| Schema isolation | Plugin can only register schemas in its namespace |
| Subscription isolation | Plugin can subscribe anywhere (with permission) |
| Hook isolation | Plugin lifecycle hooks cannot block other plugins |
| Payload isolation | Plugin payload size limited to 64KB (vs 256KB for core) |

---

## 25. Workflow Event Integration

### 25.1 Workflow as Event Consumer

The Workflow Engine subscribes to agent and user events to drive DAG execution:

```python
class WorkflowEventSubscriptions:
    """Standard subscriptions the Workflow Engine creates."""

    @staticmethod
    def get_subscriptions(engine_id: str) -> list[tuple[str, SubscribeOptions]]:
        return [
            # Agent lifecycle — track nodes executed by agents
            ("agent.completed", SubscribeOptions(
                filter=EventFilter(exists=["workflow_node_id"]),
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            )),
            ("agent.failed", SubscribeOptions(
                filter=EventFilter(exists=["workflow_node_id"]),
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            )),
            ("agent.cancelled", SubscribeOptions(
                filter=EventFilter(exists=["workflow_node_id"]),
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
            )),

            # User actions — approval gates
            ("user.action.approved", SubscribeOptions(
                filter=EventFilter(exists=["workflow_node_id"]),
            )),
            ("user.action.rejected", SubscribeOptions(
                filter=EventFilter(exists=["workflow_node_id"]),
            )),
        ]
```

### 25.2 Workflow as Event Publisher

```python
class WorkflowEventPublisher:
    """Events the Workflow Engine publishes."""

    def publish_node_started(self, workflow_id: str, node_id: str) -> None:
        self._bus.publish("workflow.node.started", {
            "type": "workflow.node.started",
            "workflow_id": workflow_id,
            "node_id": node_id,
            "timestamp": now(),
        }, PublishOptions(routing_key=workflow_id))

    def publish_node_completed(
        self, workflow_id: str, node_id: str, status: str
    ) -> None:
        self._bus.publish("workflow.node.completed", {
            "type": "workflow.node.completed",
            "workflow_id": workflow_id,
            "node_id": node_id,
            "status": status,  # completed | failed | skipped
            "timestamp": now(),
        }, PublishOptions(routing_key=workflow_id))
```

### 25.3 Event-Driven DAG Transitions

```
workflow.node.completed (agent A)
    │
    ▼
Workflow Engine receives event
    │
    ├── Mark node A as COMPLETED
    ├── Evaluate DAG dependencies
    ├── Node B: all deps met → READY
    ├── Node B dispatched as agent invocation
    │
    └── Publish workflow.node.started (node B)
```

---

## 26. Agent Event Integration

### 26.1 Agent Runtime as Event Publisher

The Agent Runtime is the most prolific publisher. Every agent lifecycle transition and execution step emits events:

```python
class AgentEventPublisher:
    """Published by Agent Runtime during agent execution."""

    def publish_agent_started(
        self, agent_type: str, invocation_id: str, model: str, context_size: int
    ) -> None:
        self._bus.publish("agent.started", {
            "type": "agent.started",
            "agent_type": agent_type,
            "invocation_id": invocation_id,
            "model": model,
            "context_size": context_size,
        }, PublishOptions(routing_key=invocation_id))

    def publish_agent_completed(
        self, invocation_id: str, duration_ms: int, token_usage: dict
    ) -> None:
        self._bus.publish("agent.completed", {
            "type": "agent.completed",
            "invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "token_usage": token_usage,
        }, PublishOptions(routing_key=invocation_id))

    def publish_thinking_update(
        self, invocation_id: str, text: str, is_partial: bool
    ) -> None:
        self._bus.publish("agent.thinking", {
            "type": "agent.thinking",
            "invocation_id": invocation_id,
            "text": text,
            "is_partial": is_partial,
        }, PublishOptions(
            routing_key=invocation_id,
            # Thinking updates are ephemeral: at-most-once, no persistence
        ))

    def publish_tool_request(
        self, invocation_id: str, tool_id: str, call_id: str, params: dict
    ) -> None:
        self._bus.publish("agent.tool_request", {
            "type": "agent.tool_request",
            "invocation_id": invocation_id,
            "tool_id": tool_id,
            "call_id": call_id,
            "params": params,
        }, PublishOptions(routing_key=invocation_id))

    def publish_tool_result(
        self, invocation_id: str, call_id: str, success: bool, duration_ms: int
    ) -> None:
        self._bus.publish("agent.tool_result", {
            "type": "agent.tool_result",
            "invocation_id": invocation_id,
            "call_id": call_id,
            "success": success,
            "duration_ms": duration_ms,
        }, PublishOptions(routing_key=invocation_id))
```

### 26.2 Agent Runtime as Event Consumer

The Agent Runtime subscribes to events that affect running agents:

| Event | Effect |
|---|---|
| `user.action.cancelled` | Cancel agent with matching invocation_id |
| `user.action.approved` | Resume agent waiting on approval gate |
| `user.action.rejected` | Notify agent that approval was denied |
| `system.config.changed` | Possibly reload config for future invocations |
| `system.runtime.shutting_down` | Begin graceful shutdown, cancel all agents |

### 26.3 Agent Approval Gate via Events

```
Agent reaches approval gate
    │
    ├── 1. Pause agent execution
    ├── 2. Publish agent.approval_required
    │       {
    │           invocation_id,
    │           call_id,
    │           tool_id,
    │           params,
    │           description,
    │           workflow_node_id (if part of workflow)
    │       }
    │
    ▼
UI receives event → shows approval dialog
    │
    ├── User approves → publish user.action.approved
    │   {
    │       invocation_id,
    │       call_id,
    │       modified_params (optional),
    │       approved_at
    │   }
    │
    └── User rejects → publish user.action.rejected
        {
            invocation_id,
            call_id,
            reason (optional)
        }

    ▼
Agent Runtime receives approval result
    ├── Resolve waiting agent via invocation_id + call_id
    ├── Resume with approval or rejection
    └── Continue execution loop
```

---

## 27. Future Distributed Migration Path

### 27.1 Evolution Phases

```
Phase 1 (v4.0) — SINGLE PROCESS
┌─────────────────────────────────────┐
│  InMemoryEventBus                    │
│  │ asyncio.Queue per channel        │
│  │ SQLite Event Store               │
│  │ No network dependency            │
│  └ Capacity: ~10K events/sec        │
└─────────────────────────────────────┘

Phase 2 (v4.5) — PLUGGABLE BACKEND
┌─────────────────────────────────────┐
│  EventBus with Backend abstraction  │
│  │ InMemoryBackend (default)        │
│  │ SQLiteBackend                    │
│  │ FileBackend (JSONL)              │
│  └ Capacity: ~10K events/sec        │
└─────────────────────────────────────┘

Phase 3 (v5.0) — NETWORKED
┌─────────────────────────────────────┐
│  EventBus with Remote Backend       │
│  │ NATSBackend (lightweight)        │
│  │ RedisBackend (pub/sub + stream)  │
│  │ Multiple processes, one machine  │
│  └ Capacity: ~100K events/sec       │
└─────────────────────────────────────┘

Phase 4 (v5.2+) — DISTRIBUTED CLUSTER
┌─────────────────────────────────────┐
│  EventBus Cluster                   │
│  │ KafkaBackend (partitioned)       │
│  │ Multi-node, multi-machine        │
│  │ Geo-replicated                   │
│  └ Capacity: ~1M+ events/sec        │
└─────────────────────────────────────┘
```

### 27.2 What Changes (Phase 3+)

| Component | Local (Phase 1) | Distributed (Phase 3+) |
|---|---|---|
| Transport | `asyncio.Queue` | NATS subject / Kafka topic |
| Persistence | SQLite | NATS JetStream / Kafka log |
| Ordering | Per-queue sequential | Per-partition sequential |
| Routing | In-memory dict | NATS/Kafka broker routing |
| Subscriptions | Python callbacks | Consumer groups |
| Dead letter | SQLite table | NATS/Kafka DLQ topic |
| Metrics | In-memory counters | Prometheus / OTLP |
| Tracing | Local span buffer | W3C Trace Context + Jaeger |

### 27.3 What Stays the Same

| Aspect | Why |
|---|---|
| `EventBusProtocol` | All phases implement the same interface |
| `EventEnvelope` schema | Envelope structure is transport-agnostic |
| `EventSchema` registration | Schema registry is independent of transport |
| Event type namespacing | `core.agent.started` is the same everywhere |
| Subscription filter syntax | Filters are applied client-side after deserialization |
| Authorization model | Checked before publish/subscribe, regardless of transport |
| Dead letter handling | Concept same, only storage differs |
| Replay API | Interface same, implementation differs (SQL query vs Kafka offset) |

### 27.4 Backend Abstraction

```python
class EventBusBackendProtocol(Protocol):
    """Abstract over local vs distributed transport."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def publish(
        self, topic: str, envelope: EventEnvelope
    ) -> None: ...

    def subscribe(
        self, topic: str, handler: EventHandler
    ) -> Subscription: ...

    async def replay(
        self, topic: str, handler: EventHandler, options: ReplayOptions
    ) -> int: ...

    # Backend-specific
    @property
    def backend_type(self) -> str: ...         # "memory" | "sqlite" | "nats" | "kafka"

    @property
    def supports_exactly_once(self) -> bool: ...
    @property
    def supports_global_ordering(self) -> bool: ...
    @property
    def max_message_size(self) -> int: ...
```

### 27.5 Migration Strategy

```yaml
migration:
  from: InMemoryBackend
  to: NATSBackend

  steps:
    - 1: Add NATSBackend implementation (no behavior change)
    - 2: Add configuration option `event_bus.backend = "memory" | "nats"`
    - 3: Run both backends in parallel (dual-write) for observability
    - 4: Switch default to NATS
    - 5: Remove InMemoryBackend after deprecation period
```

---

*End of specification. This document defines the Event Bus contracts, architecture, and all operational concerns. Implementations must satisfy these specifications while remaining free to choose internal data structures as long as external contracts are met.*
