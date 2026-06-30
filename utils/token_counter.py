"""Thread-safe token counter backed by tiktoken."""

from __future__ import annotations

import threading

import tiktoken

from utils.logging_setup import get_logger

log = get_logger("utils.token_counter")

_LOCK = threading.Lock()
_CACHE: dict[str, tiktoken.Encoding] = {}


def _get_encoding(name: str = "cl100k_base") -> tiktoken.Encoding:
    with _LOCK:
        if name not in _CACHE:
            try:
                _CACHE[name] = tiktoken.get_encoding(name)
            except Exception as exc:
                log.warning("Cannot load encoding %r: %s — falling back to cl100k_base", name, exc)
                _CACHE[name] = tiktoken.get_encoding("cl100k_base")
        return _CACHE[name]


def count(text: str, encoding: str = "cl100k_base") -> int:
    """Return the number of tokens in *text* using the given tiktoken encoding."""
    if not text:
        return 0
    try:
        return len(_get_encoding(encoding).encode(text))
    except Exception as exc:
        log.error("Token counting failed: %s — using character estimate", exc)
        return max(1, len(text) // 4)
