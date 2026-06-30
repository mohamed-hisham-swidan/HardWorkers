"""Image processing and preprocessing for the vision pipeline."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("hard_workers.vision.image_processor")


class ImageFormat(Enum):
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    WEBP = "webp"
    BMP = "bmp"
    GIF = "gif"


SUPPORTED_FORMATS = {ImageFormat.PNG, ImageFormat.JPG, ImageFormat.JPEG, ImageFormat.WEBP}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB


@dataclass
class ProcessedImage:
    """Result of image processing."""

    path: str
    format: str
    width: int
    height: int
    size_bytes: int
    mode: str
    base64_data: str = ""
    thumbnail_base64: str = ""
    ocr_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(self.height, 1)

    @property
    def megapixels(self) -> float:
        return (self.width * self.height) / 1_000_000


class ImageProcessor:
    """Loads, validates, and preprocesses images for the vision pipeline."""

    # ── Public API ──────────────────────────────────────────────────────────────

    def load(self, path: str | Path | bytes) -> ProcessedImage:
        """Load an image from a file path, URL path, or raw bytes."""
        import base64

        from PIL import Image

        if isinstance(path, bytes):
            image_data = path
            source_name = "bytes"
        else:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(f"Image not found: {path}")
            if path.stat().st_size > MAX_IMAGE_SIZE:
                raise ValueError(f"Image too large: {path.stat().st_size} bytes (max {MAX_IMAGE_SIZE})")
            source_name = path.name
            image_data = path.read_bytes()

        img = Image.open(io.BytesIO(image_data))
        img_format = img.format.lower() if img.format else "png"
        b64 = base64.b64encode(image_data).decode("utf-8")

        # Generate thumbnail for preview (max 256px)
        thumb = img.copy()
        thumb.thumbnail((256, 256))
        thumb_buf = io.BytesIO()
        thumb.save(thumb_buf, format=img_format.upper() if img_format != "webp" else "PNG")
        thumb_b64 = base64.b64encode(thumb_buf.getvalue()).decode("utf-8")

        return ProcessedImage(
            path=str(source_name),
            format=img_format,
            width=img.width,
            height=img.height,
            size_bytes=len(image_data),
            mode=img.mode,
            base64_data=b64,
            thumbnail_base64=thumb_b64,
            metadata={"original_format": img.format, "mode": img.mode},
        )

    def validate_format(self, path: str | Path) -> bool:
        """Check if the file format is supported."""
        ext = Path(path).suffix.lower().lstrip(".")
        try:
            fmt = ImageFormat(ext)
            return fmt in SUPPORTED_FORMATS
        except ValueError:
            return False

    def get_image_info(self, path: str | Path) -> dict[str, Any]:
        """Get basic image information without full processing."""
        from PIL import Image

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        img = Image.open(path)
        return {
            "path": str(path),
            "format": img.format or "unknown",
            "width": img.width,
            "height": img.height,
            "mode": img.mode,
            "size_bytes": path.stat().st_size,
            "aspect_ratio": img.width / max(img.height, 1),
        }

    def resize_for_model(
        self,
        image: ProcessedImage,
        max_size: int = 1024,
    ) -> ProcessedImage:
        """Resize image to fit within max_size while maintaining aspect ratio."""
        import base64
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(base64.b64decode(image.base64_data)))
        ratio = min(max_size / img.width, max_size / img.height, 1.0)
        if ratio < 1.0:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format=image.format.upper() if image.format != "webp" else "PNG")
            new_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            image.base64_data = new_b64
            image.width, image.height = new_size
            image.size_bytes = len(buf.getvalue())

        return image

    def run_ocr(self, image: ProcessedImage) -> str:
        """Run OCR on the image using Tesseract (if available)."""
        try:
            import base64
            import io

            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(base64.b64decode(image.base64_data)))
            text = pytesseract.image_to_string(img)
            image.ocr_text = text.strip()
            log.info("OCR extracted %d characters", len(text))
            return image.ocr_text
        except ImportError:
            log.warning("pytesseract not installed — OCR unavailable")
            return ""
        except Exception as exc:
            log.warning("OCR failed: %s", exc)
            return ""
