from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from PIL import Image

from app.core.config import Settings
from app.schemas.image_pipeline import (
    BlindTextAudit,
    EditScopeGuardResult,
    ImageEditRequest,
    ImageRestoreRequest,
    NormalizedBBox,
    VisualAuditCheck,
    VisualAuditChecks,
    VisualCriticResult,
    VisualIssue,
    normalize_critic,
)
from app.schemas.science_figure import ChineseFigureBrief, CoreCausalStep
from app.services.cell_ip_assets import CellIpGenerationProfile
from app.services.edit_instruction_rewriter import EditInstructionRewriter
from app.services.science_image_job_manager import JobConflictError, ScienceImageJobManager
from app.services.science_image_organizer import ScienceImageOrganizer
from app.services.wan_image_generator import WanImageGenerator


def _brief(route: str = "fast") -> ChineseFigureBrief:
    return ChineseFigureBrief(
        image_type="mechanism_diagram",
        generation_route=route,  # type: ignore[arg-type]
        optimized_chinese_prompt=(
            "制作一张9:16竖版中文免疫机制图解，清楚展示抗原呈递如何促进免疫细胞识别，"
            "并以简洁标签说明免疫记忆形成过程。"
        ),
        chinese_labels=["抗原呈递", "免疫记忆"],
        scientific_claims=["抗原呈递参与适应性免疫应答。"],
        core_causal_steps=[CoreCausalStep(primary_relation="抗原呈递促进免疫细胞识别。")],
        route_reason="测试路由。",
    )


def _critic(status: str = "pass", *, confidence: float = 0.95) -> VisualCriticResult:
    audit_checks = VisualAuditChecks(
        visual_integrity=VisualAuditCheck(
            status="pass", evidence="对象边缘完整。", confidence=confidence
        ),
        text_legibility=VisualAuditCheck(
            status="pass", evidence="文字可辨。", confidence=confidence
        ),
        layout_hierarchy=VisualAuditCheck(
            status="pass", evidence="层级清楚。", confidence=confidence
        ),
        brief_alignment=VisualAuditCheck(
            status="pass", evidence="主题元素可见。", confidence=confidence
        ),
        causal_step_coverage=VisualAuditCheck(
            status="pass", evidence="流程关系可见。", confidence=confidence
        ),
        scientific_expression_risk=VisualAuditCheck(
            status="pass", evidence="未见潜在风险。", confidence=confidence
        ),
    )
    if status == "pass":
        return VisualCriticResult(
            overall_status="pass",
            summary="画面通过审核。",
            recommended_action="accept",
            auto_fixable=False,
            human_input_required=False,
            audit_checks=audit_checks,
            issues=[],
        )
    if status == "auto":
        return VisualCriticResult(
            overall_status="needs_revision",
            summary="局部标签需要修正。",
            recommended_action="auto_fix",
            auto_fixable=True,
            human_input_required=False,
            audit_checks=audit_checks,
            issues=[
                VisualIssue(
                    issue_type="text_error",
                    severity="medium",
                    description="标签有乱码。",
                    bbox=NormalizedBBox([0.1, 0.1, 0.4, 0.3]),
                    observed_text="树抗细胞",
                    replacement_text="树突状细胞",
                    confidence=confidence,
                    suggested_fix="改为清晰简体中文",
                    auto_fixable=True,
                    human_input_required=False,
                )
            ],
        )
    return VisualCriticResult(
        overall_status="needs_human_review",
        summary="需要人工确认。",
        recommended_action="request_human_feedback",
        auto_fixable=False,
        human_input_required=True,
        audit_checks=audit_checks,
        issues=[],
    )


def _guard(passed: bool) -> EditScopeGuardResult:
    return EditScopeGuardResult(
        passed=passed,
        outside_change_score=0.01 if passed else 0.2,
        threshold=0.05,
        changed_outside_bbox=not passed,
        inside_change_score=0.08,
        minimum_inside_change=0.01,
        insufficient_change_inside_bbox=False,
        notes="通过" if passed else "框外变化过大",
    )


def _auto_issue_with_human_issue() -> VisualCriticResult:
    result = _critic("auto")
    return result.model_copy(
        update={
            "overall_status": "needs_human_review",
            "recommended_action": "request_human_feedback",
            "auto_fixable": False,
            "human_input_required": True,
            "issues": [
                *result.issues,
                VisualIssue(
                    issue_type="ip_identity_mismatch",
                    severity="medium",
                    description="固定角色外形与参考不一致。",
                    bbox=None,
                    confidence=0.9,
                    suggested_fix="请人工核验固定角色。",
                    auto_fixable=False,
                    human_input_required=True,
                ),
            ],
        }
    )


