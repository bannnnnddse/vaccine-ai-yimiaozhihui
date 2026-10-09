"""Keep blocking image work owned by its task until the thread has exited."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def run_image_blocking(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        # Python cannot kill a running thread. Drain it before task cleanup removes
        # files or releases the single-operation slot, including repeated cancellation.
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not worker.cancelled():
            worker.exception()
        raise
