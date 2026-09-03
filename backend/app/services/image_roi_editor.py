"""Hard-boundary ROI preparation and compositing for human image edits."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.image_pipeline import NormalizedBBox

PixelBBox = tuple[int, int, int, int]


class InvalidBBoxError(ValueError):
    """Raised when a normalized bbox cannot authorize a useful pixel region."""


class ROICompositeError(RuntimeError):
    """Raised when an edited ROI cannot be safely composed into its source image."""


@dataclass(frozen=True)
class ROIEditContext:
    image_size: tuple[int, int]
    original_bbox: PixelBBox
    expanded_bbox: PixelBBox

    @property
    def roi_size(self) -> tuple[int, int]:
        left, top, right, bottom = self.expanded_bbox
        return right - left, bottom - top

    @property
    def roi_original_bbox(self) -> PixelBBox:
        left, top, _, _ = self.expanded_bbox
        x1, y1, x2, y2 = self.original_bbox
        return x1 - left, y1 - top, x2 - left, y2 - top


@dataclass(frozen=True)
class ROICompositeResult:
    output_path: Path
    outside_diff_ratio: float
    outside_max_channel_diff: int
    mask_area_ratio: float
    edited_roi_resized: bool
    edited_roi_aspect_ratio_error: float


def validate_bbox(
    bbox: NormalizedBBox,
    image_width: int,
    image_height: int,
    *,
    min_side_px: int = 4,
    min_area_px: int = 64,
) -> PixelBBox:
    """Validate and convert a normalized bbox to a half-open pixel rectangle."""

    if image_width <= 0 or image_height <= 0:
        raise InvalidBBoxError("原图尺寸无效。")
    x1, y1, x2, y2 = bbox.root
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        raise InvalidBBoxError("bbox 坐标必须是有限数值。")
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise InvalidBBoxError("bbox 必须位于图片边界内且具有正宽高。")

    left = max(0, min(image_width - 1, math.floor(x1 * image_width)))
    top = max(0, min(image_height - 1, math.floor(y1 * image_height)))
    right = max(left + 1, min(image_width, math.ceil(x2 * image_width)))
    bottom = max(top + 1, min(image_height, math.ceil(y2 * image_height)))
    width, height = right - left, bottom - top
    if width < min_side_px or height < min_side_px:
        raise InvalidBBoxError(f"框选区域过小，宽高至少需要 {min_side_px} 像素。")
    if width * height < min_area_px:
        raise InvalidBBoxError(f"框选区域过小，面积至少需要 {min_area_px} 像素。")
    return left, top, right, bottom


def validate_bbox_for_image(
    image_path: Path,
    bbox: NormalizedBBox,
    *,
    min_side_px: int = 4,
    min_area_px: int = 64,
) -> PixelBBox:
    """Validate a normalized bbox against the actual trusted-image dimensions."""

    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except (OSError, ValueError) as exc:
        raise InvalidBBoxError("无法读取当前可信图片尺寸。") from exc
    return validate_bbox(
        bbox,
        width,
        height,
        min_side_px=min_side_px,
        min_area_px=min_area_px,
    )


def expand_bbox(
    bbox: PixelBBox,
    image_width: int,
    image_height: int,
    padding_ratio: float = 0.20,
) -> PixelBBox:
    """Expand a pixel bbox on every side and clamp it to the source image."""

    if padding_ratio < 0:
        raise ValueError("padding_ratio cannot be negative")
    left, top, right, bottom = bbox
    pad_x = math.ceil((right - left) * padding_ratio)
    pad_y = math.ceil((bottom - top) * padding_ratio)
    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image_width, right + pad_x),
        min(image_height, bottom + pad_y),
    )


def prepare_roi(
    trusted_path: Path,
    roi_before_path: Path,
    bbox: NormalizedBBox,
    *,
    padding_ratio: float = 0.20,
    min_side_px: int = 4,
    min_area_px: int = 64,
) -> ROIEditContext:
    """Crop an expanded ROI from the frozen trusted image."""

    with Image.open(trusted_path) as source_image:
        source = source_image.convert("RGB")
        original_bbox = validate_bbox(
            bbox,
            *source.size,
            min_side_px=min_side_px,
            min_area_px=min_area_px,
        )
        expanded_bbox = expand_bbox(original_bbox, *source.size, padding_ratio)
        roi = source.crop(expanded_bbox)
    roi_before_path.parent.mkdir(parents=True, exist_ok=True)
    roi.save(roi_before_path, format="PNG")
    return ROIEditContext(source.size, original_bbox, expanded_bbox)


def crop_roi(source_path: Path, output_path: Path, expanded_bbox: PixelBBox) -> Path:
    """Crop a known expanded ROI from an image with the trusted image dimensions."""

    with Image.open(source_path) as image:
        roi = image.convert("RGB").crop(expanded_bbox)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    roi.save(output_path, format="PNG")
    return output_path


def build_edit_mask(
    image_size: tuple[int, int],
    original_bbox: PixelBBox,
    feather_px: int = 12,
) -> Image.Image:
    """Build an inward-feathered mask whose non-zero pixels never leave the user bbox."""

    width, height = image_size
    left, top, right, bottom = original_bbox
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise InvalidBBoxError("edit mask bbox is outside its image")
    mask = np.zeros((height, width), dtype=np.float32)
    box_width, box_height = right - left, bottom - top
    if feather_px <= 0:
        mask[top:bottom, left:right] = 1.0
    else:
        feather = max(1, min(feather_px, box_width // 2, box_height // 2))
        xs = np.arange(box_width)
        ys = np.arange(box_height)
        distance_x = np.minimum(xs + 1, box_width - xs)
        distance_y = np.minimum(ys + 1, box_height - ys)
        distance = np.minimum(distance_y[:, None], distance_x[None, :])
        progress = np.clip(distance / feather, 0.0, 1.0)
        # A cosine ramp avoids a visible rectangular alpha step at the boundary.
        mask[top:bottom, left:right] = 0.5 - 0.5 * np.cos(np.pi * progress)
    return Image.fromarray(np.rint(mask * 255).astype(np.uint8), mode="L")


def composite_roi(
    trusted_path: Path,
    edited_roi_path: Path,
    output_path: Path,
    context: ROIEditContext,
    *,
    feather_px: int = 12,
    outside_tolerance: int = 0,
    max_aspect_ratio_error: float = 0.05,
) -> ROICompositeResult:
    """Composite an edited ROI into trusted pixels under a hard user-bbox mask."""

    with Image.open(trusted_path) as trusted_image:
        trusted = trusted_image.convert("RGB")
    if trusted.size != context.image_size:
        raise ROICompositeError("trusted image dimensions changed after ROI capture")
    try:
        with Image.open(edited_roi_path) as edited_image:
            edited_roi = edited_image.convert("RGB")
    except (OSError, ValueError) as exc:
        raise ROICompositeError("edited ROI is not a decodable image") from exc

    expected_aspect = context.roi_size[0] / context.roi_size[1]
    actual_aspect = edited_roi.width / edited_roi.height
    aspect_ratio_error = abs(actual_aspect / expected_aspect - 1.0)
    if aspect_ratio_error > max_aspect_ratio_error:
        raise ROICompositeError(
            "edited ROI aspect ratio does not match the source ROI "
            f"(expected={expected_aspect:.4f}, actual={actual_aspect:.4f}, "
            f"error={aspect_ratio_error:.4f})"
        )
    resized = edited_roi.size != context.roi_size
    if resized:
        edited_roi = edited_roi.resize(context.roi_size, Image.Resampling.LANCZOS)

    roi_mask = build_edit_mask(context.roi_size, context.roi_original_bbox, feather_px)
    final_image = trusted.copy()
    final_image.paste(edited_roi, context.expanded_bbox[:2], roi_mask)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_image.save(output_path, format="PNG")

    full_mask = Image.new("L", context.image_size, 0)
    full_mask.paste(roi_mask, context.expanded_bbox[:2])
    outside_ratio, outside_max = calculate_outside_diff(
        trusted, final_image, full_mask, tolerance=outside_tolerance
    )
    if outside_ratio > 0:
        output_path.unlink(missing_ok=True)
        raise ROICompositeError(
            "hard composite changed pixels outside the authorized mask "
            f"(ratio={outside_ratio:.8f}, max_diff={outside_max})"
        )
    mask_array = np.asarray(full_mask, dtype=np.uint8)
    mask_area_ratio = float(np.count_nonzero(mask_array) / mask_array.size)
    return ROICompositeResult(
        output_path=output_path,
        outside_diff_ratio=outside_ratio,
        outside_max_channel_diff=outside_max,
        mask_area_ratio=mask_area_ratio,
        edited_roi_resized=resized,
        edited_roi_aspect_ratio_error=aspect_ratio_error,
    )


def calculate_outside_diff(
    original: Image.Image,
    final: Image.Image,
    edit_mask: Image.Image,
    *,
    tolerance: int = 0,
) -> tuple[float, int]:
    """Return changed-pixel ratio and max channel delta outside the writable mask."""

    if original.size != final.size or original.size != edit_mask.size:
        raise ROICompositeError("outside-diff inputs must have identical dimensions")
    original_array = np.asarray(original.convert("RGB"), dtype=np.int16)
    final_array = np.asarray(final.convert("RGB"), dtype=np.int16)
    outside = np.asarray(edit_mask, dtype=np.uint8) == 0
    if not outside.any():
        return 0.0, 0
    channel_diff = np.abs(original_array - final_array)
    pixel_diff = channel_diff.max(axis=2)
    changed = outside & (pixel_diff > tolerance)
    return float(changed.sum() / outside.sum()), int(pixel_diff[outside].max(initial=0))


def save_debug_metadata(
    path: Path,
    *,
    context: ROIEditContext,
    original_bbox: NormalizedBBox,
    composite: ROICompositeResult,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "original_bbox_normalized": original_bbox.root,
                "original_bbox_pixels": context.original_bbox,
                "expanded_bbox_pixels": context.expanded_bbox,
                "image_size": context.image_size,
                "roi_size": context.roi_size,
                "outside_diff_ratio": composite.outside_diff_ratio,
                "outside_max_channel_diff": composite.outside_max_channel_diff,
                "mask_area_ratio": composite.mask_area_ratio,
                "edited_roi_resized": composite.edited_roi_resized,
                "edited_roi_aspect_ratio_error": composite.edited_roi_aspect_ratio_error,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
