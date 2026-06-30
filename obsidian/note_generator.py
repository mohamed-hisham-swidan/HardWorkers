"""Obsidian note generator — creates formatted markdown notes with frontmatter, tags, and links."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from obsidian.vault import ObsidianVault

log = logging.getLogger("hard_workers.obsidian.note_generator")


@dataclass
class ObsidianNote:
    """Represents a single Obsidian markdown note with metadata."""

    title: str
    content: str
    folder: str = "Knowledge"
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    frontmatter: dict[str, Any] = field(default_factory=dict)
    created: str = ""
    updated: str = ""

    def __post_init__(self) -> None:
        if not self.created:
            self.created = datetime.now().strftime("%Y-%m-%d")
        if not self.updated:
            self.updated = self.created

    def render(self) -> str:
        """Render the note as a complete markdown string with YAML frontmatter."""
        parts: list[str] = []

        # YAML frontmatter
        frontmatter_lines = ["---"]
        frontmatter_lines.append(f'title: "{self.title}"')
        frontmatter_lines.append(f"created: {self.created}")
        frontmatter_lines.append(f"updated: {self.updated}")

        if self.tags:
            tags_str = ", ".join(f'"{t}"' for t in self.tags)
            frontmatter_lines.append(f"tags: [{tags_str}]")

        if self.aliases:
            for alias in self.aliases:
                frontmatter_lines.append(f"aliases: [{alias}]")
                break

        for key, value in self.frontmatter.items():
            if isinstance(value, str):
                frontmatter_lines.append(f'{key}: "{value}"')
            else:
                frontmatter_lines.append(f"{key}: {value}")

        frontmatter_lines.append("---")
        parts.append("\n".join(frontmatter_lines))

        # Main content
        parts.append("")
        parts.append(f"# {self.title}")
        parts.append("")

        if self.content:
            parts.append(self.content)

        # Tags section
        if self.tags:
            parts.append("")
            parts.append("---")
            tags_line = " ".join(f"#{t}" for t in self.tags)
            parts.append(tags_line)

        # Links section
        if self.links:
            parts.append("")
            parts.append("## Links")
            for link in self.links:
                parts.append(f"- [[{link}]]")

        return "\n".join(parts).strip()

    @property
    def wikilinks(self) -> list[str]:
        return re.findall(r"\[\[([^\]]+)\]\]", self.content)


class NoteGenerator:
    """Generates structured Obsidian notes from different content types."""

    def __init__(self, vault: ObsidianVault) -> None:
        self._vault = vault

    # ── Note generation ─────────────────────────────────────────────────────────

    def generate_knowledge_note(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> ObsidianNote:
        """Generate a knowledge note from extracted content."""
        safe_tags = list(set(tags or []))
        note = ObsidianNote(
            title=title,
            content=self._format_knowledge_content(content, sources),
            folder="Knowledge",
            tags=safe_tags,
            links=list(set(sources or [])),
        )
        path = self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
        log.info("Knowledge note created: %s", path.name)
        return note

    def generate_project_note(
        self,
        title: str,
        description: str,
        tags: list[str] | None = None,
        status: str = "active",
    ) -> ObsidianNote:
        note = ObsidianNote(
            title=title,
            content=self._format_project_content(description, status),
            folder="Projects",
            tags=list(set(tags or [])),
            frontmatter={"status": status},
        )
        path = self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
        log.info("Project note created: %s", path.name)
        return note

    def generate_idea_note(
        self,
        title: str,
        description: str,
        tags: list[str] | None = None,
    ) -> ObsidianNote:
        note = ObsidianNote(
            title=title,
            content=self._format_idea_content(description),
            folder="Ideas",
            tags=list(set(tags or [])),
        )
        path = self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
        log.info("Idea note created: %s", path.name)
        return note

    def generate_research_note(
        self,
        title: str,
        content: str,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> ObsidianNote:
        note = ObsidianNote(
            title=title,
            content=self._format_research_content(content, sources),
            folder="Research",
            tags=list(set(tags or [])),
            links=list(set(sources or [])),
        )
        path = self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
        log.info("Research note created: %s", path.name)
        return note

    def generate_conversation_note(
        self,
        title: str,
        summary: str,
        key_points: list[str],
        date: str | None = None,
    ) -> ObsidianNote:
        note = ObsidianNote(
            title=title,
            content=self._format_conversation_content(summary, key_points),
            folder="Conversations",
            tags=["conversation"],
            created=date or datetime.now().strftime("%Y-%m-%d"),
        )
        path = self._vault.write_note(note.folder, note.title, note.render())
        log.info("Conversation note created: %s", path.name)
        return note

    def generate_code_note(
        self,
        title: str,
        code: str,
        language: str = "unknown",
        description: str = "",
        tags: list[str] | None = None,
    ) -> ObsidianNote:
        safe_tags = list(set((tags or []) + [f"code-{language}"]))
        content_parts = [description]
        if code:
            content_parts.append(f"```{language}\n{code}\n```")
        note = ObsidianNote(
            title=title,
            content="\n\n".join(content_parts),
            folder="Code",
            tags=safe_tags,
            frontmatter={"language": language},
        )
        path = self._vault.write_note(note.folder, note.title, note.render(), tags=note.tags)
        log.info("Code note created: %s", path.name)
        return note

    # ── Content formatters ──────────────────────────────────────────────────────

    def _format_knowledge_content(self, content: str, sources: list[str] | None) -> str:
        parts = [content]
        if sources:
            parts.append("\n## Sources\n")
            for src in sources:
                parts.append(f"- [[{src}]]")
        return "\n".join(parts)

    def _format_project_content(self, description: str, status: str) -> str:
        return f"**Status:** {status}\n\n## Description\n{description}\n\n## Tasks\n- [ ] \n\n## Notes\n"

    def _format_idea_content(self, description: str) -> str:
        return f"## Description\n{description}\n\n## Why\n\n## Next Steps\n- [ ] \n"

    def _format_research_content(self, content: str, sources: list[str] | None) -> str:
        parts = [f"## Summary\n{content}"]
        if sources:
            parts.append("## Sources\n" + "\n".join(f"- [[{s}]]" for s in sources))
        parts.append("## Key Findings\n- \n\n## Open Questions\n- ")
        return "\n\n".join(parts)

    def _format_conversation_content(self, summary: str, key_points: list[str]) -> str:
        points = "\n".join(f"- {p}" for p in key_points)
        return f"## Summary\n{summary}\n\n## Key Points\n{points}\n\n## Action Items\n- [ ] \n"
