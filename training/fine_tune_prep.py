"""Fine-tuning preparation pipeline.

Prepares datasets for fine-tuning by:
- Formatting examples into instruction-following templates
- Tokenizing and chunking for model input
- Creating train/test splits
- Converting to HuggingFace Dataset format
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

from training.dataset import DatasetIngestor, TrainingExample
from training.lora_config import LoRAConfiguration

log = logging.getLogger("hard_workers.training.fine_tune_prep")


class FineTunePreparer:
    """Prepares datasets for fine-tuning workflows."""

    def __init__(self, config: LoRAConfiguration | None = None) -> None:
        self._config = config or LoRAConfiguration.defaults()

    # ── Public API ──────────────────────────────────────────────────────────────

    def prepare_dataset(
        self,
        ingestor: DatasetIngestor,
        template: str = "alpaca",
        output_path: Path | str | None = None,
    ) -> Path:
        """Prepare and save a dataset in the format needed for training."""
        examples = ingestor.get_all()
        formatted = self._format_examples(examples, template)
        if output_path is None:
            output_path = Path(self._config.output_dir) / "prepared_dataset.json"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(formatted, f, indent=2, ensure_ascii=False)

        log.info(
            "Dataset prepared — %d examples → %s (template=%s)",
            len(formatted),
            output_path,
            template,
        )
        return output_path

    def create_train_test_split(
        self,
        examples: list[TrainingExample],
        test_ratio: float | None = None,
        shuffle_seed: int | None = None,
    ) -> tuple[list[TrainingExample], list[TrainingExample]]:
        ratio = test_ratio if test_ratio is not None else self._config.test_split_ratio
        seed = shuffle_seed if shuffle_seed is not None else self._config.shuffle_seed
        rng = random.Random(seed)
        shuffled = list(examples)
        rng.shuffle(shuffled)
        split_idx = max(1, int(len(shuffled) * (1 - ratio)))
        train = shuffled[:split_idx]
        test = shuffled[split_idx:]
        log.info("Train/test split: %d train, %d test", len(train), len(test))
        return train, test

    def to_huggingface_dataset(
        self,
        examples: list[TrainingExample],
        template: str = "alpaca",
    ) -> Any:
        """Convert training examples to a HuggingFace Dataset."""
        try:
            from datasets import Dataset
        except ImportError:
            raise ImportError("datasets package required: pip install datasets")
        formatted = self._format_examples(examples, template)
        dataset = Dataset.from_list(formatted)
        log.info("HuggingFace Dataset created — %d rows", len(dataset))
        return dataset

    # ── Formatting ──────────────────────────────────────────────────────────────

    def _format_examples(
        self,
        examples: list[TrainingExample],
        template: str,
    ) -> list[dict[str, str]]:
        formatters = {
            "alpaca": self._format_alpaca,
            "sharegpt": self._format_sharegpt,
            "chatml": self._format_chatml,
            "openai": self._format_openai,
            "plain": self._format_plain,
        }
        formatter = formatters.get(template, self._format_alpaca)
        return [formatter(ex) for ex in examples]

    def _format_alpaca(self, ex: TrainingExample) -> dict[str, str]:
        if ex.input:
            text = (
                f"Below is an instruction that describes a task, "
                f"paired with an input that provides further context.\n\n"
                f"### Instruction:\n{ex.instruction}\n\n"
                f"### Input:\n{ex.input}\n\n"
                f"### Response:\n{ex.output}"
            )
        else:
            text = (
                f"Below is an instruction that describes a task.\n\n"
                f"### Instruction:\n{ex.instruction}\n\n"
                f"### Response:\n{ex.output}"
            )
        return {
            "instruction": ex.instruction,
            "input": ex.input,
            "output": ex.output,
            "text": text,
        }

    def _format_sharegpt(self, ex: TrainingExample) -> dict[str, Any]:
        return {
            "conversations": [
                {
                    "from": "human",
                    "value": f"{ex.instruction}\n{ex.input}".strip(),
                },
                {"from": "gpt", "value": ex.output},
            ],
            "source": ex.source,
        }

    def _format_chatml(self, ex: TrainingExample) -> dict[str, Any]:
        messages = []
        if ex.instruction:
            messages.append({"role": "user", "content": ex.instruction})
        if ex.input:
            messages.append({"role": "user", "content": ex.input})
        messages.append({"role": "assistant", "content": ex.output})
        return {"messages": messages}

    def _format_openai(self, ex: TrainingExample) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
        ]
        user_content = ex.instruction
        if ex.input:
            user_content += f"\n\n{ex.input}"
        messages.append({"role": "user", "content": user_content})
        messages.append({"role": "assistant", "content": ex.output})
        return {"messages": messages}

    def _format_plain(self, ex: TrainingExample) -> dict[str, str]:
        return {
            "prompt": f"{ex.instruction}\n{ex.input}".strip(),
            "completion": ex.output,
        }
