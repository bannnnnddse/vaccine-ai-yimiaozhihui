import asyncio
import threading

import pytest

from app.services.image_worker import run_image_blocking


@pytest.mark.asyncio
async def test_cancel_drains_thread_before_returning_even_with_repeated_cancellation():
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()

    def work():
        entered.set()
        assert release.wait(2)
        exited.set()
        return "image"

    task = asyncio.create_task(run_image_blocking(work))
    assert await asyncio.to_thread(entered.wait, 1)
    try:
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert not exited.is_set()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert exited.is_set()


@pytest.mark.asyncio
async def test_blocking_worker_returns_values_and_preserves_failures():
    assert await run_image_blocking(lambda: 42) == 42

    def failure():
        raise ValueError("provider failed")

    with pytest.raises(ValueError, match="provider failed"):
        await run_image_blocking(failure)
