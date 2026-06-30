"""Vault structure management — folder organization, tags, and linking strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from obsidian.vault import ObsidianVault

log = logging.getLogger("hard_workers.obsidian.structure")


# Canonical folder definitions
FOLDER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "Knowledge": {
        "description": "General knowledge and reference notes",
        "icon": "📚",
        "tags": ["knowledge"],
        "auto_categorize": True,
    },
    "Projects": {
        "description": "Active and completed projects",
        "icon": "📋",
        "tags": ["project"],
        "auto_categorize": True,
    },
    "Ideas": {
        "description": "New ideas and brainstorming",
        "icon": "💡",
        "tags": ["idea"],
        "auto_categorize": True,
    },
    "Research": {
        "description": "Research notes and findings",
        "icon": "🔬",
        "tags": ["research"],
        "auto_categorize": True,
    },
    "Conversations": {
        "description": "Saved conversation summaries and transcripts",
        "icon": "💬",
        "tags": ["conversation"],
        "auto_categorize": True,
    },
    "Agents": {
        "description": "Agent configurations and workflow definitions",
        "icon": "🤖",
        "tags": ["agent"],
        "auto_categorize": False,
    },
    "Documentation": {
        "description": "Technical and user documentation",
        "icon": "📄",
        "tags": ["documentation"],
        "auto_categorize": True,
    },
    "Code": {
        "description": "Code snippets, references, and analysis",
        "icon": "💻",
        "tags": ["code"],
        "auto_categorize": True,
    },
    "Archives": {
        "description": "Archived or historical notes",
        "icon": "📦",
        "tags": ["archive"],
        "auto_categorize": False,
    },
    "Templates": {
        "description": "Note templates",
        "icon": "📝",
        "tags": ["template"],
        "auto_categorize": False,
    },
    "Daily": {
        "description": "Daily notes",
        "icon": "📅",
        "tags": ["daily"],
        "auto_categorize": False,
    },
}


@dataclass
class VaultFolder:
    """Definition of a vault folder with metadata."""

    name: str
    description: str = ""
    icon: str = "📁"
    default_tags: list[str] = field(default_factory=list)
    auto_categorize: bool = True


class VaultStructure:
    """Manages vault folder organization and auto-categorization."""

    def __init__(self, vault: ObsidianVault) -> None:
        self._vault = vault

    # ── Folder management ───────────────────────────────────────────────────────

    def get_folders(self) -> list[VaultFolder]:
        return [
            VaultFolder(
                name=name,
                description=meta["description"],
                icon=meta["icon"],
                default_tags=meta["tags"],
                auto_categorize=meta["auto_categorize"],
            )
            for name, meta in FOLDER_DEFINITIONS.items()
        ]

    def suggest_folder(self, title: str, content: str, tags: list[str] | None = None) -> str:
        """Automatically suggest a folder for a new note based on content analysis."""
        text = f"{title} {content}".lower()
        all_tags = set(t.lower() for t in (tags or []))

        scoring: dict[str, float] = {}
        for folder_name, meta in FOLDER_DEFINITIONS.items():
            score = 0.0

            # Score by tag match
            tag_matches = all_tags & set(meta["tags"])
            score += len(tag_matches) * 3

            # Score by keyword match
            keyword_map = {
                "Knowledge": ["knowledge", "reference", "learn", "concept", "theory"],
                "Projects": ["project", "task", "milestone", "deadline", "deliverable"],
                "Ideas": ["idea", "brainstorm", "think", "maybe", "suggest"],
                "Research": ["research", "study", "find", "analyze", "investigate"],
                "Conversations": ["chat", "conversation", "meeting", "discussion", "talk"],
                "Documentation": ["guide", "document", "manual", "how to", "tutorial"],
                "Code": ["code", "python", "function", "class", "algorithm", "script"],
                "Archives": ["archive", "old", "deprecated", "backup"],
            }
            keywords = keyword_map.get(folder_name, [])
            keyword_matches = sum(1 for kw in keywords if kw in text)
            score += keyword_matches * 2

            # Check auto_categorize
            if not meta["auto_categorize"]:
                score *= 0.3

            if score > 0:
                scoring[folder_name] = score

        if not scoring:
            return "Knowledge"

        best = max(scoring, key=scoring.get)
        return best

    def ensure_folder_structure(self) -> None:
        """Ensure all canonical folders exist in the vault."""
        for folder_name in FOLDER_DEFINITIONS:
            folder_path = self._vault.path / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
        log.info("Folder structure verified — %d folders", len(FOLDER_DEFINITIONS))

    def generate_index_notes(self) -> list[Path]:
        """Generate index/MOC notes for each major folder."""
        index_notes: list[Path] = []
        for folder_name, meta in FOLDER_DEFINITIONS.items():
            if folder_name in ("Templates", "Daily", "Archives"):
                continue
            notes = self._vault.list_notes(folder_name)
            if not notes:
                continue

            content_parts = [
                f"# {meta['icon']} {folder_name}\n",
                f"{meta['description']}\n",
                f"**{len(notes)} notes**\n",
            ]
            for note in sorted(notes):
                note_title = note.stem
                content_parts.append(f"- [[{note_title}]]")

            index_content = "\n".join(content_parts)
            index_path = self._vault.write_note(folder_name, f"_{folder_name} Index", index_content)
            index_notes.append(index_path)

        log.info("Generated %d index notes", len(index_notes))
        return index_notes

    def get_folder_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for each folder."""
        stats: dict[str, dict[str, Any]] = {}
        for folder_name, meta in FOLDER_DEFINITIONS.items():
            notes = self._vault.list_notes(folder_name)
            stats[folder_name] = {
                "name": folder_name,
                "description": meta["description"],
                "icon": meta["icon"],
                "note_count": len(notes),
                "size_bytes": sum(n.stat().st_size for n in notes),
            }
        return stats