@pytest.mark.asyncio
async def test_restore_previous_keeps_both_versions_and_switches_presented_image(
    dependencies,
) -> None:
    manager, *_ = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    initial = await manager.get(created.job_id)
    assert initial is not None and initial.image_id is not None

    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=initial.image_id,
            bbox=NormalizedBBox([0.1, 0.1, 0.4, 0.4]),
            user_edit_request="把框内标签改清楚",
        ),
    )
    await _wait_idle(manager, created.job_id)
    revised = await manager.get(created.job_id)
    assert revised is not None and revised.image_id is not None
    assert revised.previous_image_id == initial.image_id
    assert revised.previous_image_url == initial.image_url

    restored = await manager.restore_previous(
        created.job_id,
        ImageRestoreRequest(target_image_id=revised.image_id),
    )
    assert restored.image_id == initial.image_id
    assert restored.image_url == initial.image_url
    assert restored.previous_image_id == revised.image_id


@pytest.fixture
def dependencies(tmp_path: Path):
    settings = Settings(_env_file=None, dashscope_api_key="test-key", generated_image_dir=tmp_path)
    organizer = AsyncMock(spec=ScienceImageOrganizer)
    organizer.refine.return_value = _brief()
    wan = AsyncMock(spec=WanImageGenerator)

    async def generate(**kwargs):
        Image.new("RGB", (90, 160), "white").save(kwargs["output_path"])
        return type("Result", (), {"final_path": kwargs["output_path"]})()

    async def edit(**kwargs):
        with Image.open(kwargs["source_path"]) as source:
            Image.new("RGB", source.size, "#eeeeee").save(kwargs["output_path"])
        return type("Result", (), {"final_path": kwargs["output_path"]})()

    wan.generate.side_effect = generate
    wan.edit.side_effect = edit
    critic = AsyncMock()
    critic.review.return_value = _critic()
    guard = AsyncMock()
    guard.check.return_value = _guard(True)
    manager = ScienceImageJobManager(
        settings, organizer, wan, critic, EditInstructionRewriter(), guard
    )
    return manager, organizer, wan, critic, guard


async def _wait_idle(manager: ScienceImageJobManager, job_id: str) -> None:
    for _ in range(200):
        record = manager._jobs[job_id]
        if record._task is not None and record._task.done():
            await asyncio.sleep(0)
            return
        await asyncio.sleep(0.005)
    raise AssertionError("image task did not finish")


@pytest.mark.asyncio
async def test_initial_generation_uses_wan_and_persists_structured_audit(
    dependencies,
) -> None:
    manager, organizer, wan, critic, _ = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)
    assert status is not None
    assert status.stage == "completed"
    assert status.generation_route == "fast"
    assert status.image_id == f"{created.job_id}-v0"
    assert [event.stage for event in status.trace_events] == [
        "understanding",
        "prompt_rewrite",
        "generation",
        "visual_critic",
        "completed",
    ]
    assert all(event.status != "running" for event in status.trace_events)
    wan.generate.assert_awaited_once()
    critic.review.assert_awaited_once()
    audit = json.loads(manager._metadata_path(created.job_id).read_text("utf-8"))
    assert audit["critic_result"]["overall_status"] == "pass"
    assert audit["cell_ip_enabled"] is False
    assert audit["aspect_ratio"] == "9:16"
    assert "test-key" not in json.dumps(audit)


@pytest.mark.asyncio
async def test_image_is_not_exposed_until_automatic_visual_review_settles(dependencies) -> None:
    manager, _, _, critic, _ = dependencies
    review_started = asyncio.Event()
    release_review = asyncio.Event()

    async def delayed_review(*_args, **_kwargs):
        review_started.set()
        await release_review.wait()
        return _critic()

    critic.review.side_effect = delayed_review
    created = await manager.create("解释免疫记忆")
    await asyncio.wait_for(review_started.wait(), timeout=1)
    in_review = await manager.get(created.job_id)

    assert in_review is not None
    assert in_review.stage == "critic_review_1"
    assert in_review.image_url is None
    assert in_review.image_id is None

    release_review.set()
    await _wait_idle(manager, created.job_id)
    completed = await manager.get(created.job_id)
    assert completed is not None
    assert completed.stage == "completed"
    assert completed.image_url is not None
    assert completed.image_id == f"{created.job_id}-v0"


