"""Safe local erasure for selections surrounded by a uniform background."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.image_pipeline import NormalizedBBox


@dataclass(frozen=True)
class LocalEraseResult:
    applied: bool
    reason: str


async def erase_on_uniform_background(
    source_path: Path, output_path: Path, bbox: NormalizedBBox
) -> LocalEraseResult:
    """Erase only ``bbox`` when its surrounding pixels form a stable background.

    This deliberately declines textured/complex regions.  It is a deterministic
    alternative for title deletion, where a generative editor may rewrite the
    rest of a diagram despite receiving a local bounding box.
    """

    return await asyncio.to_thread(_erase_on_uniform_background, source_path, output_path, bbox)


def _erase_on_uniform_background(
    source_path: Path, output_path: Path, bbox: NormalizedBBox
) -> LocalEraseResult:
    with Image.open(source_path) as image:
        source = image.convert("RGB")
    pixels = np.asarray(source, dtype=np.uint8).copy()
    height, width = pixels.shape[:2]
    x1, y1, x2, y2 = bbox.root
    left, top = int(round(x1 * width)), int(round(y1 * height))
    right, bottom = int(round(x2 * width)), int(round(y2 * height))
    if right <= left or bottom <= top:
        return LocalEraseResult(False, "选区无有效面积")

    padding = max(6, min(width, height) // 180)
    outer_left, outer_top = max(0, left - padding), max(0, top - padding)
    outer_right, outer_bottom = min(width, right + padding), min(height, bottom + padding)
    ring = pixels[outer_top:outer_bottom, outer_left:outer_right].copy()
    ring[top - outer_top : bottom - outer_top, left - outer_left : right - outer_left] = 0
    ring_mask = np.ones(ring.shape[:2], dtype=bool)
    ring_mask[top - outer_top : bottom - outer_top, left - outer_left : right - outer_left] = False
    samples = ring[ring_mask]
    if samples.size == 0:
        return LocalEraseResult(False, "选区周围没有足够的背景像素")

    background = np.median(samples, axis=0).astype(np.uint8)
    distance = np.abs(samples.astype(np.int16) - background.astype(np.int16)).mean(axis=1)
    stable_fraction = float(np.mean(distance <= 18))
    if stable_fraction < 0.84:
        return LocalEraseResult(False, "选区周围背景不够均匀，需使用生成式局部编辑")

    pixels[top:bottom, left:right] = background
    Image.fromarray(pixels, mode="RGB").save(output_path, format="PNG")
    return LocalEraseResult(True, "选区周围背景均匀，已仅擦除框内内容")
