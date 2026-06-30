"""Knowledge extraction pipeline.

Transforms imported documents into structured training examples
suitable for fine-tuning a local model.
"""

from __future__ import annotations

import logging
import re

from training.dataset import TrainingExample
from training.document_import import ImportedDocument

log = logging.getLogger("hard_workers.training.knowledge_extractor")


class KnowledgeExtractor:
    """Extracts knowledge from imported documents and converts to training examples."""

    def __init__(self, max_chunk_size: int = 2048) -> None:
        self._max_chunk_size = max_chunk_size

    # ── Public API ──────────────────────────────────────────────────────────────

    def extract_from_document(
        self,
        doc: ImportedDocument,
    ) -> list[TrainingExample]:
        """Convert an imported document into training examples."""
        examples: list[TrainingExample] = []

        if doc.source_type == "code":
            examples.extend(self._extract_code_knowledge(doc))
        elif doc.source_type == "markdown":
            examples.extend(self._extract_markdown_knowledge(doc))
        elif doc.source_type == "obsidian":
            examples.extend(self._extract_obsidian_knowledge(doc))
        elif doc.source_type == "pdf":
            examples.extend(self._extract_text_knowledge(doc, "document"))
        elif doc.source_type == "json":
            examples.extend(self._extract_json_knowledge(doc))
        else:
            examples.extend(self._extract_text_knowledge(doc, "text"))

        log.info(
            "Extracted %d training examples from '%s' (type=%s)",
            len(examples),
            doc.title,
            doc.source_type,
        )
        return examples

    def extract_from_documents(
        self,
        docs: list[ImportedDocument],
    ) -> list[TrainingExample]:
        all_examples: list[TrainingExample] = []
        for doc in docs:
            all_examples.extend(self.extract_from_document(doc))
        return all_examples

    # ── Knowledge extraction strategies ─────────────────────────────────────────

    def _extract_code_knowledge(self, doc: ImportedDocument) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        language = doc.metadata.get("language", "unknown")
        code = doc.content

        # Q&A pairs from code comments and docstrings
        docstring_pattern = re.compile(r'"""([^"]*?)"""', re.DOTALL)
        for match in docstring_pattern.finditer(code):
            doc_text = match.group(1).strip()
            if doc_text and len(doc_text) > 20:
                examples.append(
                    TrainingExample(
                        instruction=f"Explain this {language} code",
                        input=doc_text[:200],
                        output=doc_text,
                        source=doc.title,
                        category="coding",
                        metadata={"language": language},
                    )
                )

        # Function/class understanding
        func_pattern = re.compile(
            r"(?:def|class|function|impl|fn)\s+(\w+)[\s\S]*?(?=\n\S|\Z)",
            re.IGNORECASE,
        )
        for match in func_pattern.finditer(code):
            snippet = match.group(0).strip()
            if len(snippet) > 50:
                examples.append(
                    TrainingExample(
                        instruction=f"Analyze this {language} code snippet",
                        input=snippet[: self._max_chunk_size],
                        output=snippet[: self._max_chunk_size],
                        source=doc.title,
                        category="coding",
                        metadata={"language": language},
                    )
                )

        return examples

    def _extract_markdown_knowledge(self, doc: ImportedDocument) -> list[TrainingExample]:
        examples: list[TrainingExample] = []

        for section in doc.sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            if not content:
                continue

            chunks = self._chunk_text(content)
            for i, chunk in enumerate(chunks):
                examples.append(
                    TrainingExample(
                        instruction=f"Summarize: {heading}",
                        input=chunk,
                        output=chunk,
                        source=f"{doc.title}#{heading}",
                        category="knowledge",
                        metadata={"section": heading, "chunk": i},
                    )
                )

        return examples

    def _extract_obsidian_knowledge(self, doc: ImportedDocument) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        wikilinks = doc.metadata.get("wikilinks", [])
        tags = doc.metadata.get("tags", [])

        content = doc.content
        for wikilink in wikilinks:
            examples.append(
                TrainingExample(
                    instruction=f"What is the relationship between {doc.title} and [[{wikilink}]]?",
                    input=f"Document: {doc.title}\nLinked to: [[{wikilink}]]",
                    output=f"[[{doc.title}]] is related to [[{wikilink}]].",
                    source=doc.title,
                    category="obsidian",
                    metadata={"wikilink": wikilink, "tags": tags},
                )
            )

        if tags:
            examples.append(
                TrainingExample(
                    instruction=f"Extract knowledge from {doc.title}",
                    input=f"Tags: {', '.join(tags)}\n\n{content[: self._max_chunk_size]}",
                    output=content[: self._max_chunk_size],
                    source=doc.title,
                    category="obsidian",
                    metadata={"tags": tags},
                )
            )

        return examples

    def _extract_text_knowledge(
        self,
        doc: ImportedDocument,
        category: str = "text",
    ) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        chunks = self._chunk_text(doc.content)

        for i, chunk in enumerate(chunks):
            examples.append(
                TrainingExample(
                    instruction=f"Extract information from {doc.title}",
                    input=chunk,
                    output=chunk,
                    source=doc.title,
                    category=category,
                    metadata={"chunk": i, "total_chunks": len(chunks)},
                )
            )

        return examples

    def _extract_json_knowledge(self, doc: ImportedDocument) -> list[TrainingExample]:
        examples: list[TrainingExample] = []
        try:
            import json

            data = json.loads(doc.content)
        except json.JSONDecodeError:
            return self._extract_text_knowledge(doc, "json")

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    instruction = item.get("instruction", "") or item.get("question", "")
                    inp = item.get("input", "") or item.get("context", "")
                    output = item.get("output", "") or item.get("response", "") or item.get("answer", "")
                    if instruction and output:
                        examples.append(
                            TrainingExample(
                                instruction=instruction,
                                input=inp,
                                output=output,
                                source=doc.title,
                                category="training",
                            )
                        )

        return examples

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _chunk_text(self, text: str) -> list[str]:
        words = text.split()
        chunks: list[str] = []
        current_chunk: list[str] = []

        for word in words:
            current_chunk.append(word)
            if len(" ".join(current_chunk)) >= self._max_chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks or [text]
