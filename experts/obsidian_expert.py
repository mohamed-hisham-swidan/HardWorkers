"""Obsidian Knowledge Expert — reviews vault organization, knowledge graph, and note linking."""

from __future__ import annotations

from typing import Any

from experts.base import ExpertBase


class ObsidianExpert(ExpertBase):
    """Reviews Obsidian vault structure, knowledge organization, and note linking strategies."""

    def __init__(self) -> None:
        super().__init__(
            name="Obsidian Knowledge Expert",
            role="Knowledge Management & Vault Design",
            description="Reviews Obsidian vault organization, knowledge graph design, "
            "note linking strategies, and automatic categorization.",
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        task = plan.get("task", "").lower()

        vault_keywords = ["vault", "obsidian", "note", "markdown", "knowledge", "wiki"]
        for kw in vault_keywords:
            if kw in task:
                findings.append(f"Obsidian/knowledge management task detected: '{kw}'")
                break

        if "folder" in task or "directory" in task:
            findings.append("Folder structure changes — verify vault folder organization is maintained")
        if "link" in task or "backlink" in task:
            findings.append("Linking strategy changes — verify wikilink and backlink consistency")
        if "tag" in task:
            findings.append("Tag changes — verify tag hierarchy and consistency")

        return findings

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        risks: list[str] = []
        task = plan.get("task", "").lower()

        if "restructure" in task or "reorganize" in task:
            risks.append("Vault restructuring can break existing links")
        if "rename" in task:
            risks.append("Renaming notes breaks incoming wikilinks — use aliases")
        if "delete" in task:
            risks.append("Deleting notes removes them from the knowledge graph")
        if "import" in task:
            risks.append("Large imports may create duplicate or unlinked notes")

        return risks

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        return [
            "Maintain consistent folder structure: Knowledge/, Projects/, Ideas/, etc.",
            "Use wikilinks [[Note Name]] for cross-references",
            "Add relevant tags (#tag) to every note for discoverability",
            "Generate backlinks automatically when creating new notes",
            "Create MOC (Map of Content) notes for major topics",
            "Use YAML frontmatter for metadata: title, tags, created, updated",
        ]
