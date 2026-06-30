"""Local model training pipeline — dataset ingestion, fine-tuning, quantization support.

Provides a complete pipeline for creating specialized local models:
- Dataset ingestion from documents, code, notes, PDFs, Obsidian vaults
- Knowledge extraction and preparation
- LoRA/QLoRA fine-tuning preparation
- GGUF quantization support
- Ollama and LM Studio compatibility
"""

from training.dataset import DatasetIngestor, TrainingExample
from training.document_import import DocumentImporter, ImportedDocument
from training.fine_tune_prep import FineTunePreparer
from training.gguf_handler import GGUFHandler
from training.knowledge_extractor import KnowledgeExtractor
from training.lm_studio_adapter import LMStudioAdapter
from training.lora_config import LoRAConfiguration
from training.ollama_adapter import OllamaAdapter
from training.training_pipeline import TrainingPipeline

__all__ = [
    "DatasetIngestor",
    "TrainingExample",
    "DocumentImporter",
    "ImportedDocument",
    "KnowledgeExtractor",
    "FineTunePreparer",
    "LoRAConfiguration",
    "GGUFHandler",
    "OllamaAdapter",
    "LMStudioAdapter",
    "TrainingPipeline",
]
