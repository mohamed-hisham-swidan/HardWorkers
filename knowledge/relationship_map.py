"""Relationship map — maps and visualizes connections between knowledge concepts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from knowledge.concept_analyzer import ConceptAnalyzer

log = logging.getLogger("hard_workers.knowledge.relationship_map")


class RelationshipType(Enum):
    DEPENDS_ON = "depends_on"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    CONTAINS = "contains"
    USES = "uses"
    PRODUCES = "produces"
    PRECEDES = "precedes"
    FOLLOWS = "follows"
    CONFLICTS_WITH = "conflicts_with"
    SIMILAR_TO = "similar_to"


@dataclass
class Relationship:
    """A relationship between two concepts in the knowledge graph."""

    source: str
    target: str
    type: RelationshipType = RelationshipType.RELATED_TO
    strength: float = 0.5
    weight: int = 1
    context: str = ""
    bidirectional: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class RelationshipMap:
    """Builds and queries a map of relationships between concepts."""

    def __init__(self, analyzer: ConceptAnalyzer | None = None) -> None:
        self._analyzer = analyzer
        self._relationships: dict[str, list[Relationship]] = {}
        self._edges: set[tuple[str, str, str]] = set()

    # ── Public API ──────────────────────────────────────────────────────────────

    def build_from_analyzer(self, analyzer: ConceptAnalyzer) -> None:
        """Build relationship map from a concept analyzer's data."""
        self._analyzer = analyzer
        self.clear()
        for concept in analyzer.get_all_concepts():
            for rel in concept.relations:
                self.add_relationship(
                    source=rel.source,
                    target=rel.target,
                    type=RelationshipType(rel.relation_type)
                    if rel.relation_type in RelationshipType._value2member_map_
                    else RelationshipType.RELATED_TO,
                    strength=rel.strength,
                    context=rel.context,
                )
        log.info("Built relationship map with %d edges from analyzer", len(self._edges))

    def add_relationship(
        self,
        source: str,
        target: str,
        type: RelationshipType = RelationshipType.RELATED_TO,
        strength: float = 0.5,
        context: str = "",
    ) -> None:
        """Add a relationship between two concepts."""
        edge_key = (source.lower().strip(), target.lower().strip(), type.value)
        if edge_key in self._edges:
            # Update existing
            for rel in self._relationships.get(source.lower().strip(), []):
                if rel.target.lower().strip() == target.lower().strip() and rel.type == type:
                    rel.weight += 1
                    rel.strength = min(rel.strength + 0.05, 1.0)
                    if context and context not in rel.context:
                        rel.context = f"{rel.context}; {context}" if rel.context else context
                    return

        rel = Relationship(
            source=source,
            target=target,
            type=type,
            strength=strength,
            context=context,
            bidirectional=type
            in (
                RelationshipType.RELATED_TO,
                RelationshipType.SIMILAR_TO,
                RelationshipType.CONFLICTS_WITH,
            ),
        )
        normalized_source = source.lower().strip()
        if normalized_source not in self._relationships:
            self._relationships[normalized_source] = []
        self._relationships[normalized_source].append(rel)
        self._edges.add(edge_key)

    def remove_relationship(self, source: str, target: str, type: RelationshipType | None = None) -> bool:
        normalized_source = source.lower().strip()
        if normalized_source not in self._relationships:
            return False
        before = len(self._relationships[normalized_source])
        if type:
            self._relationships[normalized_source] = [
                r
                for r in self._relationships[normalized_source]
                if not (r.target.lower().strip() == target.lower().strip() and r.type == type)
            ]
            self._edges.discard((normalized_source, target.lower().strip(), type.value if type else ""))
        else:
            self._relationships[normalized_source] = [
                r for r in self._relationships[normalized_source] if r.target.lower().strip() != target.lower().strip()
            ]
            self._edges = {e for e in self._edges if not (e[0] == normalized_source and e[1] == target.lower().strip())}
        return len(self._relationships[normalized_source]) < before

    def get_relationships(
        self,
        concept: str,
        type: RelationshipType | None = None,
    ) -> list[Relationship]:
        """Get all relationships for a concept."""
        normalized = concept.lower().strip()
        results: list[Relationship] = list(self._relationships.get(normalized, []))
        if type:
            results = [r for r in results if r.type == type]
        return results

    def find_path(
        self,
        source: str,
        target: str,
        max_depth: int = 4,
    ) -> list[list[Relationship]]:
        """Find all paths between two concepts using BFS."""
        normalized_source = source.lower().strip()
        normalized_target = target.lower().strip()
        if normalized_source == normalized_target:
            return []

        paths: list[list[Relationship]] = []
        visited: set[str] = set()
        queue: list[tuple[str, list[Relationship]]] = [(normalized_source, [])]

        while queue:
            current, path = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            if current == normalized_target and path:
                paths.append(path)
                continue

            if len(path) >= max_depth:
                continue

            for rel in self._relationships.get(current, []):
                next_node = rel.target.lower().strip()
                if next_node not in visited:
                    queue.append((next_node, path + [rel]))

        return paths

    def get_connected_components(self) -> list[list[str]]:
        """Find all connected components in the relationship graph."""
        all_nodes: set[str] = set()
        for source, rels in self._relationships.items():
            all_nodes.add(source)
            for rel in rels:
                all_nodes.add(rel.target.lower().strip())

        visited: set[str] = set()
        components: list[list[str]] = []

        for node in all_nodes:
            if node in visited:
                continue
            component: list[str] = []
            queue = [node]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.append(current)
                for rel in self._relationships.get(current, []):
                    neighbor = rel.target.lower().strip()
                    if neighbor not in visited:
                        queue.append(neighbor)
            components.append(component)

        return components

    def get_central_concepts(self, top_n: int = 10) -> list[tuple[str, int]]:
        """Find the most central concepts by degree (number of connections)."""
        degrees: dict[str, int] = {}
        for source, rels in self._relationships.items():
            degrees[source] = degrees.get(source, 0) + len(rels)
            for rel in rels:
                target = rel.target.lower().strip()
                degrees[target] = degrees.get(target, 0) + 1
        sorted_degrees = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
        return sorted_degrees[:top_n]

    def clear(self) -> None:
        self._relationships.clear()
        self._edges.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_relationships": len(self._edges),
            "unique_sources": len(self._relationships),
            "connected_components": len(self.get_connected_components()),
            "top_central": self.get_central_concepts(5),
        }

    def export_json(self, path: str | Path) -> None:
        """Export relationship map as JSON."""
        data = []
        for source, rels in self._relationships.items():
            for rel in rels:
                data.append({
                    "source": rel.source,
                    "target": rel.target,
                    "type": rel.type.value,
                    "strength": rel.strength,
                    "weight": rel.weight,
                    "context": rel.context,
                })
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("Exported %d relationships to %s", len(data), path)

    def export_graphviz(self, path: str | Path) -> None:
        """Export relationship map as Graphviz DOT format for visualization."""
        lines = ["digraph KnowledgeGraph {", '  rankdir="LR";', "  node [shape=box, style=rounded];"]
        seen_nodes: set[str] = set()

        for source, rels in self._relationships.items():
            for rel in rels:
                src_label = rel.source.replace('"', '\\"')
                tgt_label = rel.target.replace('"', '\\"')
                src_id = src_label.lower().replace(" ", "_").replace("-", "_")
                tgt_id = tgt_label.lower().replace(" ", "_").replace("-", "_")

                if src_id not in seen_nodes:
                    lines.append(f'  {src_id} [label="{src_label}"];')
                    seen_nodes.add(src_id)
                if tgt_id not in seen_nodes:
                    lines.append(f'  {tgt_id} [label="{tgt_label}"];')
                    seen_nodes.add(tgt_id)

                style = "solid" if rel.strength > 0.7 else "dashed"
                arrow = "none" if rel.bidirectional else "normal"
                lines.append(
                    f"  {src_id} -> {tgt_id} [style={style}, arrowhead={arrow}, "
                    f'label="{rel.type.value}", penwidth={max(0.5, rel.strength * 2):.1f}];'
                )

        lines.append("}")
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        log.info("Exported Graphviz graph to %s", path)
