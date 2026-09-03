import logging

import torch

logger = logging.getLogger(__name__)


def configure_cpu_threads(num_threads: int, interop_threads: int) -> None:
    """Bound PyTorch CPU pools before the first model inference.

    PyTorch only permits changing the inter-op pool before parallel work starts,
    so a repeated or late call is intentionally non-fatal.
    """

    torch.set_num_threads(num_threads)
    try:
        torch.set_num_interop_threads(interop_threads)
    except RuntimeError:
        logger.warning(
            "PyTorch inter-op thread pool was already initialized; keeping existing value"
        )
    logger.info(
        "PyTorch CPU thread limits configured num_threads=%d interop_threads=%d",
        torch.get_num_threads(),
        torch.get_num_interop_threads(),
    )
