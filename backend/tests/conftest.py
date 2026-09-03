"""Global test isolation from developer-local backend configuration."""

from app.core.config import Settings, get_settings


def pytest_configure() -> None:
    """Prevent backend/.env from changing unit-test defaults during collection."""
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
