"""Core knowledge extraction engine — extracts structured knowledge from diverse sources."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

log = logging.getLogger("hard_workers.knowledge.extractor")


class KnowledgeSource(Enum):
    DOCUMENT = "document"
    CODE = "code"
    CONVERSATION = "conversation"
    OBSIDIAN = "obsidian"
    AGENT = "agent"
    RESEARCH = "research"
    USER_INPUT = "user_input"


@dataclass
class ExtractedKnowledge:
    """A single knowledge unit extracted from any source."""

    id: str = ""
    title: str = ""
    content: str = ""
    summary: str = ""
    source_type: KnowledgeSource = KnowledgeSource.DOCUMENT
    source_path: str = ""
    tags: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    relationships: list[tuple[str, str, str]] = field(default_factory=list)
    importance: float = 0.5
    created: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            import hashlib

            raw = f"{self.title}{self.content}{self.source_path}{datetime.now().isoformat()}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.created:
            self.created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class KnowledgeExtractorEngine:
    """Extracts structured knowledge from various input sources."""

    def __init__(self) -> None:
        self._extracted: list[ExtractedKnowledge] = []

    # ── Public API ──────────────────────────────────────────────────────────────

    def extract_from_text(
        self,
        text: str,
        source: str = "unknown",
        source_type: KnowledgeSource = KnowledgeSource.DOCUMENT,
        tags: list[str] | None = None,
    ) -> ExtractedKnowledge:
        """Extract knowledge from raw text."""
        title = self._infer_title(text)
        summary = self._generate_summary(text)
        concepts = self._extract_concepts(text)
        entities = self._extract_entities(text)

        knowledge = ExtractedKnowledge(
            title=title,
            content=text,
            summary=summary,
            source_type=source_type,
            source_path=source,
            tags=list(set(tags or [])),
            concepts=concepts,
            entities=entities,
            importance=self._score_importance(text, concepts, source_type),
        )
        self._extracted.append(knowledge)
        log.info("Extracted knowledge: '%s' (%d chars, %d concepts)", title, len(text), len(concepts))
        return knowledge

    def extract_from_code(
        self,
        code: str,
        language: str = "unknown",
        source: str = "unknown",
        tags: list[str] | None = None,
    ) -> list[ExtractedKnowledge]:
        """Extract knowledge from source code."""
        results: list[ExtractedKnowledge] = []
        safe_tags = list(set((tags or []) + [f"code-{language}"]))

        # Extract from docstrings
        docstring_patterns = [
            re.compile(r'"""([^"]*?)"""', re.DOTALL),
            re.compile(r"'''([^']*?)'''", re.DOTALL),
            re.compile(r"///\s*(.*?)(?=\n\S|\Z)", re.DOTALL),
        ]
        for pattern in docstring_patterns:
            for match in pattern.finditer(code):
                doc_text = match.group(1).strip()
                if len(doc_text) > 30:
                    concepts = self._extract_concepts(doc_text)
                    knowledge = ExtractedKnowledge(
                        title=f"Docstring: {doc_text[:60]}...",
                        content=doc_text,
                        summary=doc_text[:200],
                        source_type=KnowledgeSource.CODE,
                        source_path=source,
                        tags=safe_tags + ["docstring"],
                        concepts=concepts,
                        importance=0.6,
                        metadata={"language": language},
                    )
                    results.append(knowledge)

        # Extract function/class signatures
        func_pattern = re.compile(
            r"(?:def|class|function|impl|fn)\s+(\w+)\s*\(([^)]*)\)",
            re.IGNORECASE,
        )
        for match in func_pattern.finditer(code):
            name = match.group(1)
            params = match.group(2)
            concepts = [name]
            knowledge = ExtractedKnowledge(
                title=f"{language}: {name}",
                content=f"Function/Class `{name}` with parameters: ({params})",
                summary=f"Definition of {name} in {source}",
                source_type=KnowledgeSource.CODE,
                source_path=source,
                tags=safe_tags + [f"func-{name.lower()}"],
                concepts=concepts,
                entities=[name],
                importance=0.7,
                metadata={"language": language, "signature": f"{name}({params})"},
            )
            results.append(knowledge)

        log.info("Extracted %d knowledge units from code (%s)", len(results), source)
        self._extracted.extend(results)
        return results

    def extract_from_conversation(
        self,
        messages: list[dict[str, str]],
        source: str = "conversation",
    ) -> ExtractedKnowledge:
        """Extract knowledge from a conversation transcript."""
        combined = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages if m.get("content"))
        title = f"Conversation: {self._infer_title(combined)}"
        concepts = self._extract_concepts(combined)
        entities = self._extract_entities(combined)
        key_points = self._extract_key_points(combined)

        knowledge = ExtractedKnowledge(
            title=title,
            content=combined,
            summary="\n".join(key_points[:5]),
            source_type=KnowledgeSource.CONVERSATION,
            source_path=source,
            tags=["conversation"] + concepts[:3],
            concepts=concepts,
            entities=entities,
            importance=0.5,
            metadata={
                "message_count": len(messages),
                "key_points": key_points,
            },
        )
        self._extracted.append(knowledge)
        log.info("Extracted knowledge from conversation (%d messages, %d concepts)", len(messages), len(concepts))
        return knowledge

    def get_all(self) -> list[ExtractedKnowledge]:
        return list(self._extracted)

    def clear(self) -> None:
        self._extracted.clear()

    # ── Internal analysis ───────────────────────────────────────────────────────

    def _infer_title(self, text: str) -> str:
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
            if line and len(line) < 120:
                return line[:100]
        return text[:80].strip() + ("..." if len(text) > 80 else "")

    def _generate_summary(self, text: str, max_sentences: int = 3) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        meaningful = [s for s in sentences if len(s) > 20]
        if not meaningful:
            return text[:150]
        return " ".join(meaningful[:max_sentences])

    def _extract_concepts(self, text: str) -> list[str]:
        concepts: list[str] = []
        patterns = [
            r"\*\*([^*]+)\*\*",  # **bold**
            r"__([^_]+)__",  # __bold__
            r"`([^`]+)`",  # `code`
            r"\[\[([^\]]+)\]\]",  # [[wikilink]]
            r"#([a-zA-Z][a-zA-Z0-9_/-]+)",  # #tag
        ]
        for pattern in patterns:
            concepts.extend(m.group(1).strip() for m in re.finditer(pattern, text) if m.group(1).strip())

        # Extract capitalized multi-word terms
        term_pattern = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
        concepts.extend(t for t in term_pattern if len(t) > 5)

        # Remove duplicates, keep order
        seen: set[str] = set()
        unique: list[str] = []
        for c in concepts:
            c_lower = c.lower().strip()
            if c_lower not in seen and len(c_lower) > 2:
                seen.add(c_lower)
                unique.append(c.strip())
        return unique[:20]

    def _extract_entities(self, text: str) -> list[str]:
        entities: list[str] = []

        # Extract wikilinks
        entities.extend(m.group(1).strip() for m in re.finditer(r"\[\[([^\]]+)\]\]", text) if m.group(1).strip())

        # Extract URLs
        entities.extend(m.group(0) for m in re.finditer(r'https?://[^\s<>"]+', text))

        # Extract file paths
        entities.extend(
            m.group(0) for m in re.finditer(r"[\w/\\]+\.\w{2,4}", text) if not m.group(0).startswith(("http", "www"))
        )

        return list(set(entities))

    def _extract_key_points(self, text: str) -> list[str]:
        points: list[str] = []
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ", "+ ")):
                points.append(line[2:].strip())
            elif re.match(r"^\d+[.)]\s", line):
                points.append(re.sub(r"^\d+[.)]\s*", "", line).strip())
            elif "**" in line and ":" in line:
                points.append(line.strip())
        return [p for p in points if len(p) > 15][:20]

    def _score_importance(
        self,
        text: str,
        concepts: list[str],
        source_type: KnowledgeSource,
    ) -> float:
        score = 0.3

        if source_type == KnowledgeSource.CODE:
            score += 0.3
        if source_type == KnowledgeSource.RESEARCH:
            score += 0.2

        if len(concepts) >= 5:
            score += 0.2
        if len(text) > 1000:
            score += 0.1
        if len(text) > 5000:
            score += 0.1

        importance_keywords = [
            "important",
            "critical",
            "key",
            "essential",
            "fundamental",
            "significant",
            "major",
            "core",
            "primary",
            "main",
        ]
        for kw in importance_keywords:
            if kw in text.lower():
                score += 0.05

        return min(score, 1.0)
