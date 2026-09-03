import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_trace_id: ContextVar[str] = ContextVar("trace_id", default="unscoped")


def current_trace_id() -> str:
    return _trace_id.get()


def set_trace_id(trace_id: str) -> Token[str]:
    return _trace_id.set(trace_id)


def reset_trace_id(token: Token[str]) -> None:
    _trace_id.reset(token)


@contextmanager
def timed_stage(logger: logging.Logger, stage: str, **fields: object) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except BaseException as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.warning(
            "stage trace_id=%s stage=%s outcome=error duration_ms=%.1f error_type=%s%s",
            current_trace_id(),
            stage,
            duration_ms,
            type(exc).__name__,
            _format_fields(fields),
        )
        raise
    else:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "stage trace_id=%s stage=%s outcome=success duration_ms=%.1f%s",
            current_trace_id(),
            stage,
            duration_ms,
            _format_fields(fields),
        )


def _format_fields(fields: dict[str, object]) -> str:
    if not fields:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in sorted(fields.items()))