@pytest.mark.asyncio
async def test_cell_ip_profile_reaches_critic_edits_and_audit(dependencies) -> None:
    manager, _, wan, critic, _ = dependencies
    manager._settings.cell_ip_enabled = True
    profile = CellIpGenerationProfile(
        visual_profile="cell_ip_scientific",
        role_ids=("b_cell", "antigen"),
        role_names=("B 细胞", "抗原"),
        role_specs=("B 细胞：蓝色圆体", "抗原：紫色圆刺团"),
        unmatched_cell_terms=("宫颈上皮细胞",),
        aspect_ratio="16:9",
        composition="causal_diagram",
        max_causal_steps=4,
        allow_title=True,
        style_instruction="使用固定角色但保留科学结构。",
        composition_instruction="完整保留核心因果链和箭头方向。",
        prohibitions=("3D",),
        reference_names=("role-sheet:b_cell+antigen",),
        references=(b"board",),
    )

    async def generate(**kwargs):
        Image.new("RGB", (160, 90), "white").save(kwargs["output_path"])
        return type(
            "Result",
            (),
            {"final_path": kwargs["output_path"], "cell_ip_profile": profile},
        )()

    wan.generate.side_effect = generate
    created = await manager.create("B细胞识别抗原")
    await _wait_idle(manager, created.job_id)

    audit = json.loads(manager._metadata_path(created.job_id).read_text("utf-8"))
    assert audit["cell_ip_enabled"] is True
    assert audit["cell_ip_role_ids"] == ["b_cell", "antigen"]
    assert audit["cell_ip_unmatched_cell_terms"] == ["宫颈上皮细胞"]
    assert audit["aspect_ratio"] == "16:9"
    assert audit["reference_assets"] == ["role-sheet:b_cell+antigen"]
    assert "细胞 IP skill" in critic.review.await_args.kwargs["cell_ip_context"]
    assert critic.review.await_args.kwargs["cell_ip_references"] == [b"board"]
    assert critic.review.await_args.kwargs["cell_ip_reference_names"] == (
        "role-sheet:b_cell+antigen",
    )


@pytest.mark.asyncio
async def test_prompt_rewrite_failure_ends_running_trace_without_fake_fallback(
    dependencies,
) -> None:
    manager, organizer, wan, _, _ = dependencies
    organizer.refine.side_effect = RuntimeError("rewrite unavailable")
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)

    status = await manager.get(created.job_id)

    assert status is not None and status.stage == "failed"
    assert status.trace_events[-1].title == "生成描述优化失败"
    assert status.trace_events[-1].status == "warning"
    wan.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_revision_guard_outside_change_adopts_revision_with_human_review_note(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    critic.review.side_effect = [_critic("auto"), _critic()]
    guard.check.return_value = _guard(False)
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)
    assert status is not None
    assert status.stage == "awaiting_human_feedback"
    assert status.image_id == f"{created.job_id}-v1"
    assert status.candidate_image_url is None
    assert status.auto_revision_count == 1
    assert status.critic_result is not None
    assert status.critic_result.overall_status == "needs_human_review"
    assert any(
        issue.human_input_required and "框外" in issue.description
        for issue in status.critic_result.issues
    )
    assert [event.stage for event in status.trace_events] == [
        "understanding",
        "prompt_rewrite",
        "generation",
        "visual_critic",
        "auto_revision",
        "scope_guard",
        "final_critic",
        "human_feedback",
    ]
    assert status.trace_events[-3].status == "warning"
    wan.edit.assert_awaited_once()
    guard.check.assert_awaited_once()
    assert critic.review.await_count == 2
    assert "框外" in critic.review.await_args_list[-1].kwargs["collateral_change_note"]


@pytest.mark.asyncio
async def test_auto_repair_runs_even_when_a_separate_issue_needs_human_review(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    critic.review.side_effect = [_auto_issue_with_human_issue(), _critic()]
    guard.check.return_value = _guard(True)

    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)

    assert status is not None
    assert status.stage == "completed"
    assert status.auto_revision_count == 1
    wan.edit.assert_awaited_once()
    assert critic.review.await_count == 2


