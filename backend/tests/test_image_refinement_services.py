import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import BadRequestError
from PIL import Image

from app.core.config import Settings
from app.schemas.image_pipeline import (
    BlindTextAudit,
    NormalizedBBox,
    VisualCriticResult,
    normalize_critic,
)
from app.services.edit_instruction_rewriter import EditInstructionRewriter
from app.services.edit_scope_guard_service import EditScopeGuardService
from app.services.visual_critic_service import VisualCriticService
from app.services.wan_image_generator import normalized_bbox_to_pixels


def _critic_payload(issue_type: str = "layout") -> dict[str, object]:
    return {
        "overall_status": "needs_revision",
        "summary": "发现一个问题",
        "recommended_action": "auto_fix",
        "auto_fixable": True,
        "human_input_required": False,
        "audit_checks": {
            "visual_integrity": {
                "status": "pass",
                "evidence": "对象边缘完整。",
                "confidence": 0.93,
            },
            "text_legibility": {"status": "pass", "evidence": "文字可辨。", "confidence": 0.93},
            "layout_hierarchy": {
                "status": "pass",
                "evidence": "版面层级清楚。",
                "confidence": 0.93,
            },
            "brief_alignment": {"status": "pass", "evidence": "主题元素可见。", "confidence": 0.93},
            "causal_step_coverage": {
                "status": "pass",
                "evidence": "流程关系可见。",
                "confidence": 0.93,
            },
            "scientific_expression_risk": {
                "status": "pass",
                "evidence": "未见潜在风险。",
                "confidence": 0.93,
            },
        },
        "issues": [
            {
                "issue_type": issue_type,
                "severity": "medium",
                "description": "表达可能不清楚",
                "bbox": [0.1, 0.2, 0.5, 0.6],
                **(
                    {"observed_text": "树抗细胞", "replacement_text": "树突状细胞"}
                    if issue_type == "text_error"
                    else {}
                ),
                "confidence": 0.93,
                "suggested_fix": "调整框内表达",
                "auto_fixable": True,
                "human_input_required": False,
            }
        ],
    }


def _blind_text_payload() -> dict[str, object]:
    return {
        "status": "clear",
        "summary": "检测到清晰文字。",
        "text_blocks": [{"text": "树突状细胞", "bbox": [0.1, 0.2, 0.5, 0.6], "confidence": 0.95}],
    }


@pytest.mark.asyncio
async def test_visual_critic_uses_pydantic_json_schema_and_validates_result(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    Image.new("RGB", (20, 30), "white").save(image)
    client = AsyncMock()
    client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(_blind_text_payload(), ensure_ascii=False)
                    )
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(_critic_payload(), ensure_ascii=False)
                    )
                )
            ]
        ),
    ]
    settings = Settings(_env_file=None, dashscope_api_key="test-key")
    result = await VisualCriticService(settings, client).review(
        image, user_prompt="测试", review_label="首次"
    )
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert kwargs["response_format"]["json_schema"]["schema"]["title"] == "VisualCriticResult"
    blind_call = client.chat.completions.create.await_args_list[0].kwargs
    blind_content = blind_call["messages"][1]["content"]
    assert len(blind_content) == 1
    assert blind_content[0]["type"] == "image_url"
    assert result.recommended_action == "auto_fix"


@pytest.mark.asyncio
async def test_visual_critic_sends_cell_ip_references_for_identity_review(tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    reference = tmp_path / "reference.png"
    Image.new("RGB", (20, 30), "white").save(image)
    Image.new("RGB", (20, 30), "red").save(reference)
    client = AsyncMock()
    client.chat.completions.create.side_effect = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(_blind_text_payload(), ensure_ascii=False)
                    )
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            _critic_payload("ip_identity_mismatch"), ensure_ascii=False
                        )
                    )
                )
            ]
        ),
    ]
    result = await VisualCriticService(
        Settings(_env_file=None, dashscope_api_key="test-key"), client
    ).review(
        image,
        user_prompt="展示 B 细胞",
        review_label="首次",
        cell_ip_context="固定角色：B 细胞：蓝色圆体。",
        cell_ip_references=[reference.read_bytes()],
        cell_ip_reference_names=["role-sheet:b_cell"],
    )

    content = client.chat.completions.create.await_args.kwargs["messages"][1]["content"]
    assert len(content) == 3
    assert "role-sheet:b_cell" in content[-1]["text"]
    assert result.issues[0].issue_type == "ip_identity_mismatch"


