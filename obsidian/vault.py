"""Obsidian vault management — configuration, initialization, and maintenance."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.obsidian.vault")


VAULT_FOLDERS = [
    "Knowledge",
    "Projects",
    "Ideas",
    "Research",
    "Conversations",
    "Agents",
    "Documentation",
    "Code",
    "Archives",
    "Templates",
    "Daily",
]


@dataclass
class VaultConfig:
    """Configuration for an Obsidian vault."""

    path: str | Path = "./vault"
    vault_name: str = "HardWorkers-Vault"
    create_on_init: bool = True
    folders: list[str] = field(default_factory=lambda: VAULT_FOLDERS)
    template_dir: str = "Templates"
    daily_dir: str = "Daily"
    auto_tag: bool = True
    auto_link: bool = True
    generate_backlinks: bool = True
    yaml_frontmatter: bool = True


class ObsidianVault:
    """Manages an Obsidian vault: initialization, folder structure, file operations."""

    def __init__(self, config: VaultConfig | None = None) -> None:
        self._config = config or VaultConfig()
        self._vault_path = Path(self._config.path)
        if self._config.create_on_init:
            self._init_vault()

    # ── Properties ──────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._vault_path

    @property
    def config(self) -> VaultConfig:
        return self._config

    @property
    def exists(self) -> bool:
        return self._vault_path.exists()

    # ── Vault lifecycle ─────────────────────────────────────────────────────────

    def _init_vault(self) -> None:
        """Initialize the vault directory structure."""
        self._vault_path.mkdir(parents=True, exist_ok=True)

        for folder in self._config.folders:
            folder_path = self._vault_path / folder
            folder_path.mkdir(parents=True, exist_ok=True)

        # Create .obsidian config directory
        obsidian_dir = self._vault_path / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)

        # Write minimal Obsidian config
        self._write_json_config(
            obsidian_dir / "app.json",
            {
                "promptDelete": False,
                "alwaysUpdateLinks": True,
                "newFileLocation": "current",
                "useMarkdownLinks": False,
                "showUnsupportedFiles": True,
            },
        )
        self._write_json_config(
            obsidian_dir / "core-plugins.json",
            {
                "file-explorer": True,
                "global-search": True,
                "switcher": True,
                "graph": True,
                "backlink": True,
                "outgoing-link": True,
                "tag-pane": True,
                "command-palette": True,
                "markdown-importer": True,
                "random-note": True,
                "outline": True,
                "word-count": True,
                "audio-recorder": True,
                "workspaces": True,
                "file-recovery": True,
                "publish": False,
                "sync": False,
            },
        )

        # Create template note
        template_path = self._vault_path / "Templates" / "default.md"
        if not template_path.exists():
            template_path.write_text("---\ntitle: {{title}}\ncreated: {{date}}\ntags: []\n---\n\n# {{title}}\n\n")

        log.info("Obsidian vault initialized at %s (%d folders)", self._vault_path, len(self._config.folders))

    # ── File operations ─────────────────────────────────────────────────────────

    def write_note(
        self,
        folder: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> Path:
        """Write a markdown note to the vault."""
        folder_path = self._vault_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        safe_title = self._sanitize_filename(title)
        note_path = folder_path / f"{safe_title}.md"

        note_path.write_text(content, encoding="utf-8")
        log.info("Note written: %s (%d chars)", note_path.relative_to(self._vault_path), len(content))
        return note_path

    def read_note(self, path: str | Path) -> str | None:
        """Read a note's content."""
        full_path = self._resolve_path(path)
        if full_path and full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None

    def delete_note(self, path: str | Path) -> bool:
        """Delete a note from the vault."""
        full_path = self._resolve_path(path)
        if full_path and full_path.exists():
            full_path.unlink()
            log.info("Note deleted: %s", full_path)
            return True
        return False

    def note_exists(self, title: str) -> bool:
        """Check if a note exists anywhere in the vault."""
        return any(f.stem.lower() == title.lower() for f in self._vault_path.rglob("*.md"))

    def find_note(self, title: str) -> Path | None:
        """Find a note by title (case-insensitive)."""
        for f in self._vault_path.rglob("*.md"):
            if f.stem.lower() == title.lower():
                return f
        return None

    def list_notes(self, folder: str | None = None) -> list[Path]:
        """List all markdown notes, optionally in a specific folder."""
        if folder:
            search_path = self._vault_path / folder
            if search_path.exists():
                return sorted(search_path.rglob("*.md"))
            return []
        return sorted(self._vault_path.rglob("*.md"))

    def list_folders(self) -> list[str]:
        """List all folders in the vault."""
        return sorted(
            str(f.relative_to(self._vault_path))
            for f in self._vault_path.iterdir()
            if f.is_dir() and not f.name.startswith(".")
        )

    def get_stats(self) -> dict[str, Any]:
        """Get vault statistics."""
        notes = self.list_notes()
        total_size = sum(f.stat().st_size for f in notes)
        return {
            "vault_path": str(self._vault_path),
            "total_notes": len(notes),
            "total_folders": len(self.list_folders()),
            "total_size_bytes": total_size,
            "tags": self._collect_tags(notes),
        }

    # ── Internal ────────────────────────────────────────────────────────────────

    def _resolve_path(self, path: str | Path) -> Path:
        path = Path(path)
        if path.is_absolute():
            return path
        return self._vault_path / path

    def _sanitize_filename(self, title: str) -> str:
        sanitized = title.strip().replace(":", "-").replace("/", "-").replace("\\", "-")
        sanitized = sanitized.replace("?", "").replace("*", "").replace("<", "").replace(">", "").replace('"', "")
        return sanitized[:200]

    def _collect_tags(self, notes: list[Path]) -> dict[str, int]:
        import re

        tags: dict[str, int] = {}
        for note in notes:
            try:
                content = note.read_text(encoding="utf-8")
                found = re.findall(r"(?<!\w)#([a-zA-Z][a-zA-Z0-9_/-]+)", content)
                for tag in found:
                    tags[tag] = tags.get(tag, 0) + 1
            except Exception:
                continue
        return tags

    @staticmethod
    def _write_json_config(path: Path, data: dict[str, Any]) -> None:
        import json

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