@pytest.mark.asyncio
async def test_auto_revision_guard_passes_then_runs_one_final_critic(dependencies) -> None:
    manager, _, wan, critic, guard = dependencies
    manager._settings.image_auto_revision_max = 1
    critic.review.side_effect = [_critic("auto"), _critic("auto")]
    guard.check.return_value = _guard(True)
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)
    assert status is not None
    assert status.stage == "awaiting_human_feedback"
    assert status.image_id == f"{created.job_id}-v1"
    assert status.candidate_image_url is None
    assert status.auto_revision_count == 1
    wan.edit.assert_awaited_once()
    assert critic.review.await_count == 2
    assert [event.stage for event in status.trace_events][-4:] == [
        "auto_revision",
        "scope_guard",
        "final_critic",
        "human_feedback",
    ]


@pytest.mark.asyncio
async def test_unreadable_text_uses_full_text_layer_regeneration_before_human_queue(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    unreadable = normalize_critic(
        _critic().model_copy(
            update={
                "blind_text_audit": BlindTextAudit(
                    status="unreadable",
                    summary="标题文字无法辨认。",
                    text_blocks=[],
                )
            }
        )
    )
    critic.review.side_effect = [unreadable, _critic()]
    guard.check.return_value = _guard(True)

    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)

    assert status is not None
    assert status.stage == "completed"
    assert status.auto_revision_count == 1
    assert wan.edit.await_args.kwargs["bbox"] == NormalizedBBox([0.0, 0.0, 1.0, 1.0])
    assert "审核契约" in wan.edit.await_args.kwargs["instruction"]


@pytest.mark.asyncio
async def test_multiple_text_errors_are_repaired_one_bbox_at_a_time_before_result(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    first = _critic("auto")
    second_issue = VisualIssue(
        issue_type="text_error",
        severity="high",
        description="第二处标签将抗原呈递细胞误写为抗原呈除细胞。",
        bbox=NormalizedBBox([0.5, 0.55, 0.9, 0.72]),
        observed_text="抗原呈除细胞",
        replacement_text="抗原呈递细胞",
        confidence=0.97,
        suggested_fix="将“抗原呈除细胞”改为“抗原呈递细胞”。",
        auto_fixable=True,
        human_input_required=False,
    )
    multi = first.model_copy(update={"issues": [first.issues[0], second_issue]})
    critic.review.side_effect = [multi, _critic("auto"), _critic()]
    guard.check.return_value = _guard(True)

    created = await manager.create("解释抗原呈递")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)

    assert status is not None
    assert status.stage == "completed"
    assert status.auto_revision_count == 2
    assert status.image_id == f"{created.job_id}-v2"
    assert wan.edit.await_count == 2
    assert critic.review.await_count == 3
    instructions = "\n".join(call.kwargs["instruction"] for call in wan.edit.await_args_list)
    assert "树抗细胞”逐字替换为“树突状细胞" in instructions
    assert "抗原呈除细胞”逐字替换为“抗原呈递细胞" in instructions


@pytest.mark.asyncio
async def test_auto_revision_failure_keeps_trusted_image_for_human_edit(dependencies) -> None:
    manager, _, wan, critic, _ = dependencies
    critic.review.return_value = _critic("auto")
    wan.edit.side_effect = RuntimeError("provider edit failed")
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)

    status = await manager.get(created.job_id)

    assert status is not None
    assert status.stage == "awaiting_human_feedback"
    assert status.image_id == f"{created.job_id}-v0"
    assert status.trace_events[-2].title == "自动修改未被采纳"
    assert status.trace_events[-2].status == "warning"
    assert status.trace_events[-1].stage == "human_feedback"


@pytest.mark.asyncio
async def test_low_confidence_critic_bbox_never_triggers_auto_revision(dependencies) -> None:
    manager, _, wan, critic, _ = dependencies
    critic.review.return_value = _critic("auto", confidence=0.7)
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)
    assert status is not None and status.stage == "awaiting_human_feedback"
    wan.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_human_revision_guard_outside_change_keeps_trusted_image_and_candidate(
    dependencies,
) -> None:
    manager, _, _, critic, guard = dependencies
    critic.review.return_value = _critic("human")
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    guard.check.return_value = _guard(False)
    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.2, 0.2, 0.7, 0.6],
            user_edit_request="修改框内标题",
        ),
    )
    await _wait_idle(manager, created.job_id)
    status = await manager.get(created.job_id)
    assert status is not None
    assert status.stage == "awaiting_human_feedback"
    assert status.image_id == f"{created.job_id}-v0"
    assert status.candidate_image_url is not None
    assert status.critic_result is not None
    assert status.critic_result.overall_status == "needs_human_review"
    assert critic.review.await_count == 1
    assert [event.stage for event in status.trace_events] == [
        "understanding",
        "edit_rewrite",
        "auto_revision",
        "scope_guard",
        "human_feedback",
    ]
    assert status.trace_events[-2].title == "本次修改未通过范围检查"


