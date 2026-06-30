"""Unit tests for utility functions."""

from __future__ import annotations

import pytest

from utils.helpers import elapsed_label, parse_enum, retry, sanitize_text, truncate


class TestRetry:
    def test_retry_succeeds_first_time(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = work()
        assert result == "ok"
        assert call_count == 1

    def test_retry_after_failures(self) -> None:
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary")
            return "ok"

        result = work()
        assert result == "ok"
        assert call_count == 3

    def test_retry_exhaustion(self) -> None:
        call_count = 0

        @retry(max_attempts=2, base_delay=0.01)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("always fails")

        with pytest.raises(ValueError):
            work()
        assert call_count == 2


class TestSanitizeText:
    def test_normal_text(self) -> None:
        assert sanitize_text("Hello World") == "Hello World"

    def test_truncation(self) -> None:
        long = "x" * 100
        result = sanitize_text(long, max_length=10)
        assert len(result) == 10

    def test_control_chars_removed(self) -> None:
        result = sanitize_text("Hello\x00World")
        assert result == "HelloWorld"


class TestTruncate:
    def test_short_text(self) -> None:
        assert truncate("Hello", 10) == "Hello"

    def test_long_text(self) -> None:
        result = truncate("Hello World", 5)
        assert len(result) <= 8

    def test_custom_suffix(self) -> None:
        result = truncate("Hello World", 8, suffix="[..]")
        assert result == "Hell[..]"


class TestElapsedLabel:
    def test_seconds(self) -> None:
        assert elapsed_label(0.5) == "0.5s"
        assert elapsed_label(1.0) == "1.0s"

    def test_minutes(self) -> None:
        label = elapsed_label(90)
        assert label == "1m 30s"

    def test_long_running(self) -> None:
        label = elapsed_label(4000)
        assert "m" in label


class TestParseEnum:
    def test_valid_value(self) -> None:
        from models.enums import ModelCategory

        result = parse_enum(ModelCategory, "Coding", default=ModelCategory.GENERAL)
        assert result == ModelCategory.CODING

    def test_fallback(self) -> None:
        from models.enums import ModelCategory

        result = parse_enum(ModelCategory, "Nonexistent", default=ModelCategory.GENERAL)
        assert result == ModelCategory.GENERAL
