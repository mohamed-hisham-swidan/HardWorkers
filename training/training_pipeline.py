"""Training pipeline orchestrator.

Coordinates the end-to-end training workflow:
1. Document import → 2. Knowledge extraction → 3. Dataset preparation
→ 4. LoRA/QLoRA configuration → 5. Fine-tuning → 6. GGUF conversion
→ 7. Ollama/LM Studio import
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from training.dataset import DatasetIngestor, TrainingExample
from training.document_import import DocumentImporter, ImportedDocument
from training.fine_tune_prep import FineTunePreparer
from training.gguf_handler import GGUFHandler
from training.knowledge_extractor import KnowledgeExtractor
from training.lm_studio_adapter import LMStudioAdapter
from training.lora_config import LoRAConfiguration
from training.ollama_adapter import OllamaAdapter

log = logging.getLogger("hard_workers.training.pipeline")


ProgressCallback = Callable[[str, float], None]


class TrainingPipeline:
    """End-to-end training pipeline orchestrator."""

    def __init__(
        self,
        data_dir: str | Path = "./data/training",
        models_dir: str | Path = "./models",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.models_dir = Path(models_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.ingestor = DatasetIngestor(self.data_dir / "datasets")
        self.importer = DocumentImporter()
        self.extractor = KnowledgeExtractor()
        self.preparer = FineTunePreparer()
        self.gguf = GGUFHandler(self.models_dir / "gguf")
        self.ollama = OllamaAdapter()
        self.lm_studio = LMStudioAdapter()

        self._on_progress: ProgressCallback | None = None

    # ── Progress reporting ─────────────────────────────────────────────────────

    def on_progress(self, callback: ProgressCallback) -> None:
        self._on_progress = callback

    def _report(self, stage: str, pct: float) -> None:
        if self._on_progress:
            self._on_progress(stage, pct)
        log.info("Pipeline [%s]: %.1f%%", stage, pct * 100)

    # ── Pipeline steps ─────────────────────────────────────────────────────────

    def import_documents(
        self,
        sources: list[str | Path],
        source_type: str = "auto",
    ) -> list[ImportedDocument]:
        """Step 1: Import documents from various sources."""
        self._report("import", 0.0)
        all_docs: list[ImportedDocument] = []

        for source in sources:
            source_path = Path(source)
            if source_type == "obsidian" or (source_type == "auto" and source_path.is_dir()):
                docs = self.importer.import_obsidian_vault(source_path)
            elif source_path.is_dir():
                docs = self.importer.import_directory(source_path)
            else:
                doc = self.importer.import_file(source_path)
                docs = [doc]
            all_docs.extend(docs)
            self._report("import", len(all_docs) / max(len(sources), 1))

        log.info("Pipeline: imported %d documents", len(all_docs))
        return all_docs

    def extract_knowledge(
        self,
        docs: list[ImportedDocument],
    ) -> list[TrainingExample]:
        """Step 2: Extract knowledge into training examples."""
        self._report("extract", 0.0)
        examples = self.extractor.extract_from_documents(docs)
        self.ingestor.add_examples(examples)
        self._report("extract", 1.0)
        log.info("Pipeline: extracted %d training examples", len(examples))
        return examples

    def prepare_dataset(
        self,
        template: str = "alpaca",
        output_path: str | Path | None = None,
    ) -> Path:
        """Step 3: Prepare and format the dataset for training."""
        self._report("prepare", 0.5)
        path = self.preparer.prepare_dataset(self.ingestor, template, output_path)
        self._report("prepare", 1.0)
        return path

    def save_dataset(self, path: str | Path | None = None) -> Path:
        """Save the raw dataset to disk."""
        return self.ingestor.save(path)

    def configure_training(
        self,
        config: LoRAConfiguration | None = None,
    ) -> LoRAConfiguration:
        """Step 4: Configure LoRA/QLoRA training parameters."""
        if config is None:
            config = LoRAConfiguration.qlora_defaults()
        self.preparer = FineTunePreparer(config)
        self._report("configure", 1.0)
        return config

    def get_stats(self) -> dict[str, Any]:
        return {
            "dataset": self.ingestor.stats(),
            "gguf_models": self.gguf.list_models(),
            "ollama_available": self.ollama.health_check(),
            "lm_studio_available": self.lm_studio.health_check(),
        }

    def close(self) -> None:
        self.ollama.close()
        self.lm_studio.close()
