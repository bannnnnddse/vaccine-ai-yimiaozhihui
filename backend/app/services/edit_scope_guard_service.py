"""Explainable outside-bbox pixel-change guard for every image revision."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.image_pipeline import EditScopeGuardResult, NormalizedBBox


class EditScopeGuardService:
    def __init__(self, threshold: float, minimum_inside_change: float = 0.01) -> None:
        self._threshold = threshold
        self._minimum_inside_change = minimum_inside_change

    async def check(
        self, original_path: Path, candidate_path: Path, bbox: NormalizedBBox
    ) -> EditScopeGuardResult:
        outside_score, inside_score, outside_regions = await asyncio.to_thread(
            _change_scores, original_path, candidate_path, bbox
        )
        changed_outside = outside_score > self._threshold
        insufficient_inside = inside_score < self._minimum_inside_change
        passed = not changed_outside and not insufficient_inside
        if changed_outside:
            notes = "本次编辑影响了非目标区域，候选未被接受；请重试或重新框选。"
        elif insufficient_inside:
            notes = "框内变化不足，无法确认修改要求已执行；候选未被接受。"
        else:
            notes = "框外变化处于当前工程阈值内，且框内检测到有效变化。"
        return EditScopeGuardResult(
            passed=passed,
            outside_change_score=round(outside_score, 6),
            threshold=self._threshold,
            changed_outside_bbox=changed_outside,
            inside_change_score=round(inside_score, 6),
            minimum_inside_change=self._minimum_inside_change,
            insufficient_change_inside_bbox=insufficient_inside,
            outside_change_regions=outside_regions,
            notes=notes,
        )


def _change_scores(
    original_path: Path, candidate_path: Path, bbox: NormalizedBBox
) -> tuple[float, float, list[NormalizedBBox]]:
    with Image.open(original_path) as original_image:
        original = original_image.convert("RGB")
    with Image.open(candidate_path) as candidate_image:
        candidate = candidate_image.convert("RGB").resize(original.size, Image.Resampling.LANCZOS)
    original_array = np.asarray(original, dtype=np.float32)
    candidate_array = np.asarray(candidate, dtype=np.float32)
    height, width = original_array.shape[:2]
    x1, y1, x2, y2 = bbox.root
    left, top = int(round(x1 * width)), int(round(y1 * height))
    right, bottom = int(round(x2 * width)), int(round(y2 * height))
    outside_mask = np.ones((height, width), dtype=bool)
    outside_mask[top:bottom, left:right] = False
    inside_mask = ~outside_mask
    difference = np.abs(original_array - candidate_array).mean(axis=2) / 255.0
    outside_score = float(difference[outside_mask].mean()) if outside_mask.any() else 0.0
    inside_score = float(difference[inside_mask].mean()) if inside_mask.any() else 0.0
    outside_regions = _outside_change_regions(
        difference,
        outside_mask,
        width=width,
        height=height,
        threshold=outside_score,
    )
    return outside_score, inside_score, outside_regions


def _outside_change_regions(
    difference: np.ndarray,
    outside_mask: np.ndarray,
    *,
    width: int,
    height: int,
    threshold: float,
) -> list[NormalizedBBox]:
    """Return up to four deterministic grid cells with the strongest outside change."""

    candidates: list[tuple[float, NormalizedBBox]] = []
    for row in range(4):
        for column in range(4):
            top, bottom = row * height // 4, (row + 1) * height // 4
            left, right = column * width // 4, (column + 1) * width // 4
            mask = outside_mask[top:bottom, left:right]
            if not mask.any():
                continue
            score = float(difference[top:bottom, left:right][mask].mean())
            if threshold <= 0 or score < threshold:
                continue
            candidates.append(
                (
                    score,
                    NormalizedBBox([left / width, top / height, right / width, bottom / height]),
                )
            )
    return [bbox for _, bbox in sorted(candidates, key=lambda item: item[0], reverse=True)[:4]]