@pytest.mark.asyncio
async def test_rejected_candidate_never_becomes_next_human_edit_source(dependencies) -> None:
    manager, _, wan, _, guard = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    guard.check.return_value = _guard(False)
    request = ImageEditRequest(
        target_image_id=f"{created.job_id}-v0",
        bbox=[0.2, 0.2, 0.7, 0.6],
        user_edit_request="修改框内标题",
    )
    await manager.edit(created.job_id, request)
    await _wait_idle(manager, created.job_id)

    observed_source_pixel: tuple[int, int, int] | None = None

    async def inspect_source(**kwargs):
        nonlocal observed_source_pixel
        with Image.open(kwargs["source_path"]) as source:
            observed_source_pixel = source.convert("RGB").getpixel((0, 0))
            Image.new("RGB", source.size, "#dddddd").save(kwargs["output_path"])
        return type("Result", (), {"final_path": kwargs["output_path"]})()

    wan.edit.side_effect = inspect_source
    guard.check.return_value = _guard(True)
    await manager.edit(created.job_id, request)
    await _wait_idle(manager, created.job_id)

    assert observed_source_pixel == (255, 255, 255)


@pytest.mark.asyncio
async def test_human_roi_edit_failure_keeps_trusted_image_and_returns_feedback(
    dependencies,
) -> None:
    manager, _, wan, _, _ = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    wan.edit.side_effect = RuntimeError("ROI provider unavailable")

    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.2, 0.2, 0.7, 0.6],
            user_edit_request="修改手势",
        ),
    )
    await _wait_idle(manager, created.job_id)

    status = await manager.get(created.job_id)
    assert status is not None
    assert status.stage == "awaiting_human_feedback"
    assert status.image_id == f"{created.job_id}-v0"
    assert status.candidate_image_url is None
    assert status.error is not None
    assert status.trace_events[-2].title == "局部编辑失败"


@pytest.mark.asyncio
async def test_human_revision_audits_bbox_and_instruction_and_critic_checks_intent(
    dependencies,
) -> None:
    manager, _, _, critic, _ = dependencies
    critic.review.side_effect = [_critic("human"), _critic()]
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    bbox = [0.1, 0.05, 0.9, 0.25]
    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=bbox,
            user_edit_request="把标题改为更短的中文表述",
        ),
    )
    await _wait_idle(manager, created.job_id)

    final_call = critic.review.await_args_list[-1].kwargs
    assert final_call["target_bbox"].root == bbox
    assert "更短的中文表述" in final_call["revision_instruction"]
    audit = json.loads(manager._metadata_path(created.job_id).read_text("utf-8"))
    assert audit["last_revision_bbox"] == bbox
    assert "更短的中文表述" in audit["last_edit_instruction"]


@pytest.mark.asyncio
async def test_exact_text_edit_does_not_send_cell_ip_reference_sheet(dependencies) -> None:
    manager, _, wan, _, guard = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    manager._jobs[created.job_id].cell_ip_profile = SimpleNamespace(
        critic_context="固定角色上下文",
        review_references=[],
        reference_names=(),
        role_ids=(),
        unmatched_cell_terms=(),
        aspect_ratio="16:9",
    )
    guard.check.return_value = _guard(True)

    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.15, 0.02, 0.85, 0.15],
            user_edit_request="改为“流程图”",
        ),
    )
    await _wait_idle(manager, created.job_id)

    assert wan.edit.await_args.kwargs["cell_ip_profile"] is None


@pytest.mark.asyncio
async def test_exact_text_candidate_is_not_promoted_when_blind_read_misses_target(
    dependencies,
) -> None:
    manager, _, _, critic, guard = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    guard.check.return_value = _guard(True)
    critic.review.return_value = _critic().model_copy(
        update={
            "blind_text_audit": BlindTextAudit(
                status="clear", summary="只读到旧标题。", text_blocks=[]
            )
        }
    )

    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.15, 0.02, 0.85, 0.15],
            user_edit_request="改为“流程图”",
        ),
    )
    await _wait_idle(manager, created.job_id)

    status = await manager.get(created.job_id)
    assert status is not None
    assert status.image_id == f"{created.job_id}-v0"
    assert status.candidate_image_url is not None
    assert status.critic_result is not None
    assert status.critic_result.overall_status == "needs_human_review"
    assert "未检测到用户指定的精确文字“流程图”" in status.critic_result.summary


