"""Tests for the fast native WAN image adapter."""

from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.schemas.image_pipeline import NormalizedBBox
from app.schemas.science_figure import ChineseFigureBrief
from app.services.cell_ip_assets import (
    CellIpAssetError,
    CellIpAssetService,
    CellIpGenerationProfile,
)
from app.services.wan_image_generator import (
    WanImageGenerator,
    WanImageGeneratorError,
    build_cell_ip_prompt,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "pfZFQAAAAABJRU5ErkJggg=="
)
SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "cell-ip-illustrations"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        dashscope_api_key="test-key",
        cell_ip_enabled=False,
        z_image_endpoint="https://dashscope.example/api/v1/services/aigc/multimodal-generation/generation",
    )


def _fast_brief() -> ChineseFigureBrief:
    return ChineseFigureBrief(
        image_type="mechanism_diagram",
        generation_route="fast",
        optimized_chinese_prompt=(
            "制作9:16竖版中文科普图解，展示疫苗抗原被免疫细胞识别，"
            "随后形成免疫记忆的因果顺序，并保留清晰醒目的中文标签。"
        ),
        chinese_labels=["疫苗抗原", "免疫细胞", "免疫记忆"],
        scientific_claims=["疫苗抗原可被免疫细胞识别。"],
        core_causal_steps=[
            {"primary_relation": "疫苗抗原被免疫细胞识别"},
            {"primary_relation": "免疫细胞形成免疫记忆"},
        ],
        route_reason="中文标签优先使用快速路径。",
    )


@pytest.mark.asyncio
async def test_wan_generator_submits_chinese_prompt_and_writes_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda self, **kwargs: captured.update(kwargs) or PNG_BYTES,
    )

    settings = _settings()
    result = await WanImageGenerator(settings).generate(
        brief=_fast_brief(),
        output_path=tmp_path / "fast.png",
        cancel_event=asyncio.Event(),
    )

    reference = (
        settings.reference_image_dir / "mechanism_diagram/runtime-reference.jpg"
    ).read_bytes()
    assert captured["model"] == "wan2.7-image-pro"
    assert captured["aspect_ratio"] == "9:16"
    assert captured["image_size"] == "2K"
    assert captured["reference_images"] == [reference]
    assert "疫苗抗原被免疫细胞识别" in captured["prompt"]
    assert "【信息密度与完整性契约】" in captured["prompt"]
    assert "至少设置 3 个信息分区" in captured["prompt"]
    assert result.final_path.read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_wan_generator_rejects_non_png_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda *args, **kwargs: b"not-png",
    )

    with pytest.raises(WanImageGeneratorError, match="PNG"):
        await WanImageGenerator(_settings()).generate(
            brief=_fast_brief(),
            output_path=tmp_path / "fast.png",
            cancel_event=asyncio.Event(),
        )


@pytest.mark.asyncio
async def test_wan_generator_rejects_png_signature_without_a_decodable_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda *args, **kwargs: b"\x89PNG\r\n\x1a\nnot-an-image",
    )
    output_path = tmp_path / "fast.png"

    with pytest.raises(WanImageGeneratorError, match="PNG"):
        await WanImageGenerator(_settings()).generate(
            brief=_fast_brief(),
            output_path=output_path,
            cancel_event=asyncio.Event(),
        )

    assert not output_path.exists()


@pytest.mark.asyncio
async def test_wan_generator_uses_proxy_free_session() -> None:
    generator = WanImageGenerator(_settings())
    assert generator._provider._session.trust_env is False


@pytest.mark.asyncio
async def test_wan_generator_includes_user_prompt_in_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda self, **kwargs: captured.update(kwargs) or PNG_BYTES,
    )

    await WanImageGenerator(_settings()).generate(
        brief=_fast_brief(),
        output_path=tmp_path / "fast.png",
        cancel_event=asyncio.Event(),
        user_prompt="帮我画一张抗原呈递的科普图",
    )

    prompt = captured["prompt"]
    assert isinstance(prompt, str)
    assert "【用户原始需求】" in prompt
    assert "帮我画一张抗原呈递的科普图" in prompt


@pytest.mark.asyncio
async def test_enabled_skill_does_not_override_default_scientific_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda self, **kwargs: captured.update(kwargs) or PNG_BYTES,
    )
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = SKILL_DIR

    result = await WanImageGenerator(settings).generate(
        brief=_fast_brief(),
        output_path=tmp_path / "scientific.png",
        cancel_event=asyncio.Event(),
        user_prompt="HPV疫苗作用机制图解",
    )

    reference = (
        settings.reference_image_dir / "mechanism_diagram/runtime-reference.jpg"
    ).read_bytes()
    assert captured["aspect_ratio"] == "9:16"
    assert captured["reference_images"] == [reference]
    assert result.cell_ip_profile is None