@pytest.mark.asyncio
async def test_visual_critic_falls_back_to_json_object_with_json_prompt(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    Image.new("RGB", (20, 30), "white").save(image)
    request = httpx.Request("POST", "https://example.test/chat/completions")
    unsupported = BadRequestError(
        "response_format json_schema is unsupported",
        response=httpx.Response(400, request=request),
        body={"message": "response_format json_schema is unsupported"},
    )
    success = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(_critic_payload(), ensure_ascii=False))
            )
        ]
    )
    client = AsyncMock()
    blind_success = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(_blind_text_payload(), ensure_ascii=False)
                )
            )
        ]
    )
    client.chat.completions.create.side_effect = [blind_success, unsupported, success]
    settings = Settings(_env_file=None, dashscope_api_key="test-key")

    result = await VisualCriticService(settings, client).review(
        image, user_prompt="测试", review_label="首次"
    )

    assert result.recommended_action == "auto_fix"
    assert client.chat.completions.create.await_count == 3
    fallback = client.chat.completions.create.await_args_list[2].kwargs
    assert fallback["response_format"] == {"type": "json_object"}
    assert "JSON" in fallback["messages"][0]["content"]


@pytest.mark.asyncio
async def test_visual_critic_continues_when_auxiliary_blind_text_audit_fails(
    tmp_path: Path,
) -> None:
    image = tmp_path / "image.png"
    Image.new("RGB", (20, 30), "white").save(image)
    client = AsyncMock()
    client.chat.completions.create.side_effect = [
        ValueError("blind text response malformed"),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(_critic_payload(), ensure_ascii=False)
                    )
                )
            ]
        ),
    ]

    result = await VisualCriticService(
        Settings(_env_file=None, dashscope_api_key="test-key"), client
    ).review(image, user_prompt="测试", review_label="首次")

    assert result.blind_text_audit is not None
    assert result.blind_text_audit.status == "unavailable"
    assert client.chat.completions.create.await_count == 2


def test_scientific_expression_is_only_a_human_review_risk() -> None:
    result = normalize_critic(
        VisualCriticResult.model_validate(_critic_payload("scientific_expression"))
    )
    assert result.overall_status == "needs_human_review"
    assert result.human_input_required is True
    assert result.auto_fixable is False
    assert result.issues[0].human_input_required is True
    assert "潜在科学表达风险" in result.issues[0].description


def test_unreadable_blind_text_forces_automatic_text_regeneration() -> None:
    result = VisualCriticResult.model_validate(_critic_payload()).model_copy(
        update={
            "blind_text_audit": BlindTextAudit(
                status="unreadable",
                summary="标题区域存在无法唯一辨认的字符。",
                text_blocks=[],
            )
        }
    )

    normalized = normalize_critic(result)

    assert normalized.overall_status == "needs_revision"
    assert normalized.recommended_action == "auto_fix"
    assert normalized.human_input_required is False
    assert normalized.issues[-1].issue_type == "text_regeneration"
    assert normalized.issues[-1].bbox == NormalizedBBox([0.0, 0.0, 1.0, 1.0])


def test_auto_text_regeneration_rewrites_the_whole_text_layer() -> None:
    from app.schemas.image_pipeline import VisualIssue

    instruction = EditInstructionRewriter().rewrite_auto(
        [
            VisualIssue(
                issue_type="text_regeneration",
                severity="high",
                description="发现乱码。",
                bbox=NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
                confidence=1.0,
                suggested_fix="重新生成文字。",
                auto_fixable=True,
                human_input_required=False,
            )
        ]
    )

    assert "所有乱码、错字、缺字" in instruction
    assert "审核契约" in instruction


@pytest.mark.asyncio
async def test_scope_guard_only_scores_pixels_outside_bbox(tmp_path: Path) -> None:
    original = tmp_path / "original.png"
    inside = tmp_path / "inside.png"
    outside = tmp_path / "outside.png"
    Image.new("RGB", (100, 100), "white").save(original)
    inside_image = Image.new("RGB", (100, 100), "white")
    for x in range(20, 60):
        for y in range(20, 60):
            inside_image.putpixel((x, y), (0, 0, 0))
    inside_image.save(inside)
    Image.new("RGB", (100, 100), "black").save(outside)
    guard = EditScopeGuardService(0.05)
    bbox = NormalizedBBox([0.2, 0.2, 0.6, 0.6])
    assert (await guard.check(original, inside, bbox)).passed is True
    outside_result = await guard.check(original, outside, bbox)
    assert outside_result.passed is False
    assert outside_result.outside_change_regions
    unchanged = await guard.check(original, original, bbox)
    assert unchanged.passed is False
    assert unchanged.insufficient_change_inside_bbox is True


def test_human_delete_instruction_requires_removal_and_background_fill() -> None:
    instruction = EditInstructionRewriter().rewrite_human("删掉标题")
    assert "完整移除" in instruction
    assert "背景自然填充" in instruction


def test_exact_copy_edits_are_classified_without_character_references() -> None:
    rewriter = EditInstructionRewriter()
    assert rewriter.is_text_edit_request("把标题改短") is True
    assert rewriter.is_text_edit_request("改为“流程图”") is True
    assert rewriter.is_text_edit_request("把右手改为叉腰") is False
    assert rewriter.exact_text_replacement("改为“流程图”") == "流程图"


def test_normalized_bbox_converts_to_original_absolute_pixels() -> None:
    assert normalized_bbox_to_pixels(NormalizedBBox([0.1, 0.2, 0.5, 0.75]), 1000, 2000) == [
        100,
        400,
        500,
        1500,
    ]
