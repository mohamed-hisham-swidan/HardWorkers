"""GGUF model handler.

Manages conversion, loading, and interaction with GGUF-format models
for use with llama.cpp and compatible runtimes (Ollama, LM Studio).
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.training.gguf_handler")


class GGUFHandler:
    """Handles GGUF model operations: conversion, management, and inference."""

    def __init__(
        self,
        models_dir: Path | str = "./models/gguf",
        llama_cpp_path: str | None = None,
    ) -> None:
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._llama_cpp_path = llama_cpp_path
        self._lock = threading.Lock()
        self._loaded_model = None

    # ── Public API ──────────────────────────────────────────────────────────────

    def list_models(self) -> list[dict[str, Any]]:
        """List all GGUF models in the models directory."""
        models: list[dict[str, Any]] = []
        for f in self._models_dir.glob("*.gguf"):
            models.append({
                "path": str(f),
                "name": f.stem,
                "size_bytes": f.stat().st_size,
                "size_human": self._format_size(f.stat().st_size),
            })
        return sorted(models, key=lambda m: m["name"])

    def get_model_path(self, name: str) -> Path | None:
        """Get the full path to a GGUF model by name."""
        for f in self._models_dir.glob(f"{name}.gguf"):
            return f
        path = self._models_dir / f"{name}.gguf"
        return path if path.exists() else None

    def convert_to_gguf(
        self,
        model_path: Path | str,
        output_name: str | None = None,
        quantize: str | None = "q4_k_m",
    ) -> Path | None:
        """Convert a HuggingFace model to GGUF format.

        Uses llama.cpp's convert.py if available, otherwise returns None.
        """
        model_path = Path(model_path)
        if not model_path.exists():
            log.error("Model path not found: %s", model_path)
            return None

        output_name = output_name or model_path.stem
        output_path = self._models_dir / f"{output_name}.gguf"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            convert_script = self._find_convert_script()
            if not convert_script:
                log.warning("llama.cpp convert.py not found — cannot convert to GGUF automatically")
                return None

            cmd = [
                "python",
                str(convert_script),
                str(model_path),
                "--outfile",
                str(output_path),
                "--outtype",
                quantize or "f16",
            ]
            log.info("Converting model to GGUF: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                log.error("GGUF conversion failed: %s", result.stderr)
                return None

            log.info("GGUF model created: %s", output_path)
            return output_path

        except FileNotFoundError as exc:
            log.error("Conversion tool not found: %s", exc)
            return None
        except subprocess.TimeoutExpired:
            log.error("GGUF conversion timed out")
            return None
        except Exception as exc:
            log.error("GGUF conversion error: %s", exc)
            return None

    def quantize(
        self,
        input_path: Path | str,
        output_name: str | None = None,
        method: str = "q4_k_m",
    ) -> Path | None:
        """Quantize an existing GGUF model to a smaller size."""
        input_path = Path(input_path)
        if not input_path.exists():
            log.error("Input GGUF not found: %s", input_path)
            return None

        output_name = output_name or f"{input_path.stem}-{method}"
        output_path = self._models_dir / f"{output_name}.gguf"

        try:
            quantize_bin = self._find_quantize_binary()
            if not quantize_bin:
                log.warning("llama.cpp quantize binary not found")
                return None

            cmd = [str(quantize_bin), str(input_path), str(output_path), method.upper()]
            log.info("Quantizing GGUF: %s", " ".join(cmd))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if result.returncode != 0:
                log.error("Quantization failed: %s", result.stderr)
                return None

            log.info("Quantized model: %s (%s)", output_path, method)
            return output_path

        except Exception as exc:
            log.error("Quantization error: %s", exc)
            return None

    # ── Inference ───────────────────────────────────────────────────────────────

    def load_model(
        self,
        model_path: Path | str,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
    ) -> Any:
        """Load a GGUF model using llama-cpp-python."""
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("llama-cpp-python required: pip install llama-cpp-python")

        model_path = Path(model_path)
        with self._lock:
            self._loaded_model = Llama(
                model_path=str(model_path),
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            log.info("GGUF model loaded: %s (ctx=%d, gpu=%d)", model_path, n_ctx, n_gpu_layers)
            return self._loaded_model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str | None:
        """Generate text using the loaded GGUF model."""
        if self._loaded_model is None:
            log.error("No model loaded — call load_model() first")
            return None

        try:
            output = self._loaded_model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=on_chunk is not None,
            )

            if on_chunk:
                full_text = ""
                for chunk in output:
                    text = chunk["choices"][0].get("text", "")
                    full_text += text
                    on_chunk(text)
                return full_text

            return output["choices"][0].get("text", "").strip()

        except Exception as exc:
            log.error("GGUF generation error: %s", exc)
            return None

    def unload(self) -> None:
        """Unload the current model to free memory."""
        with self._lock:
            self._loaded_model = None
            log.info("GGUF model unloaded")

    # ── Helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _find_convert_script(self) -> Path | None:
        """Locate llama.cpp's convert.py via env var or known paths."""
        env_path = os.environ.get("LLAMA_CPP_CONVERT")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p
        candidates: list[Path | None] = [
            Path(self._llama_cpp_path) / "convert.py" if self._llama_cpp_path else None,
        ]
        for c in candidates:
            if c and c.exists():
                return c
        return None

    def _find_quantize_binary(self) -> Path | None:
        """Locate llama.cpp's quantize binary."""
        candidates = [
            Path(self._llama_cpp_path) / "quantize" if self._llama_cpp_path else None,
            Path("./vendor/llama.cpp/quantize"),
            Path("./llama.cpp/quantize"),
        ]
        for c in candidates:
            if c and c.exists():
                return c
        return None