@pytest.mark.asyncio
async def test_wrong_aspect_ratio_roi_output_never_overwrites_trusted_image(
    dependencies,
) -> None:
    manager, _, wan, _, _ = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)

    async def square_output(**kwargs):
        Image.new("RGB", (1000, 1000), "white").save(kwargs["output_path"])
        return type("Result", (), {"final_path": kwargs["output_path"]})()

    wan.edit.side_effect = square_output
    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.15, 0.02, 0.85, 0.15],
            user_edit_request="改为“流程图”",
        ),
    )
    await _wait_idle(manager, created.job_id)

    status = await manager.get(created.job_id)
    assert status is not None
    assert status.image_id == f"{created.job_id}-v0"
    assert status.candidate_image_url is None
    assert status.error is not None and "aspect ratio" in status.error


@pytest.mark.asyncio
async def test_human_revision_edits_expanded_roi_and_hard_composites_into_trusted_image(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)
    trusted_before = manager._jobs[created.job_id].trusted_path
    assert trusted_before is not None
    original = np.asarray(Image.open(trusted_before).convert("RGB")).copy()
    observed_roi_size: tuple[int, int] | None = None

    async def edit_roi(**kwargs):
        nonlocal observed_roi_size
        with Image.open(kwargs["source_path"]) as roi:
            observed_roi_size = roi.size
            Image.new("RGB", roi.size, "#202020").save(kwargs["output_path"])
        return type("Result", (), {"final_path": kwargs["output_path"]})()

    wan.edit.side_effect = edit_roi
    guard.check.return_value = _guard(True)
    critic.review.side_effect = [_critic()]
    bbox = NormalizedBBox([0.2, 0.2, 0.6, 0.6])
    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=bbox,
            user_edit_request="把框内角色右手改成叉腰",
        ),
    )
    await _wait_idle(manager, created.job_id)

    assert observed_roi_size is not None
    assert observed_roi_size[0] < original.shape[1]
    assert observed_roi_size[1] < original.shape[0]
    assert wan.edit.await_args.kwargs["bbox"] == NormalizedBBox([0.0, 0.0, 1.0, 1.0])
    status = await manager.get(created.job_id)
    assert status is not None and status.image_id == f"{created.job_id}-v1"
    trusted_after = manager._jobs[created.job_id].trusted_path
    assert trusted_after is not None
    final = np.asarray(Image.open(trusted_after).convert("RGB"))
    left, top, right, bottom = (18, 32, 54, 96)
    outside = np.ones(original.shape[:2], dtype=bool)
    outside[top:bottom, left:right] = False
    assert np.array_equal(original[outside], final[outside])
    assert critic.review.await_count == 2
    assert guard.check.await_count == 1
    debug_dir = Path(manager._settings.generated_image_dir) / "debug" / created.job_id
    assert (debug_dir / "v1-roi-before.png").is_file()
    assert (debug_dir / "v1-roi-after.png").is_file()
    assert (debug_dir / "v1-final-composite.png").is_file()
    debug_metadata = json.loads((debug_dir / "v1-roi.json").read_text("utf-8"))
    assert debug_metadata["original_bbox_normalized"] == bbox.root
    assert debug_metadata["expanded_bbox_pixels"] == [10, 19, 62, 109]


@pytest.mark.asyncio
async def test_human_title_deletion_uses_local_erase_when_background_is_uniform(
    dependencies,
) -> None:
    manager, _, wan, critic, guard = dependencies
    critic.review.side_effect = [_critic("human"), _critic("human")]
    guard.check.return_value = _guard(True)
    created = await manager.create("解释免疫记忆")
    await _wait_idle(manager, created.job_id)

    await manager.edit(
        created.job_id,
        ImageEditRequest(
            target_image_id=f"{created.job_id}-v0",
            bbox=[0.2, 0.02, 0.8, 0.18],
            user_edit_request="删掉标题",
        ),
    )
    await _wait_idle(manager, created.job_id)

    wan.edit.assert_not_awaited()
    status = await manager.get(created.job_id)
    assert status is not None
    assert any(event.title == "选中内容已删除" for event in status.trace_events)


@pytest.mark.asyncio
async def test_single_concurrency_is_preserved(dependencies) -> None:
    manager, organizer, *_ = dependencies
    gate = asyncio.Event()

    async def slow_refine(_prompt: str):
        await gate.wait()
        return _brief()

    organizer.refine.side_effect = slow_refine
    await manager.create("first")
    with pytest.raises(JobConflictError):
        await manager.create("second")
    gate.set()
