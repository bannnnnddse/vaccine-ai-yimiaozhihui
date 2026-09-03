"""Single-concurrency manager for the guarded fast image pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from collections.abc import Coroutine
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.schemas.image_pipeline import (
    EditScopeGuardResult,
    ImageEditRequest,
    ImageRestoreRequest,
    NormalizedBBox,
    RevisionOrigin,
    VisualCriticResult,
    VisualIssue,
)
from app.schemas.knowledge_image import (
    ImageJobCreated,
    ImageJobStage,
    ImageJobStatus,
    ImageProcessEvent,
    ImageProcessStage,
)
from app.schemas.science_figure import ChineseFigureBrief, GenerationRoute, ScienceImageType
from app.services.edit_instruction_rewriter import EditInstructionRewriter
from app.services.image_roi_editor import (
    composite_roi,
    crop_roi,
    prepare_roi,
    save_debug_metadata,
    validate_bbox_for_image,
)
from app.services.local_image_eraser import erase_on_uniform_background
from app.services.visual_complexity_contract import derive_visual_complexity_contract

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.cell_ip_assets import CellIpGenerationProfile
    from app.services.edit_scope_guard_service import EditScopeGuardService
    from app.services.science_image_organizer import ScienceImageOrganizer
    from app.services.visual_critic_service import VisualCriticService
    from app.services.wan_image_generator import WanImageGenerator

_JOB_ID_BYTES = 12
_TERMINAL_STAGES: frozenset[ImageJobStage] = frozenset({"completed", "failed", "cancelled"})
_GENERIC_FAILURE_MESSAGE = "生成失败，请稍后重试。"
logger = logging.getLogger(__name__)


class JobNotFoundError(RuntimeError):
    pass


class JobConflictError(RuntimeError):
    pass


class JobVersionConflictError(RuntimeError):
    pass


class InvalidJobStateError(RuntimeError):
    pass


class JobCancelledError(asyncio.CancelledError):
    pass


class _JobRecord:
    def __init__(
        self, job_id: str, prompt: str, *, brief: ChineseFigureBrief | None = None
    ) -> None:
        self.job_id = job_id
        self.prompt = prompt
        self.stage: ImageJobStage = "queued"
        self.brief = brief
        self.cell_ip_profile: CellIpGenerationProfile | None = None
        self.final_generation_prompt: str | None = None
        self.reference_names_sent: tuple[str, ...] = ()
        self.trusted_path: Path | None = None
        self.image_id: str | None = None
        self.candidate_path: Path | None = None
        self.previous_trusted_path: Path | None = None
        self.previous_image_id: str | None = None
        self.previous_revision_origin: RevisionOrigin | None = None
        self.previous_critic_result: VisualCriticResult | None = None
        self.critic_result: VisualCriticResult | None = None
        self.guard_result: EditScopeGuardResult | None = None
        self.auto_revision_count = 0
        self.revision_origin: RevisionOrigin | None = None
        self.last_revision_bbox: NormalizedBBox | None = None
        self.last_edit_instruction: str | None = None
        self.version = -1
        self.error: str | None = None
        self.created_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.trace_id = _new_job_id()
        self.trace_events: list[ImageProcessEvent] = []
        self.trace_history: list[dict[str, Any]] = []
        self.cancel_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def image_type(self) -> ScienceImageType | None:
        return self.brief.image_type if self.brief else None

    @property
    def generation_route(self) -> GenerationRoute | None:
        return self.brief.generation_route if self.brief else None

    @property
    def is_terminal(self) -> bool:
        return self.stage in _TERMINAL_STAGES

    @property
    def retryable(self) -> bool:
        return self.stage in {"failed", "cancelled"} and self.brief is not None

    @property
    def is_presentable(self) -> bool:
        """Only release an image after the automated review loop has settled."""
        return self.stage in {"completed", "awaiting_human_feedback"}

    def to_status(self) -> ImageJobStatus:
        image_url = _public_url(self.trusted_path) if self.is_presentable else None
        image_id = self.image_id if self.is_presentable else None
        candidate_url = _public_url(self.candidate_path) if self.is_presentable else None
        previous_image_url = (
            _public_url(self.previous_trusted_path) if self.is_presentable else None
        )
        return ImageJobStatus(
            job_id=self.job_id,
            image_type=self.image_type,
            generation_route=self.generation_route,
            stage=self.stage,
            image_url=image_url,
            image_id=image_id,
            candidate_image_url=candidate_url,
            previous_image_url=previous_image_url,
            previous_image_id=self.previous_image_id if self.is_presentable else None,
            error=_sanitise_error(self.error),
            retryable=self.retryable,
            critic_result=self.critic_result,
            guard_result=self.guard_result,
            auto_revision_count=self.auto_revision_count,
            revision_origin=self.revision_origin,
            previous_revision_origin=self.previous_revision_origin if self.is_presentable else None,
            trace_id=self.trace_id,
            trace_events=self.trace_events,
        )


class ScienceImageJobManager:
    """Own task state and enforce one guarded revision policy for every edit."""

    def __init__(
        self,
        settings: Settings,
        organizer: ScienceImageOrganizer,
        wan_generator: WanImageGenerator,
        critic: VisualCriticService,
        rewriter: EditInstructionRewriter,
        guard: EditScopeGuardService,
    ) -> None:
        self._settings = settings
        self._organizer = organizer
        self._wan_generator = wan_generator
        self._critic = critic
        self._rewriter = rewriter
        self._guard = guard
        self._jobs: dict[str, _JobRecord] = {}
        self._active_job_id: str | None = None
        self._lock = asyncio.Lock()

    async def create(self, prompt: str) -> ImageJobCreated:
        prompt = self._validate_prompt(prompt)
        async with self._lock:
            self._check_concurrency()
            record = _JobRecord(_new_job_id(), prompt)
            self._start_trace(
                record, "understanding", "正在理解图解需求", "确认主题、画面目标与科学表达边界。"
            )
            self._jobs[record.job_id] = record
            self._start(record, self._execute_initial(record))
        return self._created(record)

    async def get(self, job_id: str) -> ImageJobStatus | None:
        record = self._jobs.get(job_id)
        return record.to_status() if record else None

    async def edit(self, job_id: str, payload: ImageEditRequest) -> ImageJobCreated:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError
            self._check_concurrency()
            if record.stage not in {"completed", "awaiting_human_feedback"}:
                raise InvalidJobStateError
            if record.image_id != payload.target_image_id or record.trusted_path is None:
                raise JobVersionConflictError
            await asyncio.to_thread(
                validate_bbox_for_image,
                record.trusted_path,
                payload.bbox,
                min_side_px=self._settings.image_edit_min_bbox_side_px,
                min_area_px=self._settings.image_edit_min_bbox_area_px,
            )
            record.cancel_event = asyncio.Event()
            record.error = None
            record.candidate_path = None
            record.guard_result = None
            record.last_revision_bbox = None
            record.last_edit_instruction = None
            self._archive_trace(record)
            self._start_trace(
                record,
                "understanding",
                "正在理解你的修改要求",
                "结合框选区域确认本轮局部修改目标。",
            )
            self._start(record, self._execute_human_edit(record, payload))
        return self._created(record)

    async def accept(self, job_id: str) -> bool:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError
            self._check_concurrency()
            if record.stage not in {"completed", "awaiting_human_feedback"}:
                raise InvalidJobStateError
            if record.trusted_path is None:
                raise InvalidJobStateError
            self._unlink(record.candidate_path)
            record.candidate_path = None
            await self._finish(record, "completed")
        return True

    async def restore_previous(self, job_id: str, payload: ImageRestoreRequest) -> ImageJobStatus:
        """Restore the one prior accepted version without deleting the current file."""

        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError
            self._check_concurrency()
            if record.stage not in {"completed", "awaiting_human_feedback"}:
                raise InvalidJobStateError
            if record.image_id != payload.target_image_id:
                raise JobVersionConflictError
            if record.previous_trusted_path is None or record.previous_image_id is None:
                raise JobConflictError
            current_path = record.trusted_path
            current_image_id = record.image_id
            current_origin = record.revision_origin
            current_critic = record.critic_result
            record.trusted_path = record.previous_trusted_path
            record.image_id = record.previous_image_id
            record.revision_origin = record.previous_revision_origin
            record.critic_result = record.previous_critic_result
            record.guard_result = None
            record.previous_trusted_path = current_path
            record.previous_image_id = current_image_id
            record.previous_revision_origin = current_origin
            record.previous_critic_result = current_critic
            self._append_event(
                record,
                "warning",
                "已恢复上一版本",
                "当前显示已切回上一版；你仍可继续编辑或确认采用。",
                "warning",
            )
            await self._finish(record, "awaiting_human_feedback")
            return record.to_status()

    async def cancel(self, job_id: str) -> bool:
        record = self._jobs.get(job_id)
        if record is None or record.is_terminal:
            return False
        record.cancel_event.set()
        if record._task is not None and not record._task.done():
            record._task.cancel()
        else:
            await self._finish(record, "cancelled")
        return True

    async def retry(self, job_id: str) -> ImageJobCreated | None:
        async with self._lock:
            record = self._jobs.get(job_id)
            if record is None or not record.retryable:
                return None
            self._check_concurrency()
            replacement = _JobRecord(_new_job_id(), record.prompt, brief=record.brief)
            self._start_trace(
                replacement,
                "understanding",
                "正在重新准备图解任务",
                "复用已整理的图解需求继续生成。",
            )
            self._jobs[replacement.job_id] = replacement
            self._start(replacement, self._execute_initial(replacement))
        return self._created(replacement)

    def _start(self, record: _JobRecord, coroutine: Coroutine[Any, Any, None]) -> None:
        self._active_job_id = record.job_id
        record._task = asyncio.create_task(coroutine)

    async def _execute_initial(self, record: _JobRecord) -> None:
        try:
            self._complete_running(record, "图解需求已确认", "已确认主题、画面目标与科学表达边界。")
            if record.brief is None:
                self._set_stage(record, "rewriting_prompt")
                self._start_trace(
                    record,
                    "prompt_rewrite",
                    "正在优化生成描述",
                    "将需求整理为适合科学图解模型理解的视觉指令。",
                )
                record.brief = await self._organizer.refine(record.prompt)
                self._complete_running(
                    record,
                    "生成描述已优化",
                    _safe_prompt_summary(record.brief.optimized_chinese_prompt)
                    + " "
                    + derive_visual_complexity_contract(record.brief).summary(),
                )
            self._check_cancel(record)
            self._set_stage(record, "generating")
            generator_name = "Wan 图像生成模型"
            self._start_trace(
                record, "generation", "正在生成第一版图像", f"已提交至 {generator_name}。"
            )
            initial_path = self._version_path(record, 0)
            result = await self._wan_generator.generate(
                brief=record.brief,
                output_path=initial_path,
                cancel_event=record.cancel_event,
                user_prompt=record.prompt,
            )
            record.cell_ip_profile = getattr(result, "cell_ip_profile", None)
            record.final_generation_prompt = getattr(result, "final_prompt", None)
            record.reference_names_sent = tuple(
                getattr(result, "reference_names_sent", ())
            )
            self._promote(record, result.final_path, "initial")
            self._complete_running(record, "第一版图像已生成", "正在准备视觉质量审查。")
            if not self._settings.enable_fast_image_refinement_pipeline:
                self._append_event(
                    record, "warning", "视觉审查未启用", "当前配置未启用自动视觉审查。", "warning"
                )
                await self._finish(record, "completed")
                return
            self._set_stage(record, "critic_review_1")
            self._start_trace(
                record,
                "visual_critic",
                "正在进行视觉审查",
                "检查主体结构、文字、构图和明显视觉错误。",
            )
            record.critic_result = await self._critic.review(
                record.trusted_path,
                user_prompt=record.prompt,
                review_label="首次生成",
                audit_contract=_audit_contract(record),
                cell_ip_context=_cell_ip_critic_context(record),
                cell_ip_references=_cell_ip_review_references(record),
                cell_ip_reference_names=_cell_ip_reference_names(record),
            )
            bbox, issues = self._auto_revision_scope(record, record.critic_result)
            if record.critic_result.overall_status == "pass":
                self._complete_running(record, "视觉审查完成", "没有发现需要继续修正的明显问题。")
                await self._finish(record, "completed")
            elif bbox is not None and issues:
                self._complete_running(
                    record,
                    "视觉审查发现一个可自动修正的问题",
                    _safe_issue_summary(issues[0].description),
                )
                await self._execute_auto_revision(record, bbox, issues)
            else:
                self._complete_critic_for_human(record)
                await self._finish(record, "awaiting_human_feedback")
        except (asyncio.CancelledError, JobCancelledError):
            await self._finish(record, "cancelled")
        except Exception as exc:
            record.error = _format_error(exc, self._settings.dashscope_api_key)
            await self._finish(record, "failed")
        finally:
            await self._release(record)

    async def _execute_auto_revision(
        self, record: _JobRecord, bbox: NormalizedBBox, issues: list[VisualIssue]
    ) -> None:
        if record.trusted_path is None:
            raise RuntimeError("trusted image missing before automatic revision")
        self._set_stage(record, "auto_revising")
        self._start_trace(
            record,
            "auto_revision",
            "正在整理并执行局部修改",
            "根据审查结果，只修改已识别的目标区域。",
        )
        record.auto_revision_count += 1
        instruction = self._rewriter.rewrite_auto(issues)
        record.last_revision_bbox = bbox
        record.last_edit_instruction = instruction
        original_path = record.trusted_path
        candidate_path = self._candidate_path(record, record.version + 1)
        try:
            result = await self._wan_generator.edit(
                source_path=original_path,
                output_path=candidate_path,
                instruction=instruction,
                bbox=bbox,
                cancel_event=record.cancel_event,
                cell_ip_profile=record.cell_ip_profile,
            )
            record.candidate_path = result.final_path
            self._complete_running(record, "局部修改已生成", "候选结果尚需通过修改范围检查。")
            self._set_stage(record, "guard_check")
            self._start_trace(
                record, "scope_guard", "正在检查修改范围", "确认修改是否局限在目标区域。"
            )
            record.guard_result = await self._guard.check(original_path, result.final_path, bbox)
        except (asyncio.CancelledError, JobCancelledError):
            raise
        except Exception:
            self._unlink(candidate_path)
            record.candidate_path = None
            self._complete_running(
                record,
                "自动修改未被采纳",
                "已保留上一版可靠图片。",
                status="warning",
            )
            await self._finish(record, "awaiting_human_feedback")
            return
        if not record.guard_result.passed:
            if record.guard_result.changed_outside_bbox:
                await self._adopt_with_collateral_review(
                    record, result.final_path, instruction, bbox, origin="auto"
                )
                return
            self._complete_running(
                record, "本次修改未通过范围检查", "已保留上一版可靠图片。", status="warning"
            )
            await self._finish(record, "awaiting_human_feedback")
            return
        self._complete_running(
            record, "修改范围检查通过", "目标区域已发生有效变化，其他区域保持稳定。"
        )
        self._promote(record, result.final_path, "auto")
        self._set_stage(record, "critic_review_2")
        self._start_trace(
            record, "final_critic", "正在重新进行视觉审查", "检查自动修订后的完整性和目标问题。"
        )
        record.critic_result = await self._critic.review(
            record.trusted_path,
            user_prompt=record.prompt,
            review_label="自动修订后",
            revision_instruction=instruction,
            target_bbox=bbox,
            audit_contract=_audit_contract(record),
            cell_ip_context=_cell_ip_critic_context(record),
            cell_ip_references=_cell_ip_review_references(record),
            cell_ip_reference_names=_cell_ip_reference_names(record),
        )
        next_bbox, next_issues = self._auto_revision_scope(record, record.critic_result)
        if record.critic_result.overall_status != "pass" and next_bbox is not None:
            self._complete_running(
                record,
                "仍发现可自动修正的局部文字问题",
                _safe_issue_summary(next_issues[0].description),
            )
            await self._execute_auto_revision(record, next_bbox, next_issues)
            return
        self._complete_final_critic(record)
        await self._finish(
            record,
            "completed"
            if record.critic_result.overall_status == "pass"
            else "awaiting_human_feedback",
        )

    async def _execute_human_edit(self, record: _JobRecord, payload: ImageEditRequest) -> None:
        roi_before_path: Path | None = None
        roi_after_path: Path | None = None
        local_erase_path: Path | None = None
        try:
            if record.trusted_path is None:
                raise RuntimeError("trusted image missing before human revision")
            self._set_stage(record, "editing_with_bbox")
            self._complete_running(record, "修改要求已确认", "本轮只处理你框选的目标区域。")
            self._start_trace(
                record, "edit_rewrite", "正在优化局部编辑指令", "加入范围约束并保留原图的其他内容。"
            )
            original_path = record.trusted_path
            frozen_image_id = record.image_id
            next_version = record.version + 1
            candidate_path = self._candidate_path(record, next_version)
            roi_before_path = self._roi_artifact_path(record, next_version, "roi-before")
            roi_after_path = self._roi_artifact_path(record, next_version, "roi-after")
            local_erase_path = self._roi_artifact_path(record, next_version, "local-erase")
            roi_context = await asyncio.to_thread(
                prepare_roi,
                original_path,
                roi_before_path,
                payload.bbox,
                padding_ratio=self._settings.image_edit_roi_padding_ratio,
                min_side_px=self._settings.image_edit_min_bbox_side_px,
                min_area_px=self._settings.image_edit_min_bbox_area_px,
            )
            logger.info(
                "human_edit_roi original_bbox=%s expanded_bbox=%s roi_size=%s image_size=%s "
                "trusted_image_id=%s",
                roi_context.original_bbox,
                roi_context.expanded_bbox,
                roi_context.roi_size,
                roi_context.image_size,
                frozen_image_id,
            )
            instruction = self._rewriter.rewrite_human(payload.user_edit_request)
            self._complete_running(
                record, "局部编辑指令已整理", "已明确目标区域与需要保持不变的内容。"
            )
            record.last_revision_bbox = payload.bbox
            record.last_edit_instruction = instruction
            local_erase = None
            if self._rewriter.is_removal_request(payload.user_edit_request):
                self._start_trace(
                    record,
                    "auto_revision",
                    "正在删除选中内容",
                    "先检查选区背景能否安全地本地擦除。",
                )
                local_erase = await erase_on_uniform_background(
                    original_path, local_erase_path, payload.bbox
                )
            if local_erase is not None and local_erase.applied:
                await asyncio.to_thread(
                    crop_roi, local_erase_path, roi_after_path, roi_context.expanded_bbox
                )
                self._complete_running(record, "选中内容已删除", local_erase.reason)
            else:
                fallback_detail = (
                    local_erase.reason
                    if local_erase is not None
                    else "当前操作需要生成式局部编辑。"
                )
                self._start_trace(
                    record,
                    "auto_revision",
                    "正在修改选中区域",
                    f"{fallback_detail} 已提交至 Wan 局部编辑模型。",
                )
                result = await self._wan_generator.edit(
                    source_path=roi_before_path,
                    output_path=roi_after_path,
                    instruction=instruction,
                    bbox=NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
                    cancel_event=record.cancel_event,
                    cell_ip_profile=(
                        None
                        if self._rewriter.is_text_edit_request(payload.user_edit_request)
                        else record.cell_ip_profile
                    ),
                )
                roi_after_path = result.final_path
                self._complete_running(record, "选中区域已修改", "候选结果尚需通过修改范围检查。")
            if record.trusted_path != original_path or record.image_id != frozen_image_id:
                raise JobVersionConflictError("trusted image changed during ROI edit")
            composite = await asyncio.to_thread(
                composite_roi,
                original_path,
                roi_after_path,
                candidate_path,
                roi_context,
                feather_px=self._settings.image_edit_mask_feather_px,
                outside_tolerance=self._settings.image_edit_outside_pixel_tolerance,
                max_aspect_ratio_error=self._settings.image_edit_max_aspect_ratio_error,
            )
            record.candidate_path = composite.output_path
            logger.info(
                "human_edit_composite outside_diff_ratio=%.8f outside_max_channel_diff=%s "
                "mask_area_ratio=%.8f edited_roi_resized=%s aspect_ratio_error=%.8f",
                composite.outside_diff_ratio,
                composite.outside_max_channel_diff,
                composite.mask_area_ratio,
                composite.edited_roi_resized,
                composite.edited_roi_aspect_ratio_error,
            )
            if self._settings.debug:
                await asyncio.to_thread(
                    shutil.copyfile,
                    composite.output_path,
                    self._roi_artifact_path(record, next_version, "final-composite"),
                )
                await asyncio.to_thread(
                    save_debug_metadata,
                    self._roi_debug_metadata_path(record, next_version),
                    context=roi_context,
                    original_bbox=payload.bbox,
                    composite=composite,
                )
            self._set_stage(record, "guard_check")
            self._start_trace(
                record, "scope_guard", "正在检查修改范围", "确认框外区域是否保持稳定。"
            )
            record.guard_result = await self._guard.check(
                original_path, candidate_path, payload.bbox
            )
            if not record.guard_result.passed:
                log_method = (
                    logger.error if record.guard_result.changed_outside_bbox else logger.warning
                )
                log_method(
                    "human_edit_scope_guard_failed changed_outside_bbox=%s "
                    "insufficient_change_inside_bbox=%s outside_change_score=%s "
                    "inside_change_score=%s trusted_image_id=%s",
                    record.guard_result.changed_outside_bbox,
                    record.guard_result.insufficient_change_inside_bbox,
                    record.guard_result.outside_change_score,
                    record.guard_result.inside_change_score,
                    frozen_image_id,
                )
                failure_detail = (
                    "硬合成后仍检测到授权框外变化，已按合成异常拒绝候选；"
                    "上一版可靠图片保持不变。"
                    if record.guard_result.changed_outside_bbox
                    else "框内变化不足，无法确认模型已完成修改；上一版可靠图片保持不变。"
                )
                self._complete_running(
                    record,
                    "本次修改未通过范围检查",
                    failure_detail,
                    status="warning",
                )
                await self._finish(record, "awaiting_human_feedback")
                return
            self._complete_running(
                record, "修改范围检查通过", "目标区域已发生有效变化，其他区域保持稳定。"
            )
            self._set_stage(record, "critic_review_final")
            self._start_trace(
                record,
                "final_critic",
                "正在进行最终视觉审查",
                "检查局部修改是否完成且画面保持完整。",
            )
            record.critic_result = await self._critic.review(
                candidate_path,
                user_prompt=record.prompt,
                review_label="人工局部编辑后",
                revision_instruction=instruction,
                target_bbox=payload.bbox,
                audit_contract=_audit_contract(record),
                cell_ip_context=_cell_ip_critic_context(record),
                cell_ip_references=_cell_ip_review_references(record),
                cell_ip_reference_names=_cell_ip_reference_names(record),
            )
            expected_text = self._rewriter.exact_text_replacement(payload.user_edit_request)
            if expected_text is not None:
                record.critic_result = _enforce_exact_text_replacement(
                    record.critic_result, expected_text, payload.bbox
                )
            logger.info(
                "human_edit_critic passed=%s issues=%s image_id=%s",
                record.critic_result.overall_status == "pass",
                [issue.issue_type for issue in record.critic_result.issues],
                record.image_id,
            )
            self._complete_final_critic(record)
            if record.critic_result.overall_status == "pass":
                self._promote(record, candidate_path, "human")
            await self._finish(
                record,
                "completed"
                if record.critic_result.overall_status == "pass"
                else "awaiting_human_feedback",
            )
        except (asyncio.CancelledError, JobCancelledError):
            self._unlink(record.candidate_path)
            record.candidate_path = None
            self._complete_running(
                record, "本次修改已取消", "已保留上一版可靠图片。", status="warning"
            )
            await self._finish(record, "awaiting_human_feedback")
        except Exception as exc:
            record.error = _format_error(exc, self._settings.dashscope_api_key)
            self._unlink(record.candidate_path)
            record.candidate_path = None
            self._complete_running(
                record,
                "局部编辑失败",
                "已保留上一版可靠图片，请调整框选或修改要求后重试。",
                status="warning",
            )
            logger.warning(
                "human_edit_failed trusted_image_id=%s error_type=%s error=%s",
                record.image_id,
                type(exc).__name__,
                record.error,
            )
            await self._finish(record, "awaiting_human_feedback")
        finally:
            self._unlink(local_erase_path)
            if not self._settings.debug:
                self._unlink(roi_before_path)
                self._unlink(roi_after_path)
            await self._release(record)

    async def _adopt_with_collateral_review(
        self,
        record: _JobRecord,
        final_path: Path,
        instruction: str,
        bbox: NormalizedBBox,
        *,
        origin: RevisionOrigin,
    ) -> None:
        """Adopt a revision that also changed outside its target box.

        The scope guard cannot describe *where* the collateral change happened,
        so the revised image is promoted and the vision critic is asked to point
        out the affected regions.  A deterministic human-review issue is then
        appended so the frontend always surfaces a manual check request.
        """
        guard = record.guard_result
        if origin != "auto":
            raise ValueError("only automatic revisions may be adopted with collateral changes")
        critic_stage: ImageJobStage = "critic_review_2"
        review_label = "自动修订后（框外变化需人工核验）"
        self._complete_running(
            record,
            "范围保护检测到框外变化",
            "已采用修订结果，请在下方审核意见中核验框外被修改的其他区域。",
            status="warning",
        )
        self._promote(record, final_path, origin)
        self._set_stage(record, critic_stage)
        self._start_trace(
            record,
            "final_critic",
            "正在核验修订后画面",
            "检查框外被修改区域是否需要人工确认。",
        )
        collateral_note = None
        if guard is not None:
            collateral_note = (
                f"目标框外区域检测到像素变化（框外变化分 {guard.outside_change_score} "
                f"超过阈值 {guard.threshold}）。请指出框外哪些具体位置发生了变化"
                "（可用 bbox 或位置描述），并判断这些变化是否影响画面完整性或科学表达；"
                "在 issues 中标记需要人工核验的变化。"
            )
        record.critic_result = await self._critic.review(
            record.trusted_path,
            user_prompt=record.prompt,
            review_label=review_label,
            revision_instruction=instruction,
            target_bbox=bbox,
            collateral_change_note=collateral_note,
            audit_contract=_audit_contract(record),
            cell_ip_context=_cell_ip_critic_context(record),
            cell_ip_references=_cell_ip_review_references(record),
            cell_ip_reference_names=_cell_ip_reference_names(record),
        )
        record.critic_result = _with_collateral_human_review(record.critic_result, guard)
        self._complete_final_critic(record)
        await self._finish(record, "awaiting_human_feedback")

    def _auto_revision_scope(
        self, record: _JobRecord, critic: VisualCriticResult
    ) -> tuple[NormalizedBBox | None, list[VisualIssue]]:
        if record.auto_revision_count >= self._settings.image_auto_revision_max:
            return None, []
        # A critic can legitimately return both an exactly repairable text
        # defect and a separate issue that still needs a human decision (for
        # example, a fixed-IP character mismatch). The aggregate action is
        # then ``request_human_feedback``, but it must not suppress the safe,
        # bounded text repair advertised to the user as "可自动修复".
        eligible = [
            issue for issue in critic.issues
            if issue.bbox is not None
            and issue.auto_fixable
            and not issue.human_input_required
            and issue.confidence >= self._settings.image_critic_auto_bbox_min_confidence
        ]
        if not eligible:
            return None, []
        # Text rendering defects get priority.  They are repaired one bbox at
        # a time so the scope guard can reject any collateral image change.
        issue = max(
            eligible,
            key=lambda item: (
                item.issue_type == "text_error",
                item.severity == "high",
                item.severity == "medium",
                item.confidence,
            ),
        )
        return issue.bbox, [issue]

    def _promote(self, record: _JobRecord, path: Path, origin: RevisionOrigin) -> None:
        if record.trusted_path is not None and record.image_id is not None:
            record.previous_trusted_path = record.trusted_path
            record.previous_image_id = record.image_id
            record.previous_revision_origin = record.revision_origin
            record.previous_critic_result = record.critic_result
        record.version += 1
        final_path = self._version_path(record, record.version)
        if path != final_path:
            path.replace(final_path)
        record.trusted_path = final_path
        record.image_id = f"{record.job_id}-v{record.version}"
        record.revision_origin = origin
        record.candidate_path = None

    def _version_path(self, record: _JobRecord, version: int) -> Path:
        output_dir = Path(self._settings.generated_image_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{record.job_id}-v{version}.png"

    def _candidate_path(self, record: _JobRecord, version: int) -> Path:
        output_dir = Path(self._settings.generated_image_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{record.job_id}-v{version}-rejected.png"

    def _roi_artifact_path(self, record: _JobRecord, version: int, name: str) -> Path:
        output_dir = Path(self._settings.generated_image_dir) / "debug" / record.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"v{version}-{name}.png"

    def _roi_debug_metadata_path(self, record: _JobRecord, version: int) -> Path:
        output_dir = Path(self._settings.generated_image_dir) / "debug" / record.job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"v{version}-roi.json"

    def _metadata_path(self, job_id: str) -> Path:
        return Path(self._settings.generated_image_dir) / f"{job_id}.json"

    async def _finish(self, record: _JobRecord, stage: ImageJobStage) -> None:
        if stage in _TERMINAL_STAGES:
            record.finished_at = datetime.now(timezone.utc)
        if stage in {"failed", "cancelled"}:
            running_stage = (
                record.trace_events[-1].stage
                if record.trace_events and record.trace_events[-1].status == "running"
                else None
            )
            title = (
                "生成已取消"
                if stage == "cancelled"
                else ("生成描述优化失败" if running_stage == "prompt_rewrite" else "图像生成失败")
            )
            detail = None if stage == "cancelled" else "本次任务未能完成，请稍后重试。"
            self._complete_running(record, title, detail, status="warning")
            self._unlink(record.candidate_path)
            if record.trusted_path is None:
                await asyncio.to_thread(
                    _unlink_job_outputs,
                    Path(self._settings.generated_image_dir),
                    record.job_id,
                )
            record.candidate_path = None
        elif stage == "awaiting_human_feedback":
            self._append_event(
                record,
                "human_feedback",
                "需要你的确认",
                "当前问题不适合继续自动修改，你可以在图片上框选区域并提出修改要求。",
                "warning",
            )
        elif stage == "completed":
            self._append_event(
                record, "completed", "图解已准备完成", "最终图片已生成。", "completed"
            )
        await self._write_audit(record, stage)
        record.stage = stage
        logger.info("image job stage job_id=%s stage=%s", record.job_id, stage)

    async def _write_audit(self, record: _JobRecord, stage: ImageJobStage) -> None:
        metadata = {
            "job_id": record.job_id,
            "prompt": record.prompt,
            "brief": record.brief.model_dump() if record.brief else None,
            "generation_route": record.generation_route,
            "visual_profile": record.brief.visual_profile if record.brief else None,
            "image_model": self._settings.dashscope_image_model,
            "cell_ip_enabled": self._settings.cell_ip_enabled,
            "cell_ip_role_ids": (
                list(record.cell_ip_profile.role_ids) if record.cell_ip_profile else []
            ),
            "cell_ip_unmatched_cell_terms": (
                list(record.cell_ip_profile.unmatched_cell_terms)
                if record.cell_ip_profile
                else []
            ),
            "reference_assets": (
                list(record.cell_ip_profile.reference_names)
                if record.cell_ip_profile
                else [f"default:{record.image_type}"] if record.image_type else []
            ),
            "reference_assets_actually_sent": list(record.reference_names_sent),
            "locked_ip_contracts": (
                [
                    {"role_id": role_id, "asset_id": f"canonical:{role_id}"}
                    for role_id in record.cell_ip_profile.role_ids
                ]
                if record.cell_ip_profile
                else []
            ),
            "final_compiled_prompt": (
                record.final_generation_prompt[:5000]
                if record.final_generation_prompt
                else None
            ),
            "visual_complexity_contract": (
                derive_visual_complexity_contract(record.brief).metadata()
                if record.brief
                else None
            ),
            "aspect_ratio": (
                record.cell_ip_profile.aspect_ratio
                if record.cell_ip_profile
                else "9:16"
            ),
            "image_id": record.image_id,
            "trusted_image": record.trusted_path.name if record.trusted_path else None,
            "candidate_image": record.candidate_path.name if record.candidate_path else None,
            "critic_result": (record.critic_result.model_dump() if record.critic_result else None),
            "guard_result": record.guard_result.model_dump() if record.guard_result else None,
            "auto_revision_count": record.auto_revision_count,
            "revision_origin": record.revision_origin,
            "last_revision_bbox": (
                record.last_revision_bbox.root if record.last_revision_bbox else None
            ),
            "last_edit_instruction": (
                record.last_edit_instruction[:1500] if record.last_edit_instruction else None
            ),
            "created_at": record.created_at.isoformat(),
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
            "stage": stage,
            "error": _sanitise_error(record.error),
            "trace_id": record.trace_id,
            "trace_events": [event.model_dump(mode="json") for event in record.trace_events],
            "trace_history": record.trace_history,
        }
        await asyncio.to_thread(
            _atomic_write_json,
            self._metadata_path(record.job_id),
            metadata,
        )

    async def _release(self, record: _JobRecord) -> None:
        async with self._lock:
            if self._active_job_id == record.job_id:
                self._active_job_id = None

    def _check_concurrency(self) -> None:
        if self._active_job_id is None:
            return
        active = self._jobs.get(self._active_job_id)
        if active and active._task and not active._task.done():
            raise JobConflictError("another image operation is running")

    @staticmethod
    def _set_stage(record: _JobRecord, stage: ImageJobStage) -> None:
        record.stage = stage
        logger.info("image job stage job_id=%s stage=%s", record.job_id, stage)

    @staticmethod
    def _created(record: _JobRecord) -> ImageJobCreated:
        return ImageJobCreated(
            job_id=record.job_id, trace_id=record.trace_id, trace_events=record.trace_events
        )

    @staticmethod
    def _archive_trace(record: _JobRecord) -> None:
        record.trace_history.append(
            {
                "trace_id": record.trace_id,
                "events": [event.model_dump(mode="json") for event in record.trace_events],
            }
        )
        record.trace_id = _new_job_id()
        record.trace_events = []

    @classmethod
    def _start_trace(
        cls, record: _JobRecord, stage: ImageProcessStage, title: str, detail: str | None = None
    ) -> None:
        cls._complete_running(record)
        cls._append_event(record, stage, title, detail, "running")

    @staticmethod
    def _append_event(
        record: _JobRecord, stage: ImageProcessStage, title: str, detail: str | None, status: str
    ) -> None:
        record.trace_events.append(
            ImageProcessEvent(
                id=f"{record.trace_id}-{len(record.trace_events) + 1}",
                stage=stage,
                title=title,
                detail=detail,
                status=status,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _complete_running(
        record: _JobRecord,
        title: str | None = None,
        detail: str | None = None,
        *,
        status: str = "completed",
    ) -> None:
        if not record.trace_events or record.trace_events[-1].status != "running":
            return
        current = record.trace_events[-1]
        record.trace_events[-1] = current.model_copy(
            update={
                "title": title or current.title,
                "detail": detail if detail is not None else current.detail,
                "status": status,
            }
        )

    @classmethod
    def _complete_critic_for_human(cls, record: _JobRecord) -> None:
        result = record.critic_result
        if result is None:
            cls._complete_running(
                record, "视觉审查暂时不可用", "请人工确认当前图片。", status="warning"
            )
            return
        unavailable = bool(result.issues) and result.issues[0].description.startswith(
            "本轮未获得可验证"
        )
        if unavailable:
            cls._complete_running(
                record,
                "视觉审查暂时不可用",
                "未获得可验证的审查结果，请人工确认当前图片。",
                status="warning",
            )
        else:
            cls._complete_running(
                record,
                "视觉审查需要人工确认",
                _safe_issue_summary(result.summary),
                status="warning",
            )

    @classmethod
    def _complete_final_critic(cls, record: _JobRecord) -> None:
        if record.critic_result and record.critic_result.overall_status == "pass":
            cls._complete_running(record, "最终视觉审查完成", "没有发现需要继续修正的明显问题。")
        else:
            cls._complete_critic_for_human(record)

    @staticmethod
    def _validate_prompt(prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be blank")
        if len(prompt) > 2000:
            raise ValueError("prompt cannot exceed 2000 characters")
        return prompt

    @staticmethod
    def _check_cancel(record: _JobRecord) -> None:
        if record.cancel_event.is_set():
            raise JobCancelledError

    @staticmethod
    def _unlink(path: Path | None) -> None:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _public_url(path: Path | None) -> str | None:
    return f"/api/v1/generated-images/{path.name}" if path else None


def _new_job_id() -> str:
    return uuid.uuid4().hex[:_JOB_ID_BYTES]


def _safe_prompt_summary(prompt: str) -> str:
    compact = " ".join(prompt.split())
    if len(compact) > 180:
        compact = compact[:179].rstrip() + "…"
    return f"已整理视觉指令摘要：{compact}"


def _cell_ip_critic_context(record: _JobRecord) -> str | None:
    return record.cell_ip_profile.critic_context if record.cell_ip_profile else None


def _audit_contract(record: _JobRecord) -> str:
    """Give the critic observable requirements without asking it to fact-check."""

    brief = record.brief
    if brief is None:
        return "未获得结构化 brief；检查画面是否清晰、完整并与用户需求一致。"
    labels = "、".join(brief.chinese_labels)
    steps = "\n".join(
        f"{index}. {step.primary_relation}"
        for index, step in enumerate(brief.core_causal_steps, start=1)
    )
    return (
        f"图像类型：{brief.image_type}\n"
        f"应出现且可读的中文标签：{labels}\n"
        f"应按顺序可视化的核心步骤：\n{steps}\n"
        f"{derive_visual_complexity_contract(brief).audit_text()}\n"
        "检查重点：对象、箭头/编号/分区是否使步骤顺序可辨；不要据此判断医学事实真伪。"
    )


def _cell_ip_review_references(record: _JobRecord) -> list[bytes]:
    return record.cell_ip_profile.review_references if record.cell_ip_profile else []


def _cell_ip_reference_names(record: _JobRecord) -> tuple[str, ...]:
    return record.cell_ip_profile.reference_names if record.cell_ip_profile else ()


def _safe_issue_summary(summary: str) -> str:
    compact = " ".join(summary.split())
    return compact[:240] if compact else "当前结果需要进一步确认。"


def _enforce_exact_text_replacement(
    result: VisualCriticResult, expected_text: str, bbox: NormalizedBBox
) -> VisualCriticResult:
    """Fail closed when the independent blind read cannot find requested exact copy."""

    audit = result.blind_text_audit
    visible_text = (
        "".join(block.text.replace(" ", "") for block in audit.text_blocks) if audit else ""
    )
    normalized_expected = expected_text.replace(" ", "")
    if normalized_expected and normalized_expected in visible_text:
        return result
    evidence = f"独立文字盲读未检测到用户指定的精确文字“{expected_text}”。"
    issue = VisualIssue(
        issue_type="text_regeneration",
        severity="high",
        description=evidence,
        bbox=bbox,
        confidence=1.0,
        suggested_fix=f"仅将框内文字替换为“{expected_text}”，并保持原排版。",
        auto_fixable=False,
        human_input_required=True,
    )
    checks = result.audit_checks.model_copy(
        update={
            "text_legibility": result.audit_checks.text_legibility.model_copy(
                update={"status": "issue", "evidence": evidence, "confidence": 1.0}
            )
        }
    )
    return result.model_copy(
        update={
            "overall_status": "needs_human_review",
            "summary": evidence + " 候选未提升，已保留上一版可信图片。",
            "recommended_action": "request_human_feedback",
            "auto_fixable": False,
            "human_input_required": True,
            "audit_checks": checks,
            "issues": [*result.issues[:11], issue],
        }
    )


def _with_collateral_human_review(
    result: VisualCriticResult, guard: EditScopeGuardResult | None
) -> VisualCriticResult:
    """Force a human-review state and append the scope-guard finding as an issue."""
    score_text = (
        f"框外变化分 {guard.outside_change_score} 超过阈值 {guard.threshold}"
        if guard is not None
        else "范围保护检测到目标框外区域发生变化"
    )
    note = VisualIssue(
        issue_type="other",
        severity="medium",
        description=(
            f"修订后，范围保护检测到目标框外区域也被修改（{score_text}）。"
            "修订图已替换显示，请人工核验框外被修改的其他区域是否可接受。"
        ),
        bbox=None,
        confidence=1.0,
        suggested_fix=(
            "请在下方 AI 审核中查看框外变化位置；如需调整，可框选相关区域再次修改，"
            "或确认无误后接受当前结果。"
        ),
        auto_fixable=False,
        human_input_required=True,
    )
    return result.model_copy(
        update={
            "overall_status": "needs_human_review",
            "recommended_action": "request_human_feedback",
            "auto_fixable": False,
            "human_input_required": True,
            "issues": [*result.issues, note][:12],
        }
    )


def _sanitise_error(error: str | None) -> str | None:
    if error is None:
        return None
    lower = error.casefold()
    if "�" in error or any(
        token in lower for token in ("sk-", "dashscope", "api_key", "api key", "bearer ")
    ):
        return _GENERIC_FAILURE_MESSAGE
    return error[:500]


def _format_error(exc: Exception, api_key: str | None = None) -> str:
    raw = str(exc)
    if type(exc).__name__ == "ScienceImageNotConfiguredError":
        return "图解生成服务尚未配置，请检查后端密钥后重试。"
    if api_key and api_key in raw:
        return _GENERIC_FAILURE_MESSAGE
    return _sanitise_error(raw) or type(exc).__name__


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _unlink_job_outputs(output_dir: Path, job_id: str) -> None:
    for path in output_dir.glob(f"{job_id}*.png"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