@pytest.mark.asyncio
async def test_wan_generator_uses_cell_ip_references_and_16_by_9_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda self, **kwargs: captured.update(kwargs) or PNG_BYTES,
    )
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = SKILL_DIR
    brief = _fast_brief().model_copy(update={"visual_profile": "cell_ip_scientific"})

    result = await WanImageGenerator(settings).generate(
        brief=brief,
        output_path=tmp_path / "cell-ip.png",
        cancel_event=asyncio.Event(),
        user_prompt="展示B细胞识别抗原",
    )

    assert captured["aspect_ratio"] == "16:9"
    references = captured["reference_images"]
    assert isinstance(references, list) and len(references) == 2
    decoded = [Image.open(io.BytesIO(value)) for value in references]
    assert all(image.mode == "RGB" for image in decoded)
    assert result.cell_ip_profile is not None
    assert result.cell_ip_profile.reference_names == (
        "canonical:b_cell",
        "canonical:antigen",
    )
    assert "完整保留核心因果链" in captured["prompt"]
    assert "允许一个必要的简短中文标题" in captured["prompt"]
    assert "固定角色外观契约" in captured["prompt"]
    assert "【信息密度与完整性契约】" in captured["prompt"]
    assert "复杂度等级：详细机制图" in captured["prompt"]
    assert "B 细胞：蓝色圆体" in captured["prompt"]
    assert "B 细胞 的独立 canonical 身份" in captured["prompt"]
    assert result.cell_ip_profile.role_ids == ("b_cell", "antigen")


def test_locked_hpv_drops_refiner_appearance_text_and_uses_its_canonical_reference() -> None:
    brief = _fast_brief().model_copy(
        update={
            "visual_profile": "cell_ip_scientific",
            "governed_role_ids": ["virus"],
            "scene_direction": "黄色球形 HPV 位于左侧并靠近宫颈上皮细胞膜。",
            "optimized_chinese_prompt": (
                "黄色球形 HPV 位于左侧，带绿色刺突并靠近宫颈上皮细胞膜，"
                "使用清晰中文标签展示科学过程。"
            ),
            "chinese_labels": ["HPV", "宫颈上皮细胞"],
            "core_causal_steps": [{"primary_relation": "HPV 靠近宫颈上皮细胞膜。"}],
        }
    )
    profile = CellIpAssetService(SKILL_DIR).profile_for(brief, "黄色球形 HPV 与宫颈上皮细胞结合")

    prompt = build_cell_ip_prompt(brief, profile)

    assert profile.reference_names == ("canonical:virus",)
    assert "黄色球形" not in prompt
    assert "绿色刺突" not in prompt
    assert "HPV 靠近宫颈上皮细胞膜" in prompt


def test_locked_scene_direction_keeps_normal_role_and_visual_words() -> None:
    brief = _fast_brief().model_copy(
        update={
            "visual_profile": "cell_ip_scientific",
            "governed_role_ids": ["b_cell", "antibody"],
            "scene_direction": "左侧B细胞角色向右侧抗体释放，视觉焦点是清楚的箭头。",
            "core_causal_steps": [{"primary_relation": "B细胞分泌抗体。"}],
        }
    )
    profile = CellIpAssetService(SKILL_DIR).profile_for(brief, "B细胞产生抗体")

    prompt = build_cell_ip_prompt(brief, profile)

    assert "左侧B细胞角色向右侧抗体释放" in prompt


@pytest.mark.asyncio
async def test_t_and_b_cells_send_independent_canonical_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda self, **kwargs: captured.update(kwargs) or PNG_BYTES,
    )
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = SKILL_DIR
    brief = _fast_brief().model_copy(
        update={
            "visual_profile": "cell_ip_scientific",
            "governed_role_ids": ["helper_t", "b_cell"],
            "scene_direction": "辅助性T细胞位于B细胞左侧并传递激活信号。",
            "chinese_labels": ["激活信号"],
            "scientific_claims": ["辅助性T细胞支持B细胞应答。"],
            "core_causal_steps": [{"primary_relation": "辅助性T细胞向B细胞传递激活信号。"}],
        }
    )

    result = await WanImageGenerator(settings).generate(
        brief, tmp_path / "t-b.png", asyncio.Event(), "T细胞正在激活B细胞"
    )

    assert result.reference_names_sent == ("canonical:helper_t", "canonical:b_cell")
    assert len(captured["reference_images"]) == 2


