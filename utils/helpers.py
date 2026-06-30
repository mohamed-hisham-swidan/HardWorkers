"""General-purpose utility helpers."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable)


def retry(max_attempts: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Decorator: retry a function with exponential back-off."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        time.sleep(base_delay * 2**attempt)
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def sanitize_text(text: str, max_length: int = 100_000) -> str:
    """Strip control characters and enforce maximum length."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text[:max_length]


def truncate(text: str, max_chars: int = 80, suffix: str = "…") -> str:
    """Truncate a string and append suffix if needed."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


def elapsed_label(seconds: float) -> str:
    """Convert elapsed seconds to a human-readable label."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"


def parse_enum(enum_cls: type[Enum], value: Any, default: Enum) -> Enum:
    """Safely parse an enum member, returning *default* on failure."""
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return default
