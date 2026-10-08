import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import Request
from openai import APITimeoutError
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.science_figure import ChineseFigureBrief
from app.services.science_image_organizer import (
    ScienceImageNotConfiguredError,
    ScienceImageOrganizer,
    ScienceImageOrganizerError,
)


def _response(payload: dict[str, object] | str) -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _chinese_brief_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "image_type": "mechanism_diagram",
        "generation_route": "fast",
        "optimized_chinese_prompt": (
            "制作9:16竖版中文免疫科普图解，依次展示疫苗抗原被免疫细胞识别、"
            "激活适应性免疫反应并形成免疫记忆；使用清晰中文标签和简洁医学插画。"
        ),
        "chinese_labels": ["疫苗抗原", "免疫细胞", "免疫记忆"],
        "scientific_claims": ["疫苗抗原可触发适应性免疫反应。"],
        "core_causal_steps": [
            {
                "primary_relation": "疫苗抗原促进免疫细胞识别并形成免疫记忆。",
            },
        ],
        "route_reason": "单一因果链和有限中文标签适合快速生成。",
    }
    payload.update(overrides)
    return payload


def _organizer(
    client: AsyncMock,
    *,
    cell_ip_enabled: bool = False,
) -> ScienceImageOrganizer:
    return ScienceImageOrganizer(
        Settings(
            _env_file=None,
            dashscope_api_key="test-key",
            cell_ip_enabled=cell_ip_enabled,
        ),
        client,
    )


def test_chinese_figure_brief_supports_fast_route() -> None:
    brief = ChineseFigureBrief.model_validate(_chinese_brief_payload())

    assert brief.generation_route == "fast"
    assert brief.chinese_labels == ["疫苗抗原", "免疫细胞", "免疫记忆"]
    assert len(brief.core_causal_steps) == 1


def test_chinese_figure_brief_limits_core_causal_steps_to_one_through_four() -> None:
    payload = _chinese_brief_payload()

    for step_count in (0, 5):
        invalid_payload = deepcopy(payload)
        invalid_payload["core_causal_steps"] = payload["core_causal_steps"][:step_count]
        if step_count == 5:
            invalid_payload["core_causal_steps"].extend(
                deepcopy(payload["core_causal_steps"] * 4)
            )

        with pytest.raises(ValidationError):
            ChineseFigureBrief.model_validate(invalid_payload)


@pytest.mark.asyncio
async def test_refiner_returns_fast_chinese_brief_for_simple_topic() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_chinese_brief_payload())

    brief = await _organizer(client).refine("疫苗帮助免疫系统识别抗原")

    assert brief.generation_route == "fast"
    assert brief.optimized_chinese_prompt.startswith("制作9:16竖版中文")
    assert brief.chinese_labels == ["疫苗抗原", "免疫细胞", "免疫记忆"]
    client.chat.completions.create.assert_awaited_once()
    call = client.chat.completions.create.await_args.kwargs
    assert call["model"] == "qwen3.8-flash"
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"enable_thinking": False}
    system_prompt = call["messages"][0]["content"]
    assert "generation_route" in system_prompt
    assert '"fast"' in system_prompt
    assert "9:16" in system_prompt
    assert "简体中文" in system_prompt
    assert "因果顺序" in system_prompt


@pytest.mark.asyncio
async def test_refiner_automatically_routes_cellular_subjects_to_scientific_ip() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_chinese_brief_payload())

    brief = await _organizer(client, cell_ip_enabled=True).refine("树突状细胞呈递抗原")

    system_prompt = client.chat.completions.create.await_args.kwargs["messages"][0]["content"]
    assert "16:9" in system_prompt
    assert "cell_ip_editorial" in system_prompt
    assert "cell_ip_scientific" in system_prompt
    assert "9:16" in system_prompt
    assert brief.visual_profile == "cell_ip_scientific"


@pytest.mark.asyncio
async def test_refiner_locks_hpv_before_it_can_write_a_visual_description() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(
            scene_direction="HPV 位于左侧并靠近宫颈上皮细胞膜。",
            optimized_chinese_prompt=(
                "制作横版图解，展示黄色球形HPV靠近宫颈上皮细胞膜并形成结合关系，"
                "使用清楚标签表现科学过程和空间关系。"
            ),
            chinese_labels=["HPV", "宫颈上皮细胞"],
            scientific_claims=["HPV 可与宫颈上皮细胞结合。"],
            core_causal_steps=[{"primary_relation": "HPV 靠近宫颈上皮细胞膜。"}],
        )
    )

    brief = await _organizer(client, cell_ip_enabled=True).refine("黄色球形 HPV 与宫颈上皮细胞结合")

    system_prompt = client.chat.completions.create.await_args.kwargs["messages"][0]["content"]
    assert brief.governed_role_ids == ["virus"]
    assert '"visual_authority":"LOCKED"' in system_prompt
    assert "不得描述、重述或改写其颜色" in system_prompt


