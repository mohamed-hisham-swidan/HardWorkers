"""Simple typed event bus for decoupled cross-component communication.

Usage::

    bus = EventBus()
    bus.on("model_changed", my_handler)
    bus.emit(ModelChangedEvent(model_name="gpt-4"))
    # my_handler receives the event instance

New-style typed event system::

    from core.events import EventMetadata, EventEnvelope, EventSchema, SchemaRegistry

    meta = EventMetadata.create(source="my_component")
    envelope = EventEnvelope(topic="agent.started", payload={...}, metadata=meta)

    registry = SchemaRegistry()
    registry.register(EventSchema(topic="agent.started", version=1, json_schema={...}))
    registry.validate("agent.started", {...})  # True/False
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

log = logging.getLogger("core.events")

T = TypeVar("T")


@dataclass
class Event:
    """Base event with optional payload."""

    sender: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ── Domain Events ──────────────────────────────────────────────────────────────


@dataclass
class ModelChangedEvent(Event):
    model_name: str = ""


@dataclass
class ModelsRefreshedEvent(Event):
    models: list[str] = field(default_factory=list)
    active: str | None = None


@dataclass
class WorkspaceSwitchedEvent(Event):
    workspace_name: str = ""
    workspace_id: int | None = None


@dataclass
class ChatCreatedEvent(Event):
    chat_id: int = 0


@dataclass
class ChatDeletedEvent(Event):
    chat_id: int = 0


@dataclass
class MemoryUpdatedEvent(Event):
    fact_key: str = ""


@dataclass
class SettingsChangedEvent(Event):
    section: str = ""


EventHandler = Callable[[Event], None]


class EventBus:
    """Pub-sub event bus. Thread-safe for register/unregister."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = __import__("threading").Lock()

    def on(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_name, []).append(handler)

    def off(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_name, [])
            if handler in handlers:
                handlers.remove(handler)

    def emit(self, event: Event) -> None:
        event_name = type(event).__name__
        with self._lock:
            handlers = list(self._handlers.get(event_name, []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                log.exception("Handler failed for event %s", event_name)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()


# ── Typed Event Envelope ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EventMetadata:
    """Immutable metadata attached to every event.

    Fields:
        event_id: Globally unique event identifier (UUID4 hex).
        timestamp: UTC datetime when the event was created.
        source: Component that created the event (e.g. ``"agent.runtime"``).
        trace_id: Distributed tracing identifier.  Defaults to event_id if not set.
        version: Schema version of the event payload.
    """

    event_id: str
    timestamp: datetime
    source: str
    trace_id: str
    version: int = 1

    @classmethod
    def create(
        cls,
        source: str,
        *,
        event_id: str | None = None,
        timestamp: datetime | None = None,
        trace_id: str | None = None,
        version: int = 1,
    ) -> EventMetadata:
        """Factory method with sensible defaults.

        ``event_id`` defaults to ``uuid.uuid4().hex``.
        ``timestamp`` defaults to ``datetime.now(timezone.utc)``.
        ``trace_id`` defaults to the same value as ``event_id``.
        """
        eid = event_id or uuid.uuid4().hex
        return cls(
            event_id=eid,
            timestamp=timestamp or datetime.now(timezone.utc),  # noqa: UP017
            source=source,
            trace_id=trace_id or eid,
            version=version,
        )


@dataclass(frozen=True)
class EventEnvelope(Generic[T]):
    """A typed event travelling through the bus.

    Generic parameter *T* captures the payload type for static analysis.
    At runtime the payload is always a ``dict`` (validated against a schema).
    """

    topic: str
    payload: T
    metadata: EventMetadata


# ── Event Schema & Registry ──────────────────────────────────────────────────────


class SchemaValidationError(Exception):
    """Raised when a payload does not conform to its registered schema."""


@dataclass
class EventSchema:
    """Describes the expected shape of an event payload.

    Fields:
        topic: Event topic this schema applies to (e.g. ``"agent.started"``).
        version: Monotonic version number.  Start at 1.
        json_schema: A JSON Schema (draft 2020-12) ``dict`` describing the payload.
    """

    topic: str
    version: int
    json_schema: dict


class SchemaRegistry:
    """In-memory registry of event schemas.

    Thread-safe for concurrent register / read operations.
    Validation uses a lightweight recursive checker — no jsonschema dependency.
    """

    def __init__(self) -> None:
        self._schemas: dict[str, dict[int, EventSchema]] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def register(self, schema: EventSchema) -> None:
        """Register a schema.  Replaces any existing schema with the same topic+version."""
        with self._lock:
            self._schemas.setdefault(schema.topic, {})[schema.version] = schema
        log.debug("Schema registered: topic=%s version=%d", schema.topic, schema.version)

    def get(self, topic: str, version: int | None = None) -> EventSchema | None:
        """Retrieve a schema.

        If *version* is ``None`` the highest version is returned.
        Returns ``None`` when the topic (or version) does not exist.
        """
        with self._lock:
            versions = self._schemas.get(topic)
            if versions is None:
                return None
            if version is not None:
                return versions.get(version)
            return versions[max(versions)] if versions else None

    def validate(
        self,
        topic: str,
        payload: dict[str, Any],
        version: int | None = None,
    ) -> bool:
        """Validate *payload* against the registered schema for *topic*.

        Returns ``True`` on success, raises :class:`SchemaValidationError` on failure.

        Raises :class:`SchemaValidationError` if the topic (or version) is not
        registered.
        """
        schema = self.get(topic, version=version)
        if schema is None:
            raise SchemaValidationError(f"No schema registered for topic={topic!r} version={version}")

        errors = _validate_against_schema(payload, schema.json_schema)
        if errors:
            raise SchemaValidationError(f"Payload validation failed for topic={topic!r}: {'; '.join(errors)}")
        return True

    def exists(self, topic: str, version: int | None = None) -> bool:
        """Check whether a schema exists for *topic* (optionally at *version*)."""
        return self.get(topic, version=version) is not None

    def list_topics(self) -> list[str]:
        """Return all topic names that have at least one registered schema."""
        with self._lock:
            return sorted(self._schemas.keys())

    def remove(self, topic: str, version: int | None = None) -> None:
        """Remove a registered schema.

        If *version* is ``None``, all versions of *topic* are removed.
        Does nothing if the topic does not exist.
        """
        with self._lock:
            if version is None:
                self._schemas.pop(topic, None)
            else:
                versions = self._schemas.get(topic)
                if versions is not None:
                    versions.pop(version, None)
                    if not versions:
                        self._schemas.pop(topic, None)


# ── Lightweight JSON Schema Validator ────────────────────────────────────────────


def _validate_against_schema(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Recursive validator that handles the common JSON Schema keywords.

    Supported keywords: ``type``, ``properties`` + ``required``, ``items``,
    ``enum``, ``minimum`` / ``maximum``, ``minLength`` / ``maxLength``,
    ``minItems`` / ``maxItems``.
    """
    errors: list[str] = []

    # --- type ---
    expected_type = schema.get("type")
    if expected_type is not None:
        type_ok, type_err = _check_type(value, expected_type, path)
        if not type_ok:
            errors.append(type_err)
            return errors  # short-circuit — further checks are meaningless

    # --- enum ---
    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        errors.append(f"{path}: value {value!r} not in enum {enum_values}")

    # --- numeric constraints ---
    if isinstance(value, (int, float)):
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: {value} < minimum ({minimum})")
        maximum = schema.get("maximum")
        if maximum is not None and value > maximum:
            errors.append(f"{path}: {value} > maximum ({maximum})")

    # --- string constraints ---
    if isinstance(value, str):
        min_len = schema.get("minLength")
        if min_len is not None and len(value) < min_len:
            errors.append(f"{path}: length {len(value)} < minLength ({min_len})")
        max_len = schema.get("maxLength")
        if max_len is not None and len(value) > max_len:
            errors.append(f"{path}: length {len(value)} > maxLength ({max_len})")

    # --- object properties ---
    if isinstance(value, dict):
        required = schema.get("required", [])
        for prop in required:
            if prop not in value:
                errors.append(f"{path}: missing required property {prop!r}")

        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in value:
                child_errors = _validate_against_schema(value[prop_name], prop_schema, path=f"{path}.{prop_name}")
                errors.extend(child_errors)

        additional = schema.get("additionalProperties", True)
        if additional is False:
            allowed = set(properties) | set(required)
            for key in value:
                if key not in allowed:
                    errors.append(f"{path}: unexpected property {key!r}")

    # --- array items ---
    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: item count {len(value)} < minItems ({min_items})")
        max_items = schema.get("maxItems")
        if max_items is not None and len(value) > max_items:
            errors.append(f"{path}: item count {len(value)} > maxItems ({max_items})")

        items_schema = schema.get("items")
        if items_schema is not None:
            for idx, item in enumerate(value):
                child_errors = _validate_against_schema(item, items_schema, path=f"{path}[{idx}]")
                errors.extend(child_errors)

    return errors


def _check_type(value: Any, expected: str, path: str) -> tuple[bool, str]:
    """Check that *value* matches the JSON Schema *expected* type."""
    type_map: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
        "null": type(None),
    }
    py_type = type_map.get(expected)
    if py_type is None:
        return True, ""  # unknown type — pass through

    if isinstance(value, py_type):
        # disallow bool as int or number (bool is a subclass of int in Python)
        if expected in ("integer", "number") and isinstance(value, bool):
            return False, f"{path}: expected {expected}, got bool"
        return True, ""

    if isinstance(value, bool) and expected in ("integer", "number"):
        return False, f"{path}: expected {expected}, got bool"

    return False, f"{path}: expected {expected}, got {type(value).__name__}"
