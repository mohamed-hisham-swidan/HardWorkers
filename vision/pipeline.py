"""Vision pipeline — orchestrates image processing through the full understanding workflow.

Architecture:
Image → Vision Model → Structured Description → Main Agent → Response
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .image_processor import ImageProcessor
from .vision_model import VisionModel

log = logging.getLogger("hard_workers.vision.pipeline")


@dataclass
class VisionResult:
    """Complete result from the vision pipeline."""

    success: bool
    description: str = ""
    structured: dict[str, Any] = field(default_factory=dict)
    ocr_text: str = ""
    image_info: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class VisionPipeline:
    """End-to-end vision understanding pipeline."""

    def __init__(
        self,
        vision_model: VisionModel | None = None,
        image_processor: ImageProcessor | None = None,
    ) -> None:
        self._image_processor = image_processor or ImageProcessor()
        self._vision_model = vision_model or VisionModel()

    # ── Public API ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        image_path: str | Path | bytes,
        detail_level: str = "detailed",
        on_chunk: Callable[[str], None] | None = None,
    ) -> VisionResult:
        """Run the full vision pipeline on an image.

        Flow: Image → Process → OCR → Vision Model → Structured Description
        """
        try:
            # Step 1: Load and process image
            processed = self._image_processor.load(image_path)

            # Step 2: OCR
            ocr_text = self._image_processor.run_ocr(processed)

            # Step 3: Generate description via vision model
            if detail_level == "detailed":
                structured = self._vision_model.describe_detailed(processed.base64_data)
                description = structured.get("description", "")
            else:
                description = self._vision_model.describe(
                    processed.base64_data,
                    prompt="Describe this image concisely.",
                    on_chunk=on_chunk,
                )
                structured = {
                    "description": description,
                    "type": "general",
                    "has_text": bool(ocr_text),
                    "key_elements": [],
                }

            return VisionResult(
                success=True,
                description=description,
                structured=structured,
                ocr_text=ocr_text,
                image_info={
                    "path": processed.path,
                    "format": processed.format,
                    "width": processed.width,
                    "height": processed.height,
                    "size_bytes": processed.size_bytes,
                },
            )

        except FileNotFoundError:
            return VisionResult(success=False, error="Image file not found")
        except ValueError:
            return VisionResult(success=False, error="Invalid image data")
        except Exception:
            log.exception("Vision pipeline error")
            return VisionResult(success=False, error="Vision processing failed")

    def analyze_screenshot(
        self,
        image_path: str | Path | bytes,
    ) -> VisionResult:
        """Specialized analysis for screenshots/UI images."""
        result = self.analyze(image_path, detail_level="detailed")

        if result.success:
            prompt = (
                "This is a screenshot. Describe the user interface shown, including:\n"
                "- Application or website shown\n"
                "- Key UI elements (buttons, menus, fields)\n"
                "- Any text content visible\n"
                "- Layout and navigation structure"
            )
            b64 = self._get_base64_from_result(result)
            if b64:
                ui_desc = self._vision_model.describe(b64, prompt)
                result.description = ui_desc
                result.structured["ui_analysis"] = ui_desc

        return result

    def analyze_document(
        self,
        image_path: str | Path | bytes,
    ) -> VisionResult:
        """Specialized analysis for document images (PDF scans, etc.)."""
        result = self.analyze(image_path, detail_level="detailed")

        if result.success:
            prompt = (
                "This is a document image. Extract and describe:\n"
                "- Document type and format\n"
                "- All visible text content\n"
                "- Document structure (headings, paragraphs, lists)\n"
                "- Any tables, figures, or diagrams"
            )
            b64 = self._get_base64_from_result(result)
            if b64:
                doc_desc = self._vision_model.describe(b64, prompt)
                result.description = doc_desc
                result.structured["document_analysis"] = doc_desc

        return result

    def analyze_diagram(
        self,
        image_path: str | Path | bytes,
    ) -> VisionResult:
        """Specialized analysis for diagrams and flowcharts."""
        result = self.analyze(image_path, detail_level="detailed")

        if result.success:
            prompt = (
                "This is a diagram or chart. Analyze and describe:\n"
                "- Type of diagram (flowchart, mind map, UML, etc.)\n"
                "- Main components and their relationships\n"
                "- Flow of information or process steps\n"
                "- Any labels, annotations, or legends"
            )
            b64 = self._get_base64_from_result(result)
            if b64:
                diag_desc = self._vision_model.describe(b64, prompt)
                result.description = diag_desc
                result.structured["diagram_analysis"] = diag_desc

        return result

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _get_base64_from_result(self, result: VisionResult) -> str | None:
        """Retry loading base64 for re-analysis."""
        path = result.image_info.get("path", "")
        if path and path != "bytes":
            try:
                processed = self._image_processor.load(path)
                return processed.base64_data
            except Exception as exc:
                log.warning("Failed to load image for re-analysis: %s", exc)
            return None


if __name__ == "__main__":
    print("Run as:  python -m vision.pipeline  (not python vision/pipeline.py)")
    sys.exit(1)
