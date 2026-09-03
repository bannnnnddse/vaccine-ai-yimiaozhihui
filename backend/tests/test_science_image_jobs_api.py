"""API integration tests for the science-image job endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.knowledge_image import ImageJobCreated, ImageJobStatus
from app.services.image_roi_editor import InvalidBBoxError
from app.services.science_image_job_manager import JobConflictError

# ── Test app factory ────────────────────────────────────────────────


@pytest.fixture
def app():
    """Return a fully wired FastAPI app with no external dependencies."""
    return create_app(Settings(dashscope_api_key=None))


@pytest.fixture
def mock_manager() -> AsyncMock:
    """Return a mock ScienceImageJobManager for dependency override."""
    return AsyncMock()


@pytest.fixture
def client(app, mock_manager) -> TestClient:
    """TestClient with the job manager dependency overridden."""
    from app.api.routes.science_image_jobs import get_job_manager

    app.dependency_overrides[get_job_manager] = lambda: mock_manager
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Lifespan initialisation ─────────────────────────────────────────


def test_lifespan_wires_job_manager_to_app_state() -> None:
    """The lifespan must attach a ScienceImageJobManager to app.state
    even when no API key is configured."""
    app = create_app(Settings(dashscope_api_key=None))

    from app.services.science_image_job_manager import ScienceImageJobManager

    # lifespan runs inside TestClient context
    with TestClient(app):
        manager = app.state.science_image_job_manager
        assert manager is not None
        assert isinstance(manager, ScienceImageJobManager)
        assert manager._wan_generator is app.state.wan_image_generator


def test_lifespan_wires_organizer_to_app_state() -> None:
    app = create_app(Settings(dashscope_api_key=None))

    from app.services.science_image_organizer import ScienceImageOrganizer

    with TestClient(app):
        organizer = app.state.science_image_organizer
        assert organizer is not None
        assert isinstance(organizer, ScienceImageOrganizer)


# ── POST /image-jobs ────────────────────────────────────────────────


def test_create_job_returns_201_and_job_id(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.return_value = ImageJobCreated(job_id="abcdef123456")

    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "HPV疫苗科普"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == "abcdef123456"
    assert data["stage"] == "queued"
    mock_manager.create.assert_awaited_once_with("HPV疫苗科普")


def test_create_job_rejects_blank_prompt(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    response = client.post(
        "/api/v1/image-jobs",
        json={"image_type": "science_poster", "prompt": "   "},
    )
    assert response.status_code == 422
    mock_manager.create.assert_not_called()


def test_create_job_accepts_prompt_without_image_type(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.return_value = ImageJobCreated(job_id="abcdef123456")
    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "test"},
    )
    assert response.status_code == 201
    mock_manager.create.assert_awaited_once_with("test")


def test_create_job_rejects_invalid_image_type(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.side_effect = ValueError("unknown image_type: 'invalid'")

    response = client.post(
        "/api/v1/image-jobs",
        json={"image_type": "invalid", "prompt": "test"},
    )
    assert response.status_code == 422


def test_create_job_returns_409_on_conflict(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.side_effect = JobConflictError("busy")

    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "test"},
    )
    assert response.status_code == 409


# ── GET /image-jobs/{job_id} ────────────────────────────────────────


def test_get_job_returns_status(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.get.return_value = ImageJobStatus(
        job_id="abcdef123456",
        image_type="science_poster",
        generation_route="fast",
        stage="completed",
        image_url="/api/v1/generated-images/abcdef123456.png",
        image_id="abcdef123456-v0",
    )

    response = client.get("/api/v1/image-jobs/abcdef123456")

    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == "abcdef123456"
    assert data["stage"] == "completed"
    assert data["image_type"] == "science_poster"
    assert data["generation_route"] == "fast"
    assert data["image_id"] == "abcdef123456-v0"


def test_get_job_returns_404_for_unknown_id(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.get.return_value = None

    response = client.get("/api/v1/image-jobs/nonexistent")

    assert response.status_code == 404


# ── DELETE /image-jobs/{job_id} ─────────────────────────────────────


def test_cancel_job_returns_200(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.cancel.return_value = True

    response = client.delete("/api/v1/image-jobs/abcdef123456")

    assert response.status_code == 200
    assert response.json()["detail"] == "任务已取消。"


def test_cancel_job_returns_404_when_not_found(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.cancel.return_value = False

    response = client.delete("/api/v1/image-jobs/nonexistent")

    assert response.status_code == 404


# ── POST /image-jobs/{job_id}/retry ─────────────────────────────────


def test_retry_job_returns_201(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.retry.return_value = ImageJobCreated(job_id="newjob000000")

    response = client.post("/api/v1/image-jobs/abcdef123456/retry")

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == "newjob000000"


def test_retry_job_returns_422_when_not_retryable(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.retry.return_value = None

    response = client.post("/api/v1/image-jobs/abcdef123456/retry")

    assert response.status_code == 422


def test_retry_job_returns_409_on_conflict(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.retry.side_effect = JobConflictError("busy")

    response = client.post("/api/v1/image-jobs/abcdef123456/retry")

    assert response.status_code == 409


def test_submit_bbox_edit_returns_202(client: TestClient, mock_manager: AsyncMock) -> None:
    mock_manager.edit.return_value = ImageJobCreated(job_id="abcdef123456")
    response = client.post("/api/v1/image-jobs/abcdef123456/edits", json={
        "target_image_id": "abcdef123456-v0",
        "bbox": [0.1, 0.2, 0.7, 0.8],
        "user_edit_request": "修改框内标题",
    })
    assert response.status_code == 202
    payload = mock_manager.edit.await_args.args[1]
    assert payload.bbox.root == [0.1, 0.2, 0.7, 0.8]


def test_submit_bbox_edit_rejects_invalid_bbox(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    response = client.post("/api/v1/image-jobs/abcdef123456/edits", json={
        "target_image_id": "abcdef123456-v0",
        "bbox": [0.7, 0.2, 0.1, 0.8],
        "user_edit_request": "修改框内标题",
    })
    assert response.status_code == 422
    mock_manager.edit.assert_not_awaited()


def test_submit_bbox_edit_surfaces_pixel_area_validation(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.edit.side_effect = InvalidBBoxError("框选区域过小")
    response = client.post("/api/v1/image-jobs/abcdef123456/edits", json={
        "target_image_id": "abcdef123456-v0",
        "bbox": [0.1, 0.1, 0.11, 0.11],
        "user_edit_request": "修改手势",
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "框选区域过小"


def test_accept_trusted_image(client: TestClient, mock_manager: AsyncMock) -> None:
    mock_manager.accept.return_value = True
    response = client.post("/api/v1/image-jobs/abcdef123456/accept")
    assert response.status_code == 200
    assert response.json() == {"job_id": "abcdef123456", "stage": "completed"}


# ── GET /generated-images/{filename} ────────────────────────────────


def test_get_generated_image_returns_file(
    client: TestClient, mock_manager: AsyncMock, tmp_path: Path
) -> None:
    """Serve a real PNG file from the configured generated_image_dir."""
    png = tmp_path / "test-image.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    app = create_app(Settings(dashscope_api_key=None, generated_image_dir=tmp_path))

    from app.api.routes.science_image_jobs import get_job_manager

    app.dependency_overrides[get_job_manager] = lambda: mock_manager

    with TestClient(app) as c:
        response = c.get("/api/v1/generated-images/test-image.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_get_generated_image_blocks_path_traversal(
    client: TestClient, mock_manager: AsyncMock, tmp_path: Path
) -> None:
    app = create_app(Settings(dashscope_api_key=None, generated_image_dir=tmp_path))

    from app.api.routes.science_image_jobs import get_job_manager

    app.dependency_overrides[get_job_manager] = lambda: mock_manager

    with TestClient(app) as c:
        response = c.get("/api/v1/generated-images/../../../etc/passwd")

    assert response.status_code == 404


def test_get_generated_image_returns_404_for_missing_file(
    client: TestClient, mock_manager: AsyncMock, tmp_path: Path
) -> None:
    app = create_app(Settings(dashscope_api_key=None, generated_image_dir=tmp_path))

    from app.api.routes.science_image_jobs import get_job_manager

    app.dependency_overrides[get_job_manager] = lambda: mock_manager

    with TestClient(app) as c:
        response = c.get("/api/v1/generated-images/nonexistent.png")

    assert response.status_code == 404


# ── Error sanitisation ──────────────────────────────────────────────


def test_error_response_does_not_leak_api_key(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.side_effect = RuntimeError("failed with sk-abc123secret")

    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "test"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "sk-" not in detail
    assert "abc123" not in detail


def test_error_response_does_not_leak_dashscope(
    client: TestClient, mock_manager: AsyncMock
) -> None:
    mock_manager.create.side_effect = RuntimeError("dashscope api_key leaked")

    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "test"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "api_key" not in detail.lower()
    assert "dashscope" not in detail.lower()
