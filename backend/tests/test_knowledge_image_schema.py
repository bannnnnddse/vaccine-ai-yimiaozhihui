import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas import knowledge_image
from app.schemas.science_figure import ChineseFigureBrief


def test_image_job_request_strips_prompt_without_caller_selected_type() -> None:
    value = knowledge_image.ImageJobCreateRequest(prompt="  HPV反应  ")

    assert value.prompt == "HPV反应"


def test_image_job_request_rejects_type_from_caller() -> None:
    with pytest.raises(ValidationError):
        knowledge_image.ImageJobCreateRequest(
            image_type="science_poster", prompt="HPV反应"
        )


def test_image_job_request_rejects_blank_prompt_after_stripping() -> None:
    with pytest.raises(ValidationError):
        knowledge_image.ImageJobCreateRequest(prompt="   ")


def test_image_job_created_starts_in_queued_stage() -> None:
    created = knowledge_image.ImageJobCreated(job_id="job-1")

    assert created.model_dump() == {
        "job_id": "job-1",
        "stage": "queued",
        "trace_id": "",
        "trace_events": [],
    }
    with pytest.raises(ValidationError):
        knowledge_image.ImageJobCreated(job_id="job-1", stage="rendering")


def test_image_job_stage_contract_is_exact() -> None:
    adapter = TypeAdapter(knowledge_image.ImageJobStage)
    stages = [
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

    assert [adapter.validate_python(stage) for stage in stages] == stages
    with pytest.raises(ValidationError):
        adapter.validate_python("preparing_content")


def test_image_process_event_contract_rejects_hidden_or_unknown_stages() -> None:
    event = knowledge_image.ImageProcessEvent(
        id="trace-1-1",
        stage="prompt_rewrite",
        title="正在优化生成描述",
        detail="整理视觉指令。",
        status="running",
        created_at="2026-08-13T10:00:00Z",
    )

    assert event.stage == "prompt_rewrite"
    with pytest.raises(ValidationError):
        knowledge_image.ImageProcessEvent(
            id="trace-1-2",
            stage="hidden_reasoning",
            title="内部推理",
            status="running",
            created_at="2026-08-13T10:00:00Z",
        )


def test_image_job_status_exposes_detected_type_and_route_after_refining() -> None:
    pending = knowledge_image.ImageJobStatus(
        job_id="job-1",
        stage="queued",
    )
    status = knowledge_image.ImageJobStatus(
        job_id="job-1",
        image_type="mechanism_diagram",
        generation_route="fast",
        stage="failed",
        error="生成失败，请重试",
        retryable=True,
    )

    assert pending.image_type is None
    assert pending.generation_route is None
    assert status.stage == "failed"
    assert status.error == "生成失败，请重试"
    assert status.retryable is True
    assert status.auto_revision_count == 0


def test_completed_status_requires_detected_type_and_generation_route() -> None:
    with pytest.raises(ValidationError):
        knowledge_image.ImageJobStatus(job_id="job-1", stage="completed")

    with pytest.raises(ValidationError):
        knowledge_image.ImageJobStatus(
            job_id="job-1", image_type="mechanism_diagram", stage="completed"
        )

    status = knowledge_image.ImageJobStatus(
        job_id="job-1",
        image_type="mechanism_diagram",
        generation_route="fast",
        stage="completed",
        image_url="/api/v1/generated-images/job-1.png",
        image_id="job-1-v0",
    )

    assert status.generation_route == "fast"


def test_chinese_brief_rejects_unknown_type_and_english_only_fields() -> None:
    with pytest.raises(ValidationError):
        ChineseFigureBrief(
            image_type="poster",
            generation_route="fast",
            optimized_chinese_prompt=(
                "制作9:16竖版中文疫苗科普图解，展示抗原识别、免疫细胞激活和"
                "免疫记忆形成，使用简洁的中文标签与医学插画。"
            ),
            chinese_labels=["疫苗抗原"],
            scientific_claims=["Antigen activates immunity."],
            core_causal_steps=[{"primary_relation": "疫苗抗原促进免疫细胞识别。"}],
            route_reason="单一机制适合快速图解。",
            expected_english_terms=["Antigen"],
        )
