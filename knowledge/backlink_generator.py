"""Backlink generator — finds and generates backlinks between knowledge notes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from knowledge.concept_analyzer import ConceptAnalyzer

log = logging.getLogger("hard_workers.knowledge.backlink_generator")


@dataclass
class Backlink:
    """A backlink from one note to another."""

    source_note: str
    target_note: str
    context: str = ""
    link_type: str = "wikilink"  # wikilink, tag, mention
    confidence: float = 1.0
    occurrences: int = 1


class BacklinkGenerator:
    """Generates and manages backlinks between notes in the knowledge base."""

    def __init__(self, analyzer: ConceptAnalyzer | None = None) -> None:
        self._analyzer = analyzer
        self._backlinks: dict[str, list[Backlink]] = {}

    # ── Public API ──────────────────────────────────────────────────────────────

    def generate_from_text(
        self,
        note_title: str,
        note_content: str,
    ) -> list[Backlink]:
        """Generate backlinks from a note's content by finding references to other concepts."""
        backlinks: list[Backlink] = []
        found_targets: dict[str, list[str]] = {}

        # Find existing wikilinks
        for match in re.finditer(r"\[\[([^\]]+)\]\]", note_content):
            target = match.group(1).strip()
            context = self._extract_context(note_content, match.start(), match.end())
            if target not in found_targets:
                found_targets[target] = []
            found_targets[target].append(context)

        # Find concept mentions via analyzer
        if self._analyzer:
            for concept in self._analyzer.get_all_concepts():
                if concept.name.lower() in note_content.lower():
                    cname = concept.name
                    if cname not in found_targets:
                        idx = note_content.lower().find(cname.lower())
                        if idx >= 0:
                            context = self._extract_context(note_content, idx, idx + len(cname))
                            found_targets[cname] = [context]

        # Find tag-like patterns
        for match in re.finditer(r"#([a-zA-Z][a-zA-Z0-9_/-]+)", note_content):
            tag = match.group(1).strip()
            if tag not in found_targets:
                found_targets[tag] = []

        # Create Backlink objects
        for target, contexts in found_targets.items():
            bl = Backlink(
                source_note=note_title,
                target_note=target,
                context=" | ".join(contexts)[:300],
                link_type="wikilink" if f"[[{target}]]" in note_content else "mention",
                occurrences=len(contexts),
            )
            backlinks.append(bl)

        if note_title not in self._backlinks:
            self._backlinks[note_title] = []
        self._backlinks[note_title].extend(backlinks)

        log.info("Generated %d backlinks from '%s'", len(backlinks), note_title)
        return backlinks

    def generate_for_vault(
        self,
        vault_path: str | Path,
        pattern: str = "*.md",
    ) -> dict[str, list[Backlink]]:
        """Generate backlinks for all notes in a vault directory."""
        vault = Path(vault_path)
        if not vault.exists():
            log.error("Vault path not found: %s", vault_path)
            return {}

        result: dict[str, list[Backlink]] = {}
        for note_file in vault.rglob(pattern):
            try:
                title = note_file.stem
                content = note_file.read_text(encoding="utf-8")
                bls = self.generate_from_text(title, content)
                if bls:
                    result[title] = bls
            except Exception as exc:
                log.warning("Failed to process %s: %s", note_file.name, exc)

        log.info("Generated backlinks for %d notes in vault", len(result))
        return result

    def get_backlinks(self, note_title: str) -> list[Backlink]:
        """Get all backlinks pointing to a given note."""
        normalized = note_title.lower().strip()
        results: list[Backlink] = []
        for source, bls in self._backlinks.items():
            for bl in bls:
                if bl.target_note.lower().strip() == normalized:
                    results.append(bl)
        return results

    def get_outgoing_links(self, note_title: str) -> list[Backlink]:
        """Get all outgoing links from a given note."""
        return list(self._backlinks.get(note_title, []))

    def generate_wikilinks_section(self, note_title: str, note_content: str) -> str:
        """Generate a backlinks section to append to a note."""
        backlinks = self.get_backlinks(note_title)
        if not backlinks:
            return ""

        lines = ["", "---", "## Backlinks"]
        seen: set[str] = set()
        for bl in backlinks:
            if bl.source_note not in seen:
                lines.append(f"- [[{bl.source_note}]]")
                if bl.context:
                    lines.append(f"  - *{bl.context[:100]}*")
                seen.add(bl.source_note)

        return "\n".join(lines)

    def get_all(self) -> dict[str, list[Backlink]]:
        return dict(self._backlinks)

    def get_stats(self) -> dict[str, Any]:
        total_bls = sum(len(bls) for bls in self._backlinks.values())
        return {
            "total_notes_with_links": len(self._backlinks),
            "total_backlinks": total_bls,
            "avg_per_note": total_bls / max(len(self._backlinks), 1),
        }

    def clear(self) -> None:
        self._backlinks.clear()

    # ── Internal ────────────────────────────────────────────────────────────────

    def _extract_context(self, text: str, start: int, end: int, window: int = 60) -> str:
        ctx_start = max(0, start - window)
        ctx_end = min(len(text), end + window)
        context = text[ctx_start:ctx_end].strip()
        # Clean up context boundaries
        if ctx_start > 0:
            context = "..." + context
        if ctx_end < len(text):
            context = context + "..."
        return context
