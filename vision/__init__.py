"""Image understanding system.

Provides a complete pipeline from image upload to structured description:
Image → Vision Model → Structured Description → Main Agent → Response

Supports: OCR, screenshots, UI analysis, diagram analysis, document analysis.
"""

from .image_processor import ImageProcessor, ProcessedImage
from .pipeline import VisionPipeline, VisionResult
from .vision_model import VisionModel

__all__ = [
    "ImageProcessor",
    "ProcessedImage",
    "VisionModel",
    "VisionPipeline",
    "VisionResult",
]
