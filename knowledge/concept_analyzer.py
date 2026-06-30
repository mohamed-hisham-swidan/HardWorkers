"""Concept analyzer — identifies, defines, and relates concepts across the knowledge base."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from knowledge.extractor import ExtractedKnowledge

log = logging.getLogger("hard_workers.knowledge.concept_analyzer")


@dataclass
class ConceptRelation:
    """A relationship between two concepts."""

    source: str
    target: str
    relation_type: str  # e.g., "depends_on", "extends", "implements", "related_to"
    strength: float = 0.5
    context: str = ""
    occurrences: int = 1


@dataclass
class Concept:
    """A structured concept with definitions, usage patterns, and relationships."""

    name: str
    aliases: list[str] = field(default_factory=list)
    definition: str = ""
    summary: str = ""
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    relations: list[ConceptRelation] = field(default_factory=list)
    occurrences: int = 1
    importance: float = 0.5
    first_seen: str = ""
    last_seen: str = ""
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.first_seen:
            self.first_seen = now
        if not self.last_seen:
            self.last_seen = now


# Categorization keywords
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "programming": [
        "function",
        "class",
        "method",
        "variable",
        "api",
        "algorithm",
        "code",
        "python",
        "javascript",
        "typescript",
        "rust",
        "go",
        "java",
        "c++",
    ],
    "ai_ml": [
        "neural",
        "model",
        "training",
        "inference",
        "embedding",
        "vector",
        "llm",
        "transformer",
        "attention",
        "fine-tune",
        "dataset",
        "loss",
        "gradient",
    ],
    "data": [
        "database",
        "sql",
        "query",
        "schema",
        "table",
        "index",
        "migration",
        "cache",
        "storage",
        "file",
        "document",
    ],
    "architecture": [
        "architecture",
        "pattern",
        "design",
        "service",
        "microservice",
        "dependency",
        "component",
        "module",
        "interface",
        "protocol",
    ],
    "devops": ["deploy", "ci/cd", "pipeline", "docker", "kubernetes", "cloud", "monitoring", "logging", "test", "qa"],
    "security": [
        "security",
        "auth",
        "encryption",
        "vulnerability",
        "permission",
        "token",
        "oauth",
        "https",
        "firewall",
    ],
    "business": [
        "project",
        "task",
        "requirement",
        "feature",
        "roadmap",
        "stakeholder",
        "milestone",
        "deadline",
        "budget",
        "sprint",
    ],
}


class ConceptAnalyzer:
    """Analyzes concepts extracted from knowledge sources."""

    def __init__(self) -> None:
        self._concepts: dict[str, Concept] = {}

    # ── Public API ──────────────────────────────────────────────────────────────

    def ingest(self, knowledge: ExtractedKnowledge) -> list[Concept]:
        """Ingest extracted knowledge and update/add concepts."""
        created: list[Concept] = []
        for concept_name in knowledge.concepts:
            concept = self._update_or_create(concept_name, knowledge)
            created.append(concept)

        # Detect relationships between concepts in the same knowledge unit
        self._detect_cooccurrence_relations(knowledge.concepts, knowledge)

        log.info("Ingested %d concepts from '%s'", len(knowledge.concepts), knowledge.title)
        return created

    def ingest_batch(self, knowledge_list: list[ExtractedKnowledge]) -> list[Concept]:
        all_concepts: list[Concept] = []
        for knowledge in knowledge_list:
            all_concepts.extend(self.ingest(knowledge))
        return all_concepts

    def get_concept(self, name: str) -> Concept | None:
        return self._concepts.get(self._normalize(name))

    def get_all_concepts(self) -> list[Concept]:
        return list(self._concepts.values())

    def search_concepts(self, query: str) -> list[Concept]:
        q = query.lower()
        results: list[Concept] = []
        for concept in self._concepts.values():
            if q in concept.name.lower() or q in concept.definition.lower() or q in concept.summary.lower():
                results.append(concept)
        return sorted(results, key=lambda c: c.importance, reverse=True)

    def get_concepts_by_category(self, category: str) -> list[Concept]:
        return [c for c in self._concepts.values() if c.category == category]

    def get_related_concepts(self, name: str, max_depth: int = 1) -> list[Concept]:
        """Get concepts related to a given concept, optionally traversing relations."""
        concept = self.get_concept(name)
        if not concept:
            return []
        related: list[Concept] = []
        seen: set[str] = {self._normalize(name)}
        queue: list[tuple[str, int]] = [(self._normalize(name), 0)]

        while queue:
            current_name, depth = queue.pop(0)
            current = self._concepts.get(current_name)
            if not current:
                continue
            if depth > max_depth:
                break
            for relation in current.relations:
                for target_name in (relation.source, relation.target):
                    normalized = self._normalize(target_name)
                    if normalized != current_name and normalized not in seen:
                        target_concept = self._concepts.get(normalized)
                        if target_concept:
                            related.append(target_concept)
                            seen.add(normalized)
                            queue.append((normalized, depth + 1))
        return related

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_concepts": len(self._concepts),
            "categories": self._category_counts(),
            "total_relations": sum(len(c.relations) for c in self._concepts.values()),
            "top_concepts": sorted(
                self._concepts.values(),
                key=lambda c: c.importance,
                reverse=True,
            )[:10],
        }

    # ── Internal ────────────────────────────────────────────────────────────────

    def _normalize(self, name: str) -> str:
        return name.lower().strip()

    def _update_or_create(self, name: str, knowledge: ExtractedKnowledge) -> Concept:
        normalized = self._normalize(name)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if normalized in self._concepts:
            concept = self._concepts[normalized]
            concept.occurrences += 1
            concept.last_seen = now
            if knowledge.source_path not in concept.sources:
                concept.sources.append(knowledge.source_path)
            concept.importance = max(concept.importance, knowledge.importance)
            return concept

        category = self._categorize(name)
        definition = self._infer_definition(name, knowledge)
        concept = Concept(
            name=name,
            definition=definition,
            summary=knowledge.summary,
            category=category,
            tags=[knowledge.source_type.value] + knowledge.tags[:3],
            occurrences=1,
            importance=knowledge.importance,
            first_seen=now,
            last_seen=now,
            sources=[knowledge.source_path] if knowledge.source_path else [],
        )
        self._concepts[normalized] = concept
        return concept

    def _detect_cooccurrence_relations(
        self,
        concepts: list[str],
        knowledge: ExtractedKnowledge,
    ) -> None:
        if len(concepts) < 2:
            return
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                c1, c2 = concepts[i], concepts[j]
                self._add_relation(c1, c2, "related_to", strength=0.3, context=knowledge.title)

    def _add_relation(
        self,
        source: str,
        target: str,
        relation_type: str,
        strength: float = 0.5,
        context: str = "",
    ) -> None:
        def add_to(name_a: str, name_b: str) -> None:
            normalized_a = self._normalize(name_a)
            concept = self._concepts.get(normalized_a)
            if not concept:
                return
            for existing in concept.relations:
                if (
                    self._normalize(existing.source) == self._normalize(name_a)
                    and self._normalize(existing.target) == self._normalize(name_b)
                    and existing.relation_type == relation_type
                ):
                    existing.occurrences += 1
                    existing.strength = min(existing.strength + 0.1, 1.0)
                    return
            concept.relations.append(
                ConceptRelation(
                    source=name_a,
                    target=name_b,
                    relation_type=relation_type,
                    strength=strength,
                    context=context,
                )
            )

        add_to(source, target)
        add_to(target, source)

    def _categorize(self, name: str) -> str:
        name_lower = name.lower()
        best_score = 0
        best_category = "general"
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in name_lower)
            if score > best_score:
                best_score = score
                best_category = category
        return best_category

    def _infer_definition(self, name: str, knowledge: ExtractedKnowledge) -> str:
        content = knowledge.content
        name_lower = name.lower()

        # Try to find definition patterns
        patterns = [
            rf"{re.escape(name)}\s+(?:is|are|was|were|refers to|means|defined as)\s+([^.]*\.)",
            rf"(?:The|An?)\s+{re.escape(name)}\s+(?:is|are|was|were)\s+([^.]*\.)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback to surrounding context
        idx = content.lower().find(name_lower)
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(content), idx + len(name) + 200)
            context = content[start:end].strip()
            if len(context) > 30:
                return context[:300]
        return ""
