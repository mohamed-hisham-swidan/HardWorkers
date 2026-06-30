from __future__ import annotations

import re
import time

from config.constants import ARCHIVE_KEEP_LAST_N
from database.connection import ConnectionManager
from models.domain import Message
from models.enums import MessageRole
from utils.logging_setup import get_logger
from utils.token_counter import count as count_tokens

log = get_logger("database.repositories.chat_repository")

_BASE64_IMG_RE = re.compile(r"!\[attached image\]\(data:image/[a-z]+;base64,[^)]+\)")
"""Matches markdown-embedded base64 image data URLs in legacy message content."""


def _strip_base64_images(text: str | None) -> str | None:
    """Remove embedded base64 image markdown from legacy message content."""
    if text is None:
        return None
    stripped = _BASE64_IMG_RE.sub("", text).strip()
    return stripped if stripped else text


# ── Chat history ──────────────────────────────────────────────────────────────


class ChatRepository:
    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    # ── Chat-ID-aware methods (new multi-chat API) ──────────────────────────────

    def save_for_chat(
        self, chat_id: int, role: str, content: str, attachment_path: str | None = None, file_type: str | None = None
    ) -> int:
        """Save a message to a specific chat session."""
        if not content or not content.strip():
            raise ValueError("Message content must not be empty.")
        tokens = count_tokens(content)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO chat_history (chat_id, role, content, tokens, timestamp, attachment_path, file_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, role, content, tokens, ts, attachment_path, file_type),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_by_token_budget(self, chat_id: int, max_tokens: int) -> list[Message]:
        """Load recent messages for a chat, bounded by token budget.

        Uses a SQL window function to compute cumulative token sums from
        newest to oldest, eliminating the TOCTOU gap of the previous
        Python-loop approach.
        """
        with self._cm.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, tokens, attachment_path, file_type FROM (
                    SELECT id, role, content, tokens, attachment_path, file_type,
                           SUM(tokens) OVER (ORDER BY id DESC ROWS UNBOUNDED PRECEDING)
                           AS cum_tokens
                    FROM chat_history
                    WHERE chat_id=?
                ) WHERE cum_tokens <= ?
                ORDER BY id ASC
                """,
                (chat_id, max_tokens),
            ).fetchall()
        return [
            Message(
                id=r["id"],
                role=MessageRole(r["role"]),
                content=_strip_base64_images(r["content"]),
                tokens=r["tokens"],
                attachment_path=r["attachment_path"],
                file_type=r["file_type"],
            )
            for r in rows
        ]

    def total_tokens_for_chat(self, chat_id: int) -> int:
        with self._cm.transaction() as conn:
            result = conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM chat_history WHERE chat_id=?",
                (chat_id,),
            ).fetchone()[0]
        return int(result)

    def delete_last_assistant(self, chat_id: int) -> bool:
        """Delete the most recent assistant message for a chat."""
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM chat_history WHERE chat_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
            if row:
                conn.execute("DELETE FROM chat_history WHERE id=?", (row["id"],))
                return True
        return False

    def get_messages(self, chat_id: int, limit: int = 50, offset: int = 0) -> list[Message]:
        """Get paginated messages for a chat, newest-first."""
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, role, content, tokens, attachment_path, file_type FROM chat_history "
                "WHERE chat_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (chat_id, limit, offset),
            ).fetchall()
        return [
            Message(
                id=r["id"],
                role=MessageRole(r["role"]),
                content=_strip_base64_images(r["content"]),
                tokens=r["tokens"],
                attachment_path=r["attachment_path"],
                file_type=r["file_type"],
            )
            for r in rows
        ]

    def get_message_count(self, chat_id: int) -> int:
        """Get total message count for a chat session."""
        with self._cm.transaction() as conn:
            result = conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE chat_id=?",
                (chat_id,),
            ).fetchone()[0]
        return int(result)

    def clear_for_chat(self, chat_id: int) -> int:
        """Delete all messages belonging to a specific chat."""
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM chat_history WHERE chat_id=?", (chat_id,))
        return cur.rowcount

    def archive_old_for_chat(self, chat_id: int, keep_last_n: int = ARCHIVE_KEEP_LAST_N) -> int:
        """Archive old messages for a specific chat, keeping the last N."""
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, role, content, tokens, timestamp, attachment_path, file_type FROM chat_history "
                "WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM chat_history WHERE chat_id=? ORDER BY id DESC LIMIT ?)",
                (chat_id, chat_id, keep_last_n),
            ).fetchall()
            if not rows:
                return 0
            conn.executemany(
                "INSERT INTO archived_chat_history (role, content, tokens, timestamp, attachment_path, file_type) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (r["role"], r["content"], r["tokens"], r["timestamp"], r["attachment_path"], r["file_type"])
                    for r in rows
                ],
            )
            conn.execute(
                "DELETE FROM chat_history WHERE chat_id=? AND id NOT IN "
                "(SELECT id FROM chat_history WHERE chat_id=? ORDER BY id DESC LIMIT ?)",
                (chat_id, chat_id, keep_last_n),
            )
        log.info("Archived %d messages from chat %d", len(rows), chat_id)
        return len(rows)

    # ── Legacy methods (deprecated — kept for backward compat, no op for chat_id) ──
    # Will be removed once all callers are migrated to the chat_id-aware API.

    def save(self, role: str, content: str) -> int:
        log.warning("DEPRECATED: ChatRepository.save() called without chat_id — use save_for_chat()")
        if not content or not content.strip():
            raise ValueError("Message content must not be empty.")
        tokens = count_tokens(content)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO chat_history (role, content, tokens, timestamp) VALUES (?, ?, ?, ?)",
                (role, content, tokens, ts),
            )
            return cur.lastrowid

    def get_recent_by_token_budget(self, max_tokens: int) -> list[Message]:
        log.warning("DEPRECATED: ChatRepository.get_recent_by_token_budget() — use get_by_token_budget(chat_id, ...)")
        with self._cm.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, tokens FROM (
                    SELECT id, role, content, tokens,
                           SUM(tokens) OVER (ORDER BY id DESC ROWS UNBOUNDED PRECEDING)
                           AS cum_tokens
                    FROM chat_history
                ) WHERE cum_tokens <= ?
                ORDER BY id ASC
                """,
                (max_tokens,),
            ).fetchall()
        return [
            Message(
                id=r["id"], role=MessageRole(r["role"]), content=_strip_base64_images(r["content"]), tokens=r["tokens"]
            )
            for r in rows
        ]

    def total_tokens(self) -> int:
        with self._cm.transaction() as conn:
            result = conn.execute("SELECT COALESCE(SUM(tokens), 0) FROM chat_history").fetchone()[0]
        return int(result)

    def active_count(self) -> int:
        with self._cm.transaction() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0])

    def archive_old(self, keep_last_n: int = ARCHIVE_KEEP_LAST_N) -> int:
        log.warning("DEPRECATED: ChatRepository.archive_old() — use archive_old_for_chat(chat_id, ...)")
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, role, content, tokens, timestamp FROM chat_history "
                "WHERE id NOT IN (SELECT id FROM chat_history ORDER BY id DESC LIMIT ?)",
                (keep_last_n,),
            ).fetchall()
            if not rows:
                return 0
            conn.executemany(
                "INSERT INTO archived_chat_history (role, content, tokens, timestamp) VALUES (?, ?, ?, ?)",
                [(r["role"], r["content"], r["tokens"], r["timestamp"]) for r in rows],
            )
            conn.execute(
                "DELETE FROM chat_history WHERE id NOT IN (SELECT id FROM chat_history ORDER BY id DESC LIMIT ?)",
                (keep_last_n,),
            )
        log.info("Archived %d messages", len(rows))
        return len(rows)
