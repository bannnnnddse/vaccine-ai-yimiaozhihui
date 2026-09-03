from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.schemas.image_pipeline import NormalizedBBox
from app.services.image_roi_editor import (
    InvalidBBoxError,
    ROICompositeError,
    build_edit_mask,
    composite_roi,
    expand_bbox,
    prepare_roi,
    validate_bbox,
)


def test_bbox_expansion_adds_twenty_percent_context() -> None:
    assert expand_bbox((20, 30, 60, 70), 100, 100, 0.20) == (12, 22, 68, 78)


def test_bbox_expansion_clamps_at_image_edges() -> None:
    assert expand_bbox((0, 2, 30, 22), 100, 80, 0.20) == (0, 0, 36, 26)


def test_prepare_roi_crops_expanded_region_from_trusted_image(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted.png"
    roi = tmp_path / "roi.png"
    Image.new("RGB", (100, 80), "white").save(trusted)

    context = prepare_roi(trusted, roi, NormalizedBBox([0.2, 0.25, 0.6, 0.75]))

    assert context.original_bbox == (20, 20, 60, 60)
    assert context.expanded_bbox == (12, 12, 68, 68)
    with Image.open(roi) as cropped:
        assert cropped.size == context.roi_size == (56, 56)


def test_edit_mask_is_correct_size_smooth_and_zero_outside_bbox() -> None:
    mask = build_edit_mask((40, 30), (10, 5, 30, 25), feather_px=5)
    array = np.asarray(mask)

    assert mask.size == (40, 30)
    assert np.count_nonzero(array[:5, :]) == 0
    assert np.count_nonzero(array[:, :10]) == 0
    assert 0 < array[5, 10] < array[10, 15] == 255


def test_composite_preserves_every_pixel_outside_user_bbox(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted.png"
    roi_before = tmp_path / "roi-before.png"
    roi_after = tmp_path / "roi-after.png"
    final = tmp_path / "final.png"
    Image.new("RGB", (100, 80), (240, 241, 242)).save(trusted)
    context = prepare_roi(trusted, roi_before, NormalizedBBox([0.2, 0.25, 0.6, 0.75]))
    Image.new("RGB", context.roi_size, (10, 20, 30)).save(roi_after)

    result = composite_roi(trusted, roi_after, final, context, feather_px=6)

    original_array = np.asarray(Image.open(trusted).convert("RGB"))
    final_array = np.asarray(Image.open(final).convert("RGB"))
    left, top, right, bottom = context.original_bbox
    outside = np.ones(original_array.shape[:2], dtype=bool)
    outside[top:bottom, left:right] = False
    assert np.array_equal(original_array[outside], final_array[outside])
    assert result.outside_diff_ratio == 0
    assert not np.array_equal(
        original_array[top:bottom, left:right], final_array[top:bottom, left:right]
    )


@pytest.mark.parametrize(
    "bbox",
    [
        [-0.1, 0.1, 0.5, 0.5],
        [0.5, 0.1, 0.5, 0.5],
        [0.10, 0.10, 0.11, 0.11],
    ],
)
def test_invalid_or_too_small_bbox_is_rejected(bbox: list[float]) -> None:
    if bbox[0] < 0 or bbox[2] <= bbox[0]:
        with pytest.raises((ValueError, InvalidBBoxError)):
            normalized = NormalizedBBox(bbox)
            validate_bbox(normalized, 100, 100)
        return
    with pytest.raises(InvalidBBoxError, match="过小"):
        validate_bbox(NormalizedBBox(bbox), 100, 100)


def test_mismatched_edited_roi_is_explicitly_resized(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted.png"
    roi_before = tmp_path / "roi-before.png"
    roi_after = tmp_path / "roi-after.png"
    final = tmp_path / "final.png"
    Image.new("RGB", (100, 80), "white").save(trusted)
    context = prepare_roi(trusted, roi_before, NormalizedBBox([0.2, 0.2, 0.6, 0.6]))
    Image.new("RGB", (28, 22), "black").save(roi_after)

    result = composite_roi(trusted, roi_after, final, context)

    assert result.edited_roi_resized is True
    with Image.open(final) as image:
        assert image.size == (100, 80)


def test_grossly_mismatched_edited_roi_aspect_ratio_is_rejected(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted.png"
    roi_before = tmp_path / "roi-before.png"
    roi_after = tmp_path / "roi-after.png"
    Image.new("RGB", (100, 80), "white").save(trusted)
    context = prepare_roi(trusted, roi_before, NormalizedBBox([0.2, 0.2, 0.6, 0.6]))
    Image.new("RGB", (100, 100), "black").save(roi_after)

    with pytest.raises(ROICompositeError, match="aspect ratio"):
        composite_roi(trusted, roi_after, tmp_path / "final.png", context)


def test_undecodable_edited_roi_is_rejected(tmp_path: Path) -> None:
    trusted = tmp_path / "trusted.png"
    roi_before = tmp_path / "roi-before.png"
    roi_after = tmp_path / "roi-after.png"
    Image.new("RGB", (100, 80), "white").save(trusted)
    context = prepare_roi(trusted, roi_before, NormalizedBBox([0.2, 0.2, 0.6, 0.6]))
    roi_after.write_text("not an image", encoding="utf-8")

    with pytest.raises(ROICompositeError, match="decodable"):
        composite_roi(trusted, roi_after, tmp_path / "final.png", context)
