from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from io import BytesIO
from pathlib import Path

import pdfplumber
from PIL import Image

from app.chunking import Chunk


@dataclass(frozen=True)
class ChunkVisual:
    image: Image.Image
    kind: str
    sha256: str
    width: int
    height: int
    bbox_pdf_points: tuple[float, float, float, float] | None


def _image_sha256(image: Image.Image) -> str:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return hashlib.sha256(buffer.getvalue()).hexdigest()


class PdfChunkRenderer:
    def __init__(self, pdf_path: Path, dpi: int = 120, cache_pages: int = 4):
        if dpi < 72:
            raise ValueError("MULTIMODAL_RENDER_DPI must be at least 72")
        self.pdf_path = pdf_path
        self.dpi = dpi
        self.cache_pages = cache_pages
        self._pdf = None
        self._cache: OrderedDict[int, Image.Image] = OrderedDict()

    def __enter__(self) -> "PdfChunkRenderer":
        self._pdf = pdfplumber.open(str(self.pdf_path))
        return self

    def __exit__(self, *_args) -> None:
        if self._pdf is not None:
            self._pdf.close()
        self._cache.clear()

    def _page_image(self, page_number: int) -> Image.Image:
        if page_number in self._cache:
            image = self._cache.pop(page_number)
            self._cache[page_number] = image
            return image
        if self._pdf is None:
            raise RuntimeError("PdfChunkRenderer must be used as a context manager")
        image = self._pdf.pages[page_number - 1].to_image(
            resolution=self.dpi, antialias=True
        ).original.convert("RGB")
        self._cache[page_number] = image
        while len(self._cache) > self.cache_pages:
            self._cache.popitem(last=False)
        return image

    def render(self, chunk: Chunk) -> ChunkVisual:
        page_image = self._page_image(chunk.page)
        image = page_image
        bbox = chunk.visual_bbox
        if bbox is not None:
            if self._pdf is None:
                raise RuntimeError("PdfChunkRenderer must be used as a context manager")
            page = self._pdf.pages[chunk.page - 1]
            x_scale = page_image.width / float(page.width)
            y_scale = page_image.height / float(page.height)
            left, top, right, bottom = bbox
            padding_x = 6.0
            padding_y = 18.0
            pixel_box = (
                max(0, round((left - padding_x) * x_scale)),
                max(0, round((top - padding_y) * y_scale)),
                min(page_image.width, round((right + padding_x) * x_scale)),
                min(page_image.height, round((bottom + padding_y) * y_scale)),
            )
            image = page_image.crop(pixel_box)
        image = image.copy()
        return ChunkVisual(
            image=image,
            kind=chunk.visual_kind,
            sha256=_image_sha256(image),
            width=image.width,
            height=image.height,
            bbox_pdf_points=bbox,
        )