@pytest.mark.asyncio
async def test_refiner_locks_roles_introduced_by_the_brief_even_when_prompt_names_none() -> None:
    """Regression: '水痘疫苗机制图' names no role, but the refiner's structured
    brief introduces 树突状/辅助性T/记忆B/病毒 — those must be locked so their
    canonical references are actually sent."""
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(
            chinese_labels=[
                "水痘-带状疱疹病毒 (VZV)",
                "树突状细胞",
                "辅助性T细胞",
                "B淋巴细胞",
                "记忆B细胞",
            ],
            scientific_claims=["树突状细胞提呈病毒抗原并激活辅助性T细胞。"],
            core_causal_steps=[
                {"primary_relation": "树突状细胞激活辅助性T细胞。"},
                {"primary_relation": "B细胞分化为记忆B细胞。"},
            ],
        )
    )

    brief = await _organizer(client, cell_ip_enabled=True).refine("生成一张水痘疫苗机制图")

    assert "virus" in brief.governed_role_ids
    assert "dendritic" in brief.governed_role_ids
    assert "helper_t" in brief.governed_role_ids
    assert "memory_b" in brief.governed_role_ids
    assert "b_cell" in brief.governed_role_ids


@pytest.mark.asyncio
async def test_refiner_keeps_non_cellular_subjects_on_scientific_default() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(
            optimized_chinese_prompt=(
                "制作9:16竖版中文公共卫生图解，展示正确洗手和通风等日常防护行为，"
                "使用简洁的步骤与清楚中文标签说明正确行为。"
            ),
            chinese_labels=["洗手", "通风", "防护"],
            scientific_claims=["日常防护可降低呼吸道传播风险。"],
            core_causal_steps=[{"primary_relation": "正确洗手和通风有助于降低传播风险。"}],
        )
    )

    brief = await _organizer(client, cell_ip_enabled=True).refine("社区呼吸道防护宣传图")

    assert brief.visual_profile == "scientific_diagram"


@pytest.mark.asyncio
async def test_refiner_routes_explicit_ip_mechanism_to_scientific_ip_profile() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(visual_profile="cell_ip_editorial")
    )

    brief = await _organizer(client, cell_ip_enabled=True).refine(
        "使用固定细胞IP画一张抗原呈递机制图"
    )

    assert brief.visual_profile == "cell_ip_scientific"


@pytest.mark.asyncio
async def test_refiner_keeps_simple_ip_article_art_as_editorial_profile() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(visual_profile="cell_ip_editorial")
    )

    brief = await _organizer(client, cell_ip_enabled=True).refine(
        "使用固定细胞IP做一张正文配图，表现B细胞发现抗原"
    )

    assert brief.visual_profile == "cell_ip_editorial"


@pytest.mark.asyncio
async def test_refiner_keeps_fast_without_explicit_academic_request() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _chinese_brief_payload(
            generation_route="fast",
            optimized_chinese_prompt=(
                "制作9:16竖版免疫机制图解，所有文字使用简体中文，以“大标题：免疫应答协作”"
                "开篇；按因果顺序展示树突状细胞呈递抗原、辅助性T细胞激活、B细胞分化和"
                "抗体分泌，并在淋巴结与组织区域之间呈现空间层级和关键细胞关系。"
            ),
            chinese_labels=["树突状细胞", "辅助性T细胞", "B细胞", "抗体"],
            scientific_claims=["抗原呈递可参与启动适应性免疫应答。"],
            core_causal_steps=[
                {"primary_relation": "树突状细胞将处理后的抗原呈递给辅助性T细胞。"},
                {"primary_relation": "辅助性T细胞的活化信号支持B细胞应答。"},
                {"primary_relation": "部分活化B细胞可分化为分泌抗体的浆细胞。"},
            ],
            route_reason="多种细胞的依赖步骤需跨区域呈现，构图层级对理解至关重要。",
        )
    )

    brief = await _organizer(client).refine("抗原呈递到B细胞产生抗体的多细胞免疫机制")

    assert brief.generation_route == "fast"
    assert len(brief.core_causal_steps) == 3
    assert brief.chinese_labels == ["树突状细胞", "辅助性T细胞", "B细胞", "抗体"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"image_type":',
        "```json\n{}\n```",
        json.dumps({**_chinese_brief_payload(), "answer": "额外问答"}, ensure_ascii=False),
        json.dumps(_chinese_brief_payload()).replace('"fast"', 'NaN'),
    ],
)
async def test_refiner_rejects_malformed_or_non_contract_json(content: str) -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(content)

    with pytest.raises(ScienceImageOrganizerError):
        await _organizer(client).refine("B细胞形成免疫记忆")


@pytest.mark.asyncio
async def test_refiner_maps_sdk_timeout_to_safe_service_error() -> None:
    client = AsyncMock()
    timeout = APITimeoutError(request=Request("POST", "https://example.org"))
    client.chat.completions.create.side_effect = timeout

    with pytest.raises(ScienceImageOrganizerError) as raised:
        await _organizer(client).refine("流感公共卫生科普")

    assert raised.value.__cause__ is timeout


@pytest.mark.asyncio
async def test_refiner_rejects_missing_client_without_model_call() -> None:
    organizer = ScienceImageOrganizer(
        Settings(_env_file=None, dashscope_api_key="test-key"), None
    )

    with pytest.raises(ScienceImageNotConfiguredError):
        await organizer.refine("B细胞形成免疫记忆")


@pytest.mark.asyncio
async def test_refiner_trims_prompt_before_applying_normalized_2000_limit() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_chinese_brief_payload())
    prompt = "免" * 2000

    await _organizer(client).refine(f"  {prompt}  ")

    call = client.chat.completions.create.await_args.kwargs
    assert call["messages"][-1]["content"] == prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["   ", "免" * 2001])
async def test_refiner_rejects_invalid_normalized_prompt_without_model_call(
    prompt: str,
) -> None:
    client = AsyncMock()

    with pytest.raises(ValueError):
        await _organizer(client).refine(prompt)

    client.chat.completions.create.assert_not_awaited()
