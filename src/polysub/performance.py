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
    return 8
