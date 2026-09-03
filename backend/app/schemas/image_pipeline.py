"""Strict contracts for the fast image review and revision pipeline."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


class NormalizedBBox(RootModel[Annotated[list[float], Field(min_length=4, max_length=4)]]):
    """One normalized [x1, y1, x2, y2] rectangle."""

    @field_validator("root")
    @classmethod
    def validate_bbox(cls, value: list[float]) -> list[float]:
        if len(value) != 4:
            raise ValueError("bbox must contain exactly four coordinates")
        if any(coordinate < 0 or coordinate > 1 for coordinate in value):
            raise ValueError("bbox coordinates must be between 0 and 1")
        x1, y1, x2, y2 = value
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have positive width and height")
        return value


IssueType = Literal[
    "text_error",
    "text_regeneration",
    "layout",
    "artifact",
    "anatomy",
    "style_inconsistency",
    "ip_identity_mismatch",
    "scientific_expression",
    "other",
]

AuditCheckStatus = Literal["pass", "issue", "not_assessable"]


class VisualAuditCheck(BaseModel):
    """One explicit, image-grounded quality gate from the critic."""

    model_config = ConfigDict(extra="forbid")

    status: AuditCheckStatus
    evidence: str = Field(min_length=1, max_length=360)
    confidence: float = Field(ge=0, le=1)

    @field_validator("evidence")
    @classmethod
    def strip_evidence(cls, value: str) -> str:
        return value.strip()


class VisualAuditChecks(BaseModel):
    """Checklist that makes a ``pass`` explainable and auditable."""

    model_config = ConfigDict(extra="forbid")

    visual_integrity: VisualAuditCheck
    text_legibility: VisualAuditCheck
    layout_hierarchy: VisualAuditCheck
    brief_alignment: VisualAuditCheck
    causal_step_coverage: VisualAuditCheck
    scientific_expression_risk: VisualAuditCheck


class VisibleTextBlock(BaseModel):
    """Verbatim text detected without access to the generation brief."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=160)
    bbox: NormalizedBBox | None = None
    confidence: float = Field(ge=0, le=1)


