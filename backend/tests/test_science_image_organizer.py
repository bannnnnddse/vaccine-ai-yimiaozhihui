import json
from copy import deepcopy
from pathlib import Path
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
    ScienceImageScopeError,
)


def _response(payload: dict[str, object] | str) -> SimpleNamespace:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _organized_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "in_scope": True,
        "title": "B细胞免疫记忆",
        "summary": "抗原识别后部分B细胞分化并保留长期应答。",
        "facts": ["记忆B细胞再次接触抗原可快速应答。"],
        "visual_subject": "B细胞抗原识别至记忆细胞形成",
        "fallback_modules": [
            {
                "kind": "fact_cards",
                "title": "核心事实",
                "items": ["B细胞识别特定抗原"],
            },
            {
                "kind": "mechanism",
                "title": "形成过程",
                "items": ["活化", "增殖", "分化"],
            },
            {
                "kind": "medical_advice",
                "title": "科学边界",
                "items": ["示意图不代表个体诊疗结论"],
            },
        ],
        "data_candidates": [
            {
                "label": "记忆细胞比例",
                "value": 12,
                "unit": "%",
                "scope": "示例研究人群",
                "source": "https://example.org/study",
            }
        ],
    }
    payload.update(overrides)
    return payload


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
    verified_facts_path: Path | None = None,
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
        verified_facts_path=verified_facts_path,
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
    ("image_type", "prompt"),
    [
        ("science_poster", "社区流感防护的公共卫生科普"),
        ("graphical_abstract", "抗原递呈连接先天免疫与适应性免疫"),
        ("mechanism_diagram", "B细胞形成免疫记忆"),
    ],
)
async def test_organizer_accepts_science_scope_and_preserves_selected_image_type(
    image_type: str,
    prompt: str,
) -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_organized_payload())

    result = await _organizer(client).organize(image_type, prompt)

    assert result.image_type == image_type
    assert result.title == "B细胞免疫记忆"
    assert result.visual_subject
    assert len(result.fallback_modules) >= 3
    client.chat.completions.create.assert_awaited_once()
    call = client.chat.completions.create.await_args.kwargs
    assert call["model"] == "qwen3.8-flash"
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"] == {"enable_thinking": False}
    assert "is_vaccine_related" not in call["messages"][0]["content"]
    assert "chat answer" not in call["messages"][0]["content"].lower()


@pytest.mark.asyncio
async def test_organizer_rejects_clearly_unrelated_content() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _organized_payload(
            in_scope=False,
            title="",
            summary="",
            facts=[],
            visual_subject="",
            fallback_modules=[],
            data_candidates=[],
        )
    )

    with pytest.raises(ScienceImageScopeError):
        await _organizer(client).organize("science_poster", "写一个红烧肉菜谱")

    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"in_scope": true',
        "```json\n{}\n```",
        json.dumps({**_organized_payload(), "answer": "这是聊天回答"}, ensure_ascii=False),
    ],
)
async def test_organizer_rejects_malformed_or_non_contract_json(content: str) -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(content)

    with pytest.raises(ScienceImageOrganizerError):
        await _organizer(client).organize("mechanism_diagram", "B细胞形成免疫记忆")


@pytest.mark.asyncio
async def test_seed_fact_pack_keeps_model_numbers_candidate_and_non_renderable() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_organized_payload())

    result = await _organizer(client).organize(
        "science_poster", "疫苗免疫记忆科普"
    )

    assert result.data_candidates
    assert all(item.verification == "candidate" for item in result.data_candidates)
    assert all(not item.is_renderable for item in result.data_candidates)