@pytest.mark.asyncio
async def test_wan_generator_fails_fast_when_locked_canonical_reference_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 7: a matched locked role with no canonical reference must not
    silently fall back to plain generation."""
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = SKILL_DIR
    broken = CellIpGenerationProfile(
        visual_profile="cell_ip_scientific",
        role_ids=("helper_t",),
        role_names=("辅助性 T 细胞",),
        role_specs=("辅助性 T 细胞：浅绿圆体",),
        unmatched_cell_terms=(),
        aspect_ratio="16:9",
        composition="causal_diagram",
        max_causal_steps=4,
        allow_title=True,
        style_instruction="使用固定角色并保留科学结构。",
        composition_instruction="完整保留核心因果链和箭头方向。",
        prohibitions=("3D",),
        reference_names=("style",),
        references=(b"anchor",),
    )
    monkeypatch.setattr(
        "app.services.wan_image_generator.CellIpAssetService.profile_for",
        lambda self, brief, user_prompt=None: broken,
    )
    brief = _fast_brief().model_copy(
        update={
            "visual_profile": "cell_ip_scientific",
            "governed_role_ids": ["helper_t"],
        }
    )

    with pytest.raises(CellIpAssetError, match="missing a canonical reference"):
        await WanImageGenerator(settings).generate(
            brief=brief,
            output_path=tmp_path / "fail-fast.png",
            cancel_event=asyncio.Event(),
            user_prompt="T细胞正在激活B细胞",
        )


def test_wan_generator_fails_at_startup_when_enabled_skill_is_missing(tmp_path: Path) -> None:
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = tmp_path / "missing"

    with pytest.raises(CellIpAssetError, match="manifest"):
        WanImageGenerator(settings)


@pytest.mark.asyncio
async def test_cell_ip_edit_aligns_references_and_bbox_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings()
    settings.cell_ip_enabled = True
    settings.cell_ip_skill_dir = SKILL_DIR
    generator = WanImageGenerator(settings)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        generator._provider,
        "_request_json",
        lambda payload, **kwargs: captured.update(payload=payload) or {"output": {}},
    )
    monkeypatch.setattr(generator._provider, "_find_image_url", lambda response: "https://x")
    monkeypatch.setattr(
        generator._provider, "_download_image", lambda url, **kwargs: PNG_BYTES
    )
    source_path = tmp_path / "source.png"
    source_path.write_bytes(PNG_BYTES)
    profile = CellIpAssetService(SKILL_DIR).profile_for(
        _fast_brief().model_copy(update={"visual_profile": "cell_ip_scientific"}),
        "展示B细胞识别抗原",
    )

    await generator.edit(
        source_path=source_path,
        output_path=tmp_path / "edited.png",
        instruction="让B细胞举起抗体",
        bbox=NormalizedBBox([0.1, 0.2, 0.7, 0.8]),
        cancel_event=asyncio.Event(),
        cell_ip_profile=profile,
    )

    payload = captured["payload"]
    content = payload["input"]["messages"][0]["content"]
    assert len(content) == 4
    assert payload["parameters"]["bbox_list"] == [[], [], [[24, 48, 168, 192]]]
    encoded_source = content[-2]["image"].split(",", 1)[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded_source))) as provider_source:
        assert provider_source.size == (240, 240)
        assert provider_source.mode == "RGB"
    assert "唯一待编辑的 ROI 画布" in content[-1]["text"]
    assert "不得复制参考图的排列" in content[-1]["text"]


@pytest.mark.asyncio
async def test_roi_edit_upscales_short_side_to_wan_minimum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = WanImageGenerator(_settings())
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        generator._provider,
        "_request_json",
        lambda payload, **kwargs: captured.update(payload=payload) or {"output": {}},
    )
    monkeypatch.setattr(generator._provider, "_find_image_url", lambda response: "https://x")
    monkeypatch.setattr(generator._provider, "_download_image", lambda url, **kwargs: PNG_BYTES)
    source_path = tmp_path / "roi.png"
    Image.new("RGB", (280, 186), "white").save(source_path)

    await generator.edit(
        source_path=source_path,
        output_path=tmp_path / "edited.png",
        instruction="修改右手手势",
        bbox=NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
        cancel_event=asyncio.Event(),
    )

    payload = captured["payload"]
    content = payload["input"]["messages"][0]["content"]
    encoded_source = content[0]["image"].split(",", 1)[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded_source))) as provider_source:
        assert provider_source.size == (362, 240)
    assert payload["parameters"]["bbox_list"] == [[[0, 0, 362, 240]]]


@pytest.mark.asyncio
async def test_wan_generator_fails_closed_when_reference_image_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    settings = _settings()
    settings.reference_image_dir = tmp_path / "no-such-references"

    with pytest.raises(RuntimeError, match="reference image missing"):
        await WanImageGenerator(settings).generate(
            brief=_fast_brief(),
            output_path=tmp_path / "fast.png",
            cancel_event=asyncio.Event(),
        )


@pytest.mark.asyncio
async def test_wan_generator_stops_before_generation_when_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        lambda *args, **kwargs: pytest.fail("provider must not be called"),
    )
    cancel_event = asyncio.Event()
    cancel_event.set()

    with pytest.raises(asyncio.CancelledError):
        await WanImageGenerator(_settings()).generate(
            brief=_fast_brief(),
            output_path=tmp_path / "fast.png",
            cancel_event=cancel_event,
        )


@pytest.mark.asyncio
async def test_wan_generator_stops_after_generation_when_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancel_event = asyncio.Event()

    def generate_and_cancel(*args: object, **kwargs: object) -> bytes:
        cancel_event.set()
        return PNG_BYTES

    monkeypatch.setattr(
        "app.services.wan_api_client.WanApiClient.generate",
        generate_and_cancel,
    )
    output_path = tmp_path / "fast.png"

    with pytest.raises(asyncio.CancelledError):
        await WanImageGenerator(_settings()).generate(
            brief=_fast_brief(),
            output_path=output_path,
            cancel_event=cancel_event,
        )

    assert not output_path.exists()
