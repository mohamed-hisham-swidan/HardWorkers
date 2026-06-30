"""Dataset ingestion pipeline.

Responsible for collecting, normalizing, and storing training examples
from various source types for fine-tuning preparation.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.training.dataset")


@dataclass
class TrainingExample:
    """A single training example for fine-tuning."""

    instruction: str
    input: str = ""
    output: str = ""
    source: str = ""
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "source": self.source,
            "category": self.category,
        }
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrainingExample:
        return cls(
            instruction=d.get("instruction", ""),
            input=d.get("input", ""),
            output=d.get("output", ""),
            source=d.get("source", ""),
            category=d.get("category", "general"),
            metadata=d.get("metadata", {}),
        )


class DatasetIngestor:
    """Ingests training examples from various sources."""

    def __init__(self, storage_dir: Path | str = "./data/training") -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._examples: list[TrainingExample] = []

    # ── Public API ──────────────────────────────────────────────────────────────

    def add_example(self, example: TrainingExample) -> None:
        with self._lock:
            self._examples.append(example)

    def add_examples(self, examples: list[TrainingExample]) -> None:
        with self._lock:
            self._examples.extend(examples)

    def get_all(self) -> list[TrainingExample]:
        with self._lock:
            return list(self._examples)

    def count(self) -> int:
        with self._lock:
            return len(self._examples)

    def clear(self) -> None:
        with self._lock:
            self._examples.clear()

    def save(
        self,
        path: Path | str | None = None,
        format: str = "jsonl",
    ) -> Path:
        path = Path(path) if path else self._storage_dir / "dataset.jsonl"
        with self._lock:
            if format == "jsonl":
                with open(path, "w", encoding="utf-8") as f:
                    for ex in self._examples:
                        f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
            elif format == "json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([ex.to_dict() for ex in self._examples], f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Unsupported format: {format}")
        log.info("Dataset saved — %d examples to %s", len(self._examples), path)
        return Path(path)

    def load(self, path: Path | str) -> int:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        examples: list[TrainingExample] = []
        if path.suffix == ".jsonl":
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        examples.append(TrainingExample.from_dict(json.loads(line)))
        elif path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                examples = [TrainingExample.from_dict(d) for d in data]
        else:
            raise ValueError(f"Unsupported file extension: {path.suffix}")
        with self._lock:
            self._examples = examples
        log.info("Dataset loaded — %d examples from %s", len(examples), path)
        return len(examples)

    def iter_batches(self, batch_size: int = 32) -> Generator[list[TrainingExample], None, None]:
        with self._lock:
            total = len(self._examples)
        for i in range(0, total, batch_size):
            with self._lock:
                yield self._examples[i : i + batch_size]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            sources: dict[str, int] = {}
            categories: dict[str, int] = {}
            for ex in self._examples:
                sources[ex.source] = sources.get(ex.source, 0) + 1
                categories[ex.category] = categories.get(ex.category, 0) + 1
            return {
                "total": len(self._examples),
                "sources": sources,
                "categories": categories,
                "storage_dir": str(self._storage_dir),
            }