@pytest.mark.asyncio
async def test_only_exact_normalized_fact_pack_match_becomes_verified(
    tmp_path: Path,
) -> None:
    facts_path = tmp_path / "verified.json"
    facts_path.write_text(
        json.dumps(
            [
                {
                    "label": " 记忆细胞比例 ",
                    "value": 12,
                    "unit": " % ",
                    "scope": "示例研究人群",
                    "source": "HTTPS://EXAMPLE.ORG/study",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = AsyncMock()
    payload = _organized_payload()
    payload["data_candidates"] = [
        {
            "label": "记忆细胞比例",
            "value": 12.0,
            "unit": "%",
            "scope": " 示例研究人群 ",
            "source": "https://example.org/study",
        },
        {
            "label": "记忆细胞比例",
            "value": 13,
            "unit": "%",
            "scope": "示例研究人群",
            "source": "https://example.org/study",
        },
    ]
    client.chat.completions.create.return_value = _response(payload)

    result = await _organizer(client, facts_path).organize(
        "science_poster", "疫苗免疫记忆科普"
    )

    assert result.data_candidates[0].verification == "verified"
    assert result.data_candidates[0].is_renderable is True
    assert result.data_candidates[1].verification == "candidate"
    assert result.data_candidates[1].is_renderable is False


@pytest.mark.asyncio
async def test_unit_matching_preserves_scientific_case_semantics(tmp_path: Path) -> None:
    facts_path = tmp_path / "verified.json"
    fact = {
        "label": "浓度",
        "value": 2,
        "unit": "mM",
        "scope": "体外实验",
        "source": "https://example.org/Study",
    }
    facts_path.write_text(json.dumps([fact], ensure_ascii=False), encoding="utf-8")
    client = AsyncMock()
    payload = _organized_payload(data_candidates=[{**fact, "unit": "mm"}])
    client.chat.completions.create.return_value = _response(payload)

    result = await _organizer(client, facts_path).organize(
        "graphical_abstract", "免疫细胞体外实验"
    )

    assert result.data_candidates[0].verification == "candidate"


@pytest.mark.asyncio
async def test_url_matching_preserves_path_and_query_case(tmp_path: Path) -> None:
    facts_path = tmp_path / "verified.json"
    fact = {
        "label": "发生率",
        "value": 2,
        "unit": "%",
        "scope": "队列",
        "source": "HTTPS://EXAMPLE.ORG/Study?Group=A",
    }
    facts_path.write_text(json.dumps([fact], ensure_ascii=False), encoding="utf-8")
    client = AsyncMock()
    payload = _organized_payload(
        data_candidates=[
            {**fact, "source": "https://example.org/study?Group=A"},
            {**fact, "source": "https://example.org/Study?Group=a"},
        ]
    )
    client.chat.completions.create.return_value = _response(payload)

    result = await _organizer(client, facts_path).organize(
        "science_poster", "队列公共卫生研究"
    )

    assert [item.verification for item in result.data_candidates] == [
        "candidate",
        "candidate",
    ]


@pytest.mark.asyncio
async def test_malformed_candidate_url_maps_to_safe_organizer_error() -> None:
    client = AsyncMock()
    payload = _organized_payload()
    payload["data_candidates"] = [
        {
            "label": "发生率",
            "value": 2,
            "unit": "%",
            "scope": "研究队列",
            "source": "https://[bad",
        }
    ]
    client.chat.completions.create.return_value = _response(payload)

    with pytest.raises(ScienceImageOrganizerError) as raised:
        await _organizer(client).organize("science_poster", "公共卫生研究")

    assert isinstance(raised.value.__cause__, ValueError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        ("label", "住院率"),
        ("value", 3),
        ("unit", "‰"),
        ("scope", "另一队列"),
        ("source", "https://example.org/Other"),
    ],
)
async def test_each_verified_fact_field_must_match(
    tmp_path: Path,
    field: str,
    different_value: object,
) -> None:
    facts_path = tmp_path / "verified.json"
    fact: dict[str, object] = {
        "label": "发生率",
        "value": 2,
        "unit": "%",
        "scope": "研究队列",
        "source": "https://example.org/Study",
    }
    facts_path.write_text(json.dumps([fact], ensure_ascii=False), encoding="utf-8")
    candidate = {**fact, field: different_value}
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(
        _organized_payload(data_candidates=[candidate])
    )

    result = await _organizer(client, facts_path).organize(
        "science_poster", "公共卫生研究"
    )

    assert result.data_candidates[0].verification == "candidate"


@pytest.mark.parametrize("field", ["label", "unit", "scope", "source"])
def test_verified_fact_pack_requires_nonblank_identity_fields(
    tmp_path: Path,
    field: str,
) -> None:
    fact = {
        "label": "发生率",
        "value": 2,
        "unit": "%",
        "scope": "研究队列",
        "source": "https://example.org/Study",
    }
    fact[field] = "   "
    facts_path = tmp_path / "verified.json"
    facts_path.write_text(json.dumps([fact], ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ScienceImageOrganizerError, match="fact pack"):
        _organizer(AsyncMock(), facts_path)


@pytest.mark.asyncio
async def test_organizer_maps_sdk_timeout_to_safe_service_error() -> None:
    client = AsyncMock()
    timeout = APITimeoutError(request=Request("POST", "https://example.org"))
    client.chat.completions.create.side_effect = timeout

    with pytest.raises(ScienceImageOrganizerError) as raised:
        await _organizer(client).organize("science_poster", "流感公共卫生科普")

    assert raised.value.__cause__ is timeout


@pytest.mark.asyncio
async def test_organizer_rejects_missing_client_without_model_call() -> None:
    organizer = ScienceImageOrganizer(Settings(dashscope_api_key="test-key"), None)

    with pytest.raises(ScienceImageNotConfiguredError):
        await organizer.organize("mechanism_diagram", "B细胞形成免疫记忆")


@pytest.mark.asyncio
async def test_organizer_trims_prompt_before_applying_normalized_2000_limit() -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = _response(_organized_payload())
    prompt = "免" * 2000

    await _organizer(client).organize("mechanism_diagram", f"  {prompt}  ")

    call = client.chat.completions.create.await_args.kwargs
    assert call["messages"][-1]["content"].endswith(prompt)
    assert not call["messages"][-1]["content"].endswith(" ")


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["   ", "免" * 2001])
async def test_organizer_rejects_invalid_normalized_prompt_without_model_call(
    prompt: str,
) -> None:
    client = AsyncMock()

    with pytest.raises(ValueError):
        await _organizer(client).organize("science_poster", prompt)

    client.chat.completions.create.assert_not_awaited()


# ── Length compression ──────────────────────────────────────────────


def test_compress_dossier_truncates_overlong_title() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    resp = _OrganizerResponse(
        in_scope=True,
        title="HPV疫苗预防宫颈癌的作用机制与公共卫生影响分析",
        summary="短摘要",
        facts=["事实一"],
        visual_subject="疫苗机制",
        fallback_modules=[
            FallbackModule(kind="fact_cards", title="事实", items=["项目"]),
            FallbackModule(kind="mechanism", title="机制", items=["步骤"]),
            FallbackModule(kind="medical_advice", title="建议", items=["咨询"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    assert len(compressed.title) <= 10


def test_compress_dossier_truncates_overlong_summary() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    # 60+ chars — well above the 32-char limit
    long_summary = (
        "这是一段非常长的摘要文本用于测试压缩功能，"
        "它包含了超过三十二字的中文内容以确保截断逻辑能够被正确触发。"
    )
    assert len(long_summary) > 32, "test fixture must exceed summary limit"

    resp = _OrganizerResponse(
        in_scope=True,
        title="短标题",
        summary=long_summary,
        facts=["事实一"],
        visual_subject="疫苗机制",
        fallback_modules=[
            FallbackModule(kind="fact_cards", title="事实", items=["项目"]),
            FallbackModule(kind="mechanism", title="机制", items=["步骤"]),
            FallbackModule(kind="medical_advice", title="建议", items=["咨询"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    assert len(compressed.summary) <= 32
    assert len(compressed.summary) < len(long_summary)


def test_compress_dossier_prefers_sentence_boundary() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    # First "。" lands at ~char 23 — within the 10-char backtrack window from 32.
    long_summary = (
        "mRNA疫苗通过脂质纳米颗粒递送编码序列进入细胞质。"
        "这段额外文字会让总长度超过三十二字以确保截断一定触发。"
    )
    assert len(long_summary) > 32, "test fixture must exceed summary limit"

    resp = _OrganizerResponse(
        in_scope=True,
        title="mRNA疫苗机制",
        summary=long_summary,
        facts=["脂质纳米颗粒递送"],
        visual_subject="疫苗机制图",
        fallback_modules=[
            FallbackModule(kind="fact_cards", title="事实", items=["项目"]),
            FallbackModule(kind="mechanism", title="机制", items=["步骤"]),
            FallbackModule(kind="medical_advice", title="建议", items=["咨询"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    # Should cut at the first "。" which is within the backtrack window
    assert compressed.summary.endswith("。")
    assert len(compressed.summary) <= 32


def test_compress_dossier_truncates_module_items() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    resp = _OrganizerResponse(
        in_scope=True,
        title="短标题",
        summary="短摘要",
        facts=["事实"],
        visual_subject="机制",
        fallback_modules=[
            FallbackModule(
                kind="fact_cards",
                title="关键事实卡片模块超长标题",
                items=["项目A内容" * 20, "短项目"],
            ),
            FallbackModule(kind="mechanism", title="机制", items=["步骤"]),
            FallbackModule(kind="medical_advice", title="建议", items=["咨询"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    assert len(compressed.fallback_modules[0].title) <= 10
    assert len(compressed.fallback_modules[0].items[0]) <= 12
    assert compressed.fallback_modules[0].items[1] == "短项目"


def test_compress_dossier_does_not_modify_short_text() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    resp = _OrganizerResponse(
        in_scope=True,
        title="HPV疫苗预防",
        summary="mRNA疫苗的作用机制",
        facts=["脂质纳米颗粒递送"],
        visual_subject="疫苗机制图",
        fallback_modules=[
            FallbackModule(kind="fact_cards", title="事实", items=["项目A"]),
            FallbackModule(kind="mechanism", title="机制", items=["步骤"]),
            FallbackModule(kind="medical_advice", title="建议", items=["咨询"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    # All fields are within limits — should be unchanged
    assert compressed.title == "HPV疫苗预防"
    assert compressed.summary == "mRNA疫苗的作用机制"
    assert compressed.visual_subject == "疫苗机制图"
    assert compressed.facts == ["脂质纳米颗粒递送"]


def test_compress_dossier_preserves_fallback_module_count() -> None:
    from app.services.science_image_organizer import (
        FallbackModule,
        _compress_dossier,
        _OrganizerResponse,
    )

    resp = _OrganizerResponse(
        in_scope=True,
        title="短标题",
        summary="短摘要",
        facts=["事实"],
        visual_subject="机制",
        fallback_modules=[
            FallbackModule(kind="fact_cards", title="事实标题", items=["项"]),
            FallbackModule(kind="mechanism", title="机制标题", items=["步"]),
            FallbackModule(kind="medical_advice", title="建议标题", items=["咨"]),
            FallbackModule(kind="symptom_cards", title="症状标题", items=["症"]),
            FallbackModule(kind="timeline", title="时间标题", items=["时"]),
        ],
        data_candidates=[],
    )
    compressed = _compress_dossier(resp)
    assert len(compressed.fallback_modules) == 5
