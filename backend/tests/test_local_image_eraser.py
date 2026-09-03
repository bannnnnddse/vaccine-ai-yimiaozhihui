from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.schemas.image_pipeline import NormalizedBBox
from app.services.local_image_eraser import erase_on_uniform_background


@pytest.mark.asyncio
async def test_erases_only_the_selected_title_on_a_uniform_background(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "output.png"
    image = Image.new("RGB", (200, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 8, 145, 22), fill="black")
    draw.rectangle((20, 70, 180, 105), fill="royalblue")
    image.save(source_path)

    result = await erase_on_uniform_background(
        source_path, output_path, NormalizedBBox([0.2, 0.02, 0.8, 0.25])
    )

    assert result.applied is True
    with Image.open(output_path) as output:
        assert output.getpixel((100, 15)) == (255, 255, 255)
        assert output.getpixel((100, 90)) == (65, 105, 225)


@pytest.mark.asyncio
async def test_declines_local_erase_when_surrounding_background_is_complex(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "output.png"
    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, 120, 8):
        draw.rectangle((x, 30, x + 3, 90), fill="black")
    image.save(source_path)

    result = await erase_on_uniform_background(
        source_path, output_path, NormalizedBBox([0.35, 0.35, 0.65, 0.65])
    )

    assert result.applied is False
    assert not output_path.exists()
