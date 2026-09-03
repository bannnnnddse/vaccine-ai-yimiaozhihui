import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import Settings

ADMIN_COOKIE_NAME = "vaccine_admin_session"


class AdminAuthError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdminSession:
    username: str
    csrf_token: str
    expires_at: int


def verify_admin_password(settings: Settings, username: str, password: str) -> bool:
    if not settings.admin_username or not settings.admin_password_hash:
        raise AdminAuthError("admin authentication is not configured")
    username_valid = hmac.compare_digest(username, settings.admin_username)
    try:
        password_valid = PasswordHasher().verify(settings.admin_password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        password_valid = False
    return username_valid and password_valid


def create_admin_session(settings: Settings) -> tuple[str, AdminSession]:
    if not settings.admin_username or not settings.admin_session_secret:
        raise AdminAuthError("admin authentication is not configured")
    expires_at = int(time.time()) + settings.admin_session_ttl_seconds
    session = AdminSession(
        username=settings.admin_username,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=expires_at,
    )
    payload = _encode_json({
        "username": session.username,
        "csrf": session.csrf_token,
        "exp": session.expires_at,
    })
    signature = hmac.new(
        settings.admin_session_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_b64encode(signature)}", session


def parse_admin_session(settings: Settings, token: str | None) -> AdminSession:
    if not settings.admin_username or not settings.admin_session_secret:
        raise AdminAuthError("admin authentication is not configured")
    if not token or "." not in token:
        raise AdminAuthError("invalid admin session")
    payload, encoded_signature = token.rsplit(".", 1)
    expected = hmac.new(
        settings.admin_session_secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        supplied = _b64decode(encoded_signature)
        data = json.loads(_b64decode(payload))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AdminAuthError("invalid admin session") from exc
    if not hmac.compare_digest(expected, supplied):
        raise AdminAuthError("invalid admin session")
    username_changed = data.get("username") != settings.admin_username
    expired = int(data.get("exp", 0)) < int(time.time())
    if username_changed or expired:
        raise AdminAuthError("invalid admin session")
    csrf = data.get("csrf")
    if not isinstance(csrf, str) or not csrf:
        raise AdminAuthError("invalid admin session")
    return AdminSession(settings.admin_username, csrf, int(data["exp"]))


def _encode_json(value: dict[str, object]) -> str:
    return _b64encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
