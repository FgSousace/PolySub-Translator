from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

CPU_USAGE_OPTIONS = (25, 50, 75, 100)
DEFAULT_CPU_USAGE = 100


@dataclass(frozen=True)
class CpuAllocation:
    percentage: int
    logical_processors: int
    threads: int

    @property
    def description(self) -> str:
        return (
            f"{self.percentage}% — {self.threads} z "
            f"{self.logical_processors} logicznych wątków"
        )


def cpu_allocation(
    percentage: int = DEFAULT_CPU_USAGE,
    *,
    logical_processors: int | None = None,
) -> CpuAllocation:
    normalized = max(1, min(int(percentage), 100))
    available = max(int(logical_processors or os.cpu_count() or 1), 1)
    threads = max(1, min(available, math.ceil(available * normalized / 100)))
    return CpuAllocation(normalized, available, threads)


def configure_thread_environment(allocation: CpuAllocation) -> None:
    value = str(allocation.threads)
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[variable] = value


def configure_torch_threads(torch_module: Any, allocation: CpuAllocation) -> None:
    configure_thread_environment(allocation)
    set_num_threads = getattr(torch_module, "set_num_threads", None)
    if callable(set_num_threads):
        set_num_threads(allocation.threads)

    # One model is executed at a time. A single inter-op worker prevents a second
    # thread pool from oversubscribing the CPU while intra-op uses the chosen cores.
    set_num_interop_threads = getattr(torch_module, "set_num_interop_threads", None)
    if callable(set_num_interop_threads):
        try:
            set_num_interop_threads(1)
        except RuntimeError:
            # PyTorch only permits changing this value before the first inter-op job.
            pass


def translation_batch_size(allocation: CpuAllocation, device: str) -> int:
    if device == "cpu":
        return max(1, min(allocation.threads, 16))
    # Accelerator engines refine this value after the model is loaded and free VRAM
    # can be queried. Keeping a much larger default than the historical 8 prevents
    # powerful GPUs from spending most of their time waiting between tiny batches.
    return 32


def accelerator_batch_size(
    torch_module: Any,
    device: str,
    model_batch_cap: int,
) -> int:
    """Choose an aggressive but bounded batch from free accelerator memory.

    ``model_batch_cap`` is the conservative catalog value used by older releases.
    On a GPU we allow up to 4x that value, capped at 64 cues. If the backend exposes
    ``mem_get_info`` we use the *free* VRAM after loading the model, which naturally
    accounts for large checkpoints. Engines additionally back off automatically on
    a real out-of-memory error, so this can aim high without aborting a translation.
    """

    conservative = max(int(model_batch_cap), 1)
    if device == "cpu":
        return conservative

    model_limit = min(conservative * 4, 64)
    candidate = min(32, model_limit)
    if not str(device).startswith("cuda"):
        return max(candidate, 1)

    try:
        free_bytes, _total_bytes = torch_module.cuda.mem_get_info()
        free_gib = float(free_bytes) / (1024**3)
    except Exception:
        return max(candidate, 1)

    if free_gib >= 12:
        candidate = 64
    elif free_gib >= 8:
        candidate = 48
    elif free_gib >= 4:
        candidate = 32
    elif free_gib >= 2:
        candidate = 16
    else:
        candidate = 8
    return max(1, min(candidate, model_limit))
