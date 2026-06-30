"""Tests for typed event envelope, schema registry, and validation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from core.events import (
    EventEnvelope,
    EventMetadata,
    EventSchema,
    SchemaRegistry,
    SchemaValidationError,
    _check_type,
    _validate_against_schema,
)

# ── EventMetadata ───────────────────────────────────────────────────────────────


class TestEventMetadata:
    def test_create_with_defaults(self) -> None:
        meta = EventMetadata.create(source="test")
        assert meta.source == "test"
        assert meta.version == 1
        assert uuid.UUID(meta.event_id).version == 4  # valid UUID4
        assert isinstance(meta.timestamp, datetime)
        assert meta.trace_id == meta.event_id  # defaults to event_id

    def test_create_explicit_values(self) -> None:
        eid = "my-custom-id"
        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)  # noqa: UP017
        meta = EventMetadata.create(
            source="agent",
            event_id=eid,
            timestamp=ts,
            trace_id="trace-abc",
            version=3,
        )
        assert meta.event_id == eid
        assert meta.timestamp == ts
        assert meta.trace_id == "trace-abc"
        assert meta.version == 3

    def test_frozen(self) -> None:
        meta = EventMetadata.create(source="test")
        with pytest.raises(AttributeError):
            meta.source = "other"  # type: ignore[misc]

    def test_fields_are_typed(self) -> None:
        meta = EventMetadata.create(source="bus")
        assert isinstance(meta.event_id, str)
        assert isinstance(meta.timestamp, datetime)
        assert isinstance(meta.source, str)
        assert isinstance(meta.trace_id, str)
        assert isinstance(meta.version, int)


# ── EventEnvelope ───────────────────────────────────────────────────────────────


class TestEventEnvelope:
    def test_create(self) -> None:
        meta = EventMetadata.create(source="test")
        payload = {"key": "value"}
        envelope = EventEnvelope(topic="test.event", payload=payload, metadata=meta)
        assert envelope.topic == "test.event"
        assert envelope.payload == payload
        assert envelope.metadata is meta

    def test_frozen(self) -> None:
        meta = EventMetadata.create(source="test")
        envelope = EventEnvelope(topic="t", payload={}, metadata=meta)
        with pytest.raises(AttributeError):
            envelope.topic = "other"  # type: ignore[misc]

    def test_payload_type_is_preserved(self) -> None:
        meta = EventMetadata.create(source="test")
        envelope: EventEnvelope[dict] = EventEnvelope(topic="t", payload={"a": 1}, metadata=meta)
        assert isinstance(envelope.payload, dict)


# ── EventSchema ─────────────────────────────────────────────────────────────────


class TestEventSchema:
    def test_create(self) -> None:
        schema = EventSchema(
            topic="agent.started",
            version=1,
            json_schema={
                "type": "object",
                "required": ["agent_type"],
                "properties": {
                    "agent_type": {"type": "string"},
                },
            },
        )
        assert schema.topic == "agent.started"
        assert schema.version == 1
        assert schema.json_schema["type"] == "object"


# ── SchemaRegistry ───────────────────────────────────────────────────────────────


class TestSchemaRegistry:
    def make_schema(self, topic: str = "test.event", version: int = 1) -> EventSchema:
        return EventSchema(
            topic=topic,
            version=version,
            json_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "count": {"type": "integer", "minimum": 0},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
        )

    # ── register / get ───────────────────────────────────────────────────────

    def test_register_and_get(self) -> None:
        reg = SchemaRegistry()
        schema = self.make_schema()
        reg.register(schema)
        assert reg.get("test.event") is schema

    def test_get_latest_version(self) -> None:
        reg = SchemaRegistry()
        v1 = self.make_schema(version=1)
        v2 = self.make_schema(version=2)
        reg.register(v1)
        reg.register(v2)
        assert reg.get("test.event") is v2  # latest

    def test_get_specific_version(self) -> None:
        reg = SchemaRegistry()
        v1 = self.make_schema(version=1)
        v2 = self.make_schema(version=2)
        reg.register(v1)
        reg.register(v2)
        assert reg.get("test.event", version=1) is v1
        assert reg.get("test.event", version=2) is v2

    def test_get_missing_topic(self) -> None:
        reg = SchemaRegistry()
        assert reg.get("nonexistent") is None

    def test_get_missing_version(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema(version=1))
        assert reg.get("test.event", version=99) is None

    # ── exists ───────────────────────────────────────────────────────────────

    def test_exists(self) -> None:
        reg = SchemaRegistry()
        assert not reg.exists("test.event")
        reg.register(self.make_schema())
        assert reg.exists("test.event")
        assert reg.exists("test.event", version=1)
        assert not reg.exists("test.event", version=99)

    # ── list_topics ──────────────────────────────────────────────────────────

    def test_list_topics_empty(self) -> None:
        reg = SchemaRegistry()
        assert reg.list_topics() == []

    def test_list_topics(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema(topic="alpha"))
        reg.register(self.make_schema(topic="beta"))
        reg.register(self.make_schema(topic="beta", version=2))
        assert reg.list_topics() == ["alpha", "beta"]

    # ── remove ───────────────────────────────────────────────────────────────

    def test_remove_single_version(self) -> None:
        reg = SchemaRegistry()
        v1 = self.make_schema(version=1)
        v2 = self.make_schema(version=2)
        reg.register(v1)
        reg.register(v2)
        reg.remove("test.event", version=1)
        assert reg.get("test.event") is v2  # latest unchanged
        assert reg.get("test.event", version=1) is None

    def test_remove_all_versions(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema(version=1))
        reg.register(self.make_schema(version=2))
        reg.remove("test.event")
        assert not reg.exists("test.event")

    def test_remove_missing_topic(self) -> None:
        reg = SchemaRegistry()
        reg.remove("nonexistent")  # should not raise

    # ── validate — success ───────────────────────────────────────────────────

    def test_validate_valid_payload(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        assert reg.validate("test.event", {"name": "Alice", "count": 3}) is True

    def test_validate_valid_with_array(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        assert reg.validate("test.event", {"name": "Bob", "tags": ["a", "b"]}) is True

    def test_validate_with_explicit_version(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema(version=2))
        assert reg.validate("test.event", {"name": "x"}, version=2) is True

    # ── validate — failures ──────────────────────────────────────────────────

    def test_validate_missing_required_field(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        with pytest.raises(SchemaValidationError, match="missing required"):
            reg.validate("test.event", {"count": 1})

    def test_validate_wrong_type(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        with pytest.raises(SchemaValidationError, match="expected string"):
            reg.validate("test.event", {"name": 42})

    def test_validate_minimum_violation(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        with pytest.raises(SchemaValidationError, match="minimum"):
            reg.validate("test.event", {"name": "x", "count": -1})

    def test_validate_min_length_violation(self) -> None:
        reg = SchemaRegistry()
        reg.register(self.make_schema())
        with pytest.raises(SchemaValidationError, match="minLength"):
            reg.validate("test.event", {"name": ""})

    def test_validate_no_schema_raises(self) -> None:
        reg = SchemaRegistry()
        with pytest.raises(SchemaValidationError, match="No schema registered"):
            reg.validate("nonexistent", {})

    def test_validate_enum_violation(self) -> None:
        reg = SchemaRegistry()
        reg.register(
            EventSchema(
                topic="status",
                version=1,
                json_schema={
                    "type": "object",
                    "required": ["level"],
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["info", "warn", "error"],
                        }
                    },
                },
            )
        )
        with pytest.raises(SchemaValidationError, match="enum"):
            reg.validate("status", {"level": "debug"})

    def test_validate_additional_properties_false(self) -> None:
        reg = SchemaRegistry()
        reg.register(
            EventSchema(
                topic="strict",
                version=1,
                json_schema={
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                    "additionalProperties": False,
                },
            )
        )
        with pytest.raises(SchemaValidationError, match="unexpected property"):
            reg.validate("strict", {"id": 1, "extra": "x"})


# ── Validator Internals ────────────────────────────────────────────────────────


class TestValidateAgainstSchema:
    def test_string_type(self) -> None:
        assert _validate_against_schema("hello", {"type": "string"}) == []

    def test_integer_type(self) -> None:
        assert _validate_against_schema(42, {"type": "integer"}) == []

    def test_number_type(self) -> None:
        assert _validate_against_schema(3.14, {"type": "number"}) == []

    def test_boolean_type(self) -> None:
        assert _validate_against_schema(True, {"type": "boolean"}) == []

    def test_null_type(self) -> None:
        assert _validate_against_schema(None, {"type": "null"}) == []

    def test_array_type(self) -> None:
        assert _validate_against_schema([1, 2], {"type": "array"}) == []

    def test_object_type(self) -> None:
        assert _validate_against_schema({"a": 1}, {"type": "object"}) == []

    def test_unknown_type_passes(self) -> None:
        assert _validate_against_schema("x", {"type": "unknown_type"}) == []

    def test_integer_rejects_bool(self) -> None:
        errors = _validate_against_schema(True, {"type": "integer"})
        assert len(errors) == 1
        assert "expected integer" in errors[0]

    def test_number_rejects_bool(self) -> None:
        errors = _validate_against_schema(False, {"type": "number"})
        assert len(errors) == 1

    def test_nested_object(self) -> None:
        schema = {
            "type": "object",
            "required": ["meta"],
            "properties": {
                "meta": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                }
            },
        }
        assert _validate_against_schema({"meta": {"id": 1}}, schema) == []
        errors = _validate_against_schema({"meta": {"id": "x"}}, schema)
        assert len(errors) == 1
        assert "expected integer" in errors[0]

    def test_array_items_validation(self) -> None:
        schema = {"type": "array", "items": {"type": "integer"}}
        assert _validate_against_schema([1, 2, 3], schema) == []
        errors = _validate_against_schema([1, "x", 3], schema)
        assert len(errors) == 1
        assert "expected integer" in errors[0]

    def test_array_min_max_items(self) -> None:
        schema = {"type": "array", "minItems": 2, "maxItems": 3}
        assert _validate_against_schema([1, 2], schema) == []
        errors = _validate_against_schema([1], schema)
        assert any("minItems" in e for e in errors)

    def test_max_length(self) -> None:
        schema = {"type": "string", "maxLength": 3}
        assert _validate_against_schema("ab", schema) == []
        errors = _validate_against_schema("abcd", schema)
        assert any("maxLength" in e for e in errors)

    def test_maximum(self) -> None:
        schema = {"type": "integer", "maximum": 10}
        assert _validate_against_schema(5, schema) == []
        errors = _validate_against_schema(15, schema)
        assert any("maximum" in e for e in errors)


class TestCheckType:
    def test_valid_types(self) -> None:
        for val, expected in [
            ("hi", "string"),
            (42, "integer"),
            (3.14, "number"),
            (True, "boolean"),
            (None, "null"),
            ([], "array"),
            ({}, "object"),
        ]:
            ok, msg = _check_type(val, expected, "$")
            assert ok, f"{val!r} should be {expected}: {msg}"

    def test_invalid_types(self) -> None:
        ok, msg = _check_type(42, "string", "$")
        assert not ok
        assert "expected string" in msg

    def test_bool_is_not_integer(self) -> None:
        ok, msg = _check_type(True, "integer", "$")
        assert not ok

    def test_bool_is_not_number(self) -> None:
        ok, msg = _check_type(True, "number", "$")
        assert not ok
