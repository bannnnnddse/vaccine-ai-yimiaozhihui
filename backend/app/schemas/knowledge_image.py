from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.image_pipeline import (
    EditScopeGuardResult,
    RevisionOrigin,
    VisualCriticResult,
)
from app.schemas.science_figure import GenerationRoute, ScienceImageType

ImageJobStage = Literal[
    "queued",
    "rewriting_prompt",
    "generating",
    "critic_review_1",
    "auto_revising",
    "guard_check",
    "critic_review_2",
    "awaiting_human_feedback",
    "editing_with_bbox",
    "critic_review_final",
    "completed",
    "failed",
    "cancelled",
]

ImageProcessStage = Literal[
    "understanding",
    "prompt_rewrite",
    "generation",
    "visual_critic",
    "auto_revision",
    "edit_rewrite",
    "scope_guard",
    "human_feedback",
    "final_critic",
    "completed",
    "warning",
]

ImageProcessEventStatus = Literal["running", "completed", "warning"]


class ImageProcessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    stage: ImageProcessStage
    title: str = Field(min_length=1, max_length=120)
    detail: str | None = Field(default=None, max_length=500)
    status: ImageProcessEventStatus
    created_at: datetime


class ImageJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("prompt cannot be blank")
        return stripped


class ImageJobCreated(BaseModel):
    job_id: str
    stage: Literal["queued"] = "queued"
    trace_id: str = ""
    trace_events: list[ImageProcessEvent] = Field(default_factory=list)


class ImageJobStatus(BaseModel):
    job_id: str
    stage: ImageJobStage
    image_type: ScienceImageType | None = None
    generation_route: GenerationRoute | None = None
    image_url: str | None = None
    image_id: str | None = None
    candidate_image_url: str | None = None
    previous_image_url: str | None = None
    previous_image_id: str | None = None
    error: str | None = None
    retryable: bool = False
    critic_result: VisualCriticResult | None = None
    guard_result: EditScopeGuardResult | None = None
    auto_revision_count: int = Field(default=0, ge=0)
    revision_origin: RevisionOrigin | None = None
    previous_revision_origin: RevisionOrigin | None = None
    trace_id: str = ""
    trace_events: list[ImageProcessEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def completed_job_requires_detected_type_and_route(self) -> "ImageJobStatus":
        if self.stage in {"completed", "awaiting_human_feedback"} and (
            self.image_type is None
            or self.generation_route is None
            or self.image_url is None
            or self.image_id is None
        ):
            raise ValueError("published image job requires type, route, image ID, and image URL")
        return self


class KnowledgeImageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=1000)

    @field_validator("question", "answer")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text cannot be blank")
        return stripped


class KnowledgeImageResponse(BaseModel):
    image_url: str
    model: str
