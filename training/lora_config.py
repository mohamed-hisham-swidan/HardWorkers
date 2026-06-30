"""LoRA and QLoRA configuration management.

Provides configuration classes and factory methods for creating
LoRA/QLoRA configurations suitable for fine-tuning local models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class QuantizationMethod(Enum):
    NONE = "none"
    NF4 = "nf4"
    FP4 = "fp4"
    INT8 = "int8"


class LoRATarget(Enum):
    ALL_LINEAR = "all_linear"
    ATTENTION = "attention"
    MLP = "mlp"
    CUSTOM = "custom"


@dataclass
class LoRAConfiguration:
    """Configuration for LoRA / QLoRA fine-tuning.

    Follows the PEFT library conventions and can be converted
    to a ``LoraConfig`` dict for use with ``peft``.
    """

    # ── LoRA hyperparameters ───────────────────────────────────────────────────
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] | None = None
    target: LoRATarget = LoRATarget.ALL_LINEAR
    bias: str = "none"
    task_type: str = "CAUSAL_LM"

    # ── QLoRA quantization ────────────────────────────────────────────────────
    quantization: QuantizationMethod = QuantizationMethod.NF4
    double_quant: bool = True
    quant_type: str = "nf4"

    # ── Training hyperparameters ───────────────────────────────────────────────
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    num_epochs: int = 3
    max_steps: int = -1
    warmup_steps: int = 100
    logging_steps: int = 25
    save_steps: int = 500
    eval_steps: int = 500
    save_total_limit: int = 3
    gradient_checkpointing: bool = True
    optim: str = "paged_adamw_8bit"
    max_grad_norm: float = 0.3

    # ── Model configuration ────────────────────────────────────────────────────
    base_model_name: str = "dolphin-2.2.1-mistral-7b"
    model_max_length: int = 2048
    trust_remote_code: bool = False
    use_flash_attention: bool = False

    # ── Output ─────────────────────────────────────────────────────────────────
    output_dir: str = "./models/fine-tuned"
    adapter_name: str = "lora_adapter"

    # ── Dataset configuration ──────────────────────────────────────────────────
    test_split_ratio: float = 0.1
    shuffle_seed: int = 42
    preprocessing_num_workers: int = 4

    # ── Methods ────────────────────────────────────────────────────────────────

    @property
    def use_quantization(self) -> bool:
        return self.quantization != QuantizationMethod.NONE

    @property
    def is_qlora(self) -> bool:
        return self.use_quantization

    def to_peft_config(self) -> dict[str, Any]:
        """Convert to a dict suitable for ``peft.LoraConfig``."""
        return {
            "r": self.r,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "bias": self.bias,
            "task_type": self.task_type,
            "target_modules": self._resolve_target_modules(),
        }

    def to_training_args(self) -> dict[str, Any]:
        """Convert to a dict suitable for ``transformers.TrainingArguments``."""
        return {
            "output_dir": self.output_dir,
            "per_device_train_batch_size": self.batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "learning_rate": self.learning_rate,
            "num_train_epochs": self.num_epochs,
            "max_steps": self.max_steps if self.max_steps > 0 else None,
            "warmup_steps": self.warmup_steps,
            "logging_steps": self.logging_steps,
            "save_steps": self.save_steps,
            "eval_steps": self.eval_steps,
            "save_total_limit": self.save_total_limit,
            "gradient_checkpointing": self.gradient_checkpointing,
            "optim": self.optim,
            "max_grad_norm": self.max_grad_norm,
            "load_best_model_at_end": True,
            "report_to": "none",
        }

    def to_bitsandbytes_config(self) -> dict[str, Any]:
        """Convert to a dict suitable for ``transformers.BitsAndBytesConfig``."""
        if not self.use_quantization:
            return {}
        from transformers import BitsAndBytesConfig

        config = BitsAndBytesConfig(
            load_in_4bit=self.quantization in (QuantizationMethod.NF4, QuantizationMethod.FP4),
            load_in_8bit=self.quantization == QuantizationMethod.INT8,
            bnb_4bit_use_double_quant=self.double_quant,
            bnb_4bit_quant_type=self.quant_type,
            bnb_4bit_compute_dtype="float16",
        )
        return config.to_dict()

    def _resolve_target_modules(self) -> list[str] | None:
        if self.target_modules:
            return self.target_modules
        mapping = {
            LoRATarget.ALL_LINEAR: None,
            LoRATarget.ATTENTION: ["q_proj", "k_proj", "v_proj", "o_proj"],
            LoRATarget.MLP: ["gate_proj", "up_proj", "down_proj"],
            LoRATarget.CUSTOM: None,
        }
        return mapping.get(self.target)

    @classmethod
    def defaults(cls) -> LoRAConfiguration:
        return cls()

    @classmethod
    def qlora_defaults(cls) -> LoRAConfiguration:
        return cls(
            quantization=QuantizationMethod.NF4,
            batch_size=2,
            gradient_accumulation_steps=8,
        )

    @classmethod
    def lora_defaults(cls) -> LoRAConfiguration:
        return cls(quantization=QuantizationMethod.NONE)