class BlindTextAudit(BaseModel):
    """A deliberately context-free transcription pass for generated images."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["clear", "unreadable", "unavailable"]
    summary: str = Field(min_length=1, max_length=360)
    text_blocks: list[VisibleTextBlock] = Field(default_factory=list, max_length=24)


class VisualIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_type: IssueType
    severity: Literal["low", "medium", "high"]
    description: str = Field(min_length=1, max_length=500)
    bbox: NormalizedBBox | None = None
    # For a text repair these are deliberately separate from the narrative
    # fields: the editing model needs an exact replacement, not an inference.
    observed_text: str | None = Field(default=None, max_length=120)
    replacement_text: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0, le=1)
    suggested_fix: str = Field(min_length=1, max_length=500)
    auto_fixable: bool
    human_input_required: bool

    @field_validator("description", "suggested_fix")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("observed_text", "replacement_text")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_exact_text_replacement_for_auto_repair(self) -> VisualIssue:
        if self.issue_type == "text_error" and self.auto_fixable:
            if not self.observed_text or not self.replacement_text:
                raise ValueError(
                    "auto-fixable text_error requires observed_text and replacement_text"
                )
        return self


class VisualCriticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_status: Literal["pass", "needs_revision", "needs_human_review", "fail"]
    summary: str = Field(min_length=1, max_length=500)
    recommended_action: Literal["accept", "auto_fix", "request_human_feedback", "reject"]
    auto_fixable: bool
    human_input_required: bool
    audit_checks: VisualAuditChecks
    blind_text_audit: BlindTextAudit | None = None
    issues: list[VisualIssue] = Field(default_factory=list, max_length=12)

    @field_validator("summary")
    @classmethod
    def strip_summary(cls, value: str) -> str:
        return value.strip()


class EditScopeGuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    outside_change_score: float = Field(ge=0, le=1)
    threshold: float = Field(ge=0, le=1)
    changed_outside_bbox: bool
    inside_change_score: float = Field(ge=0, le=1)
    minimum_inside_change: float = Field(ge=0, le=1)
    insufficient_change_inside_bbox: bool
    outside_change_regions: list[NormalizedBBox] = Field(default_factory=list, max_length=4)
    notes: str = Field(min_length=1, max_length=500)


RevisionOrigin = Literal["initial", "auto", "human"]


class ImageEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_image_id: str = Field(min_length=1, max_length=100)
    bbox: NormalizedBBox
    user_edit_request: str = Field(min_length=1, max_length=1000)

    @field_validator("target_image_id", "user_edit_request")
    @classmethod
    def strip_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class ImageRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_image_id: str = Field(min_length=1, max_length=100)

    @field_validator("target_image_id")
    @classmethod
    def strip_target_image_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target_image_id cannot be blank")
        return value


class ImageJobAccepted(BaseModel):
    job_id: str
    stage: Literal["completed"] = "completed"


def normalize_critic(result: VisualCriticResult) -> VisualCriticResult:
    """Enforce conservative business semantics after schema validation."""
    issues: list[VisualIssue] = []
    for issue in result.issues:
        if issue.issue_type == "scientific_expression":
            issue = issue.model_copy(
                update={
                    "auto_fixable": False,
                    "human_input_required": True,
                    "description": ("潜在科学表达风险（当前未接入证据核验）：" + issue.description)[
                        :500
                    ],
                }
            )
        elif issue.issue_type == "text_error":
            if issue.observed_text and issue.replacement_text:
                issue = issue.model_copy(
                    update={"auto_fixable": True, "human_input_required": False}
                )
            else:
                issue = issue.model_copy(
                    update={
                        "issue_type": "text_regeneration",
                        "bbox": issue.bbox or NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
                        "suggested_fix": (
                            "重新生成画面中的全部文字：仅使用审核契约中的中文标签和步骤，"
                            "逐字清晰排版；删除乱码、错字、残字和不可读文字。"
                        ),
                        "auto_fixable": True,
                        "human_input_required": False,
                    }
                )
        issues.append(issue)

    checks = result.audit_checks
    required_checks = (
        checks.visual_integrity,
        checks.text_legibility,
        checks.layout_hierarchy,
        checks.brief_alignment,
        checks.causal_step_coverage,
    )
    missing_required_verification = any(
        check.status == "not_assessable" for check in required_checks
    )
    blind_text_requires_regeneration = (
        result.blind_text_audit is not None and result.blind_text_audit.status == "unreadable"
    )
    blind_text_unavailable = (
        result.blind_text_audit is None or result.blind_text_audit.status == "unavailable"
    )
    if blind_text_requires_regeneration:
        # The blind reader deliberately has no knowledge of the intended copy,
        # so it must not invent a replacement.  Regenerate the complete text
        # layer from the separately supplied visual contract instead.
        issues.append(
            VisualIssue(
                issue_type="text_regeneration",
                severity="high",
                description="文字盲读发现无法辨认、乱码或缺字的文本。",
                bbox=NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
                confidence=1.0,
                suggested_fix=(
                    "重新生成画面中的全部文字：仅使用审核契约中的中文标签和步骤，"
                    "逐字清晰排版；删除乱码、错字、残字和不可读文字。"
                ),
                auto_fixable=True,
                human_input_required=False,
            )
        )
    text_check_without_detail = checks.text_legibility.status == "issue" and not any(
        issue.issue_type in {"text_error", "text_regeneration"} for issue in issues
    )
    if text_check_without_detail:
        issues.append(
            VisualIssue(
                issue_type="text_regeneration",
                severity="high",
                description="文字可读性检查发现问题，但未提供可局部替换的精确文本。",
                bbox=NormalizedBBox([0.0, 0.0, 1.0, 1.0]),
                confidence=1.0,
                suggested_fix=(
                    "重新生成画面中的全部文字：仅使用审核契约中的中文标签和步骤，"
                    "逐字清晰排版；删除乱码、错字、残字和不可读文字。"
                ),
                auto_fixable=True,
                human_input_required=False,
            )
        )
    audit_issue_without_detail = (
        any(
            check.status == "issue"
            for check in (
                *required_checks,
                checks.scientific_expression_risk,
            )
        )
        and not issues
    )
    if missing_required_verification or audit_issue_without_detail or blind_text_unavailable:
        reason = (
            "关键视觉审核项无法验证。"
            if missing_required_verification
            else (
                "审核清单发现问题但未提供可执行的问题明细。"
                if audit_issue_without_detail
                else "图片文字盲读服务不可用，无法自动定位文字修复范围。"
            )
        )
        issues.append(
            VisualIssue(
                issue_type="other",
                severity="medium",
                description=reason,
                bbox=None,
                confidence=1.0,
                suggested_fix="请人工核验图片，并补充明确的问题区域或接受结果。",
                auto_fixable=False,
                human_input_required=True,
            )
        )

    has_human_issue = any(issue.human_input_required for issue in issues)
    if has_human_issue:
        return result.model_copy(
            update={
                "overall_status": "needs_human_review",
                "recommended_action": "request_human_feedback",
                "auto_fixable": False,
                "human_input_required": True,
                "issues": issues,
            }
        )
    if any(issue.auto_fixable for issue in issues):
        return result.model_copy(
            update={
                "overall_status": "needs_revision",
                "recommended_action": "auto_fix",
                "auto_fixable": True,
                "human_input_required": False,
                "issues": issues,
            }
        )
    if result.overall_status == "pass" or result.recommended_action == "accept":
        return result.model_copy(
            update={
                "overall_status": "pass",
                "recommended_action": "accept",
                "auto_fixable": False,
                "human_input_required": False,
                "issues": issues,
            }
        )
    return result.model_copy(update={"issues": issues})


def critic_unavailable_result(reason: str = "unknown") -> VisualCriticResult:
    safe_reasons = {
        "authentication_failed": "鉴权失败",
        "quota_exhausted": "额度不足",
        "rate_limited": "调用频率受限",
        "model_or_input_not_supported": "模型不支持当前图片审核输入",
        "structured_output_not_supported": "模型不支持当前结构化输出格式",
        "invalid_structured_output": "模型返回结果未通过结构校验",
        "timeout": "模型调用超时",
        "service_error": "模型服务异常",
        "local_image_error": "本地图片读取失败",
        "unknown": "未知调用异常",
    }
    reason_text = safe_reasons.get(reason, safe_reasons["unknown"])
    return VisualCriticResult(
        overall_status="needs_human_review",
        summary=f"AI 视觉审核未完成：{reason_text}。请人工确认图片内容后再接受或修改。",
        recommended_action="request_human_feedback",
        auto_fixable=False,
        human_input_required=True,
        audit_checks=VisualAuditChecks(
            visual_integrity=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
            text_legibility=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
            layout_hierarchy=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
            brief_alignment=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
            causal_step_coverage=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
            scientific_expression_risk=VisualAuditCheck(
                status="not_assessable", evidence="审核服务不可用。", confidence=1
            ),
        ),
        blind_text_audit=BlindTextAudit(
            status="unavailable",
            summary="审核服务不可用，未能执行独立文字盲读。",
            text_blocks=[],
        ),
        issues=[
            VisualIssue(
                issue_type="other",
                severity="medium",
                description=f"本轮未获得可验证的结构化视觉审核结果（{reason}）。",
                bbox=None,
                confidence=1,
                suggested_fix="请查看图片并决定接受结果或框选区域修改。",
                auto_fixable=False,
                human_input_required=True,
            )
        ],
    )
