"""Database schema migrations (additive, never destructive) — HardWorkres."""

from __future__ import annotations

import sqlite3

from utils.logging_setup import get_logger

log = get_logger("database.migrations")

# Each entry is (version, sql). Applied in order; never removed or modified.
_MIGRATIONS: list[tuple[int, str]] = [
    # ── v1: Core schema (original HardWorkres tables) ──────────────────────────────
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT    NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content    TEXT    NOT NULL,
            tokens     INTEGER NOT NULL DEFAULT 0,
            timestamp  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS archived_chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            tokens      INTEGER NOT NULL DEFAULT 0,
            timestamp   TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_key    TEXT    UNIQUE NOT NULL,
            fact_value  TEXT    NOT NULL,
            importance  INTEGER NOT NULL DEFAULT 5
                        CHECK (importance BETWEEN 1 AND 10),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            summary    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_chat_ts      ON chat_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_fact_key     ON user_profile(fact_key);
        CREATE INDEX IF NOT EXISTS idx_fact_imp     ON user_profile(importance DESC);
    """,
    ),
    # ── v2: Model Registry + Memory Profiles + Workspaces ────────────────────
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS memory_profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    UNIQUE NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO memory_profiles (name, description)
        VALUES
            ('Shared',     'Global shared memory — all models read from the same pool'),
            ('No Memory',  'Completely isolated — no long-term memory context'),
            ('Research',   'Dedicated memory for research sessions'),
            ('Coding',     'Dedicated memory for coding sessions'),
            ('Writing',    'Dedicated memory for writing sessions');

        CREATE TABLE IF NOT EXISTS model_registry (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT    UNIQUE NOT NULL,
            provider           TEXT    NOT NULL DEFAULT 'ollama'
                               CHECK (provider IN ('ollama','openai','anthropic','openrouter','groq','gemini','deepseek','together','custom')),
            category           TEXT    NOT NULL DEFAULT 'General',
            description        TEXT    NOT NULL DEFAULT '',
            system_prompt      TEXT    NOT NULL DEFAULT '',
            base_model         TEXT    NOT NULL DEFAULT '',
            api_url            TEXT    NOT NULL DEFAULT '',
            api_key            TEXT    NOT NULL DEFAULT '',
            api_password       TEXT    NOT NULL DEFAULT '',
            memory_mode        TEXT    NOT NULL DEFAULT 'shared'
                               CHECK (memory_mode IN ('none','dedicated','shared')),
            memory_profile_id  INTEGER REFERENCES memory_profiles(id) ON DELETE SET NULL,
            created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_model_reg_provider  ON model_registry(provider);
        CREATE INDEX IF NOT EXISTS idx_model_reg_category  ON model_registry(category);

        CREATE TABLE IF NOT EXISTS workspaces (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            name               TEXT    UNIQUE NOT NULL,
            active_model       TEXT    NOT NULL DEFAULT '',
            memory_profile_id  INTEGER REFERENCES memory_profiles(id) ON DELETE SET NULL,
            router_mode        TEXT    NOT NULL DEFAULT 'disabled'
                               CHECK (router_mode IN ('disabled','auto','category')),
            category           TEXT    NOT NULL DEFAULT 'General',
            description        TEXT    NOT NULL DEFAULT '',
            created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO workspaces (name, category, description)
        VALUES
            ('Default',  'General',       'Default workspace'),
            ('Coding',   'Coding',        'Coding & programming workspace'),
            ('Research', 'Research',      'Research and study workspace'),
            ('Writing',  'Writing',       'Creative and technical writing'),
            ('Obsidian', 'Obsidian',      'Obsidian vault knowledge management');
    """,
    ),
    # ── v3: Multi-Chat System (chats, per-chat messages, per-chat memory) ─────
    (
        3,
        """
        -- Only proceed if not already applied
        CREATE TABLE IF NOT EXISTS chats (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            name         TEXT    NOT NULL,
            is_pinned    INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(workspace_id, name)
        );

        CREATE INDEX IF NOT EXISTS idx_chats_ws_pin_ts
            ON chats(workspace_id, is_pinned DESC, updated_at DESC);

        ALTER TABLE chat_history ADD COLUMN chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS idx_messages_chat_ts
            ON chat_history(chat_id, timestamp DESC);

        CREATE INDEX IF NOT EXISTS idx_messages_chat_id
            ON chat_history(chat_id);

        -- Per-chat structured memory (KV facts)
        CREATE TABLE IF NOT EXISTS chat_memory_facts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            fact_key    TEXT    NOT NULL,
            fact_value  TEXT    NOT NULL,
            importance  INTEGER NOT NULL DEFAULT 5
                        CHECK (importance BETWEEN 1 AND 10),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(chat_id, fact_key)
        );

        CREATE INDEX IF NOT EXISTS idx_facts_chat_key
            ON chat_memory_facts(chat_id, fact_key);

        -- Per-chat semantic memory (orchestrator summaries)
        CREATE TABLE IF NOT EXISTS chat_summaries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
            summary     TEXT    NOT NULL,
            source      TEXT    NOT NULL DEFAULT 'orchestrator',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_summaries_chat_ts
            ON chat_summaries(chat_id, created_at DESC);
    """,
    ),
    # ── v4: supports_vision column for model_registry ─────────────────────
    (
        4,
        """
        ALTER TABLE model_registry ADD COLUMN supports_vision INTEGER NOT NULL DEFAULT 0;
    """,
    ),
    # ── v5: attachment_path and file_type columns for chat tables ────────
    (
        5,
        """
        ALTER TABLE chat_history ADD COLUMN attachment_path TEXT DEFAULT NULL;
        ALTER TABLE chat_history ADD COLUMN file_type TEXT DEFAULT NULL;
        ALTER TABLE archived_chat_history ADD COLUMN attachment_path TEXT DEFAULT NULL;
        ALTER TABLE archived_chat_history ADD COLUMN file_type TEXT DEFAULT NULL;
    """,
    ),
]


def _validate_v3_fk(conn: sqlite3.Connection) -> None:
    """Check for FK violations in chat_history.chat_id after v3 migration."""
    try:
        cursor = conn.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()
        if violations:
            log.warning("FK violations found: %s", violations)
    except Exception as exc:
        log.warning("Could not validate FK constraints: %s", exc)


def _ensure_v3_columns(conn: sqlite3.Connection) -> None:
    """Add chat_id column to chat_history if it does not exist."""
    cursor = conn.execute("PRAGMA table_info(chat_history)")
    columns = {row[1] for row in cursor.fetchall()}
    if "chat_id" not in columns:
        conn.execute("ALTER TABLE chat_history ADD COLUMN chat_id INTEGER REFERENCES chats(id) ON DELETE CASCADE")
        log.info("Added chat_id column to chat_history")


def _migrate_v3_data(conn: sqlite3.Connection) -> None:
    """Populate per-workspace default chats and backfill chat_id on legacy messages
    after the v3 schema has been applied."""
    from config.constants import DEFAULT_CHAT_NAME

    # 1. Ensure every workspace has a "General" chat — single INSERT…SELECT, no N+1
    conn.execute(
        "INSERT OR IGNORE INTO chats (workspace_id, name) SELECT id, ? FROM workspaces",
        (DEFAULT_CHAT_NAME,),
    )

    # 2. Backfill legacy messages (chat_id IS NULL) into the Default workspace's
    #    first chat (the "General" chat just created).
    default_ws = conn.execute("SELECT id FROM workspaces WHERE name='Default'").fetchone()
    if default_ws is not None:
        default_chat = conn.execute(
            "SELECT id FROM chats WHERE workspace_id=? ORDER BY id ASC LIMIT 1",
            (default_ws["id"],),
        ).fetchone()
        if default_chat is not None:
            conn.execute(
                "UPDATE chat_history SET chat_id=? WHERE chat_id IS NULL",
                (default_chat["id"],),
            )
            updated = conn.execute("SELECT changes()").fetchone()[0]
            if updated:
                log.info(
                    "Associated %d legacy messages with chat %d (workspace 'Default')",
                    updated,
                    default_chat["id"],
                )


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending migrations to the given connection."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    applied: set[int] = {row[0] for row in conn.execute("SELECT version FROM schema_version")}

    for version, sql in _MIGRATIONS:
        if version in applied:
            continue
        log.info("Applying migration v%d", version)
        conn.executescript(sql)
        conn.execute("INSERT OR IGNORE INTO schema_version(version) VALUES (?)", (version,))
        conn.commit()
        log.info("Migration v%d applied successfully", version)

        # ── Post-migration data backfill for v3 ─────────────────────────────
        if version == 3:
            conn.execute("BEGIN IMMEDIATE")
            _ensure_v3_columns(conn)
            _migrate_v3_data(conn)
            _validate_v3_fk(conn)
            conn.commit()
