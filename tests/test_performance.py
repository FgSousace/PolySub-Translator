from types import SimpleNamespace

from polysub.performance import (
    CpuAllocation,
    accelerator_batch_size,
    configure_thread_environment,
    configure_torch_threads,
    cpu_allocation,
    translation_batch_size,
)


def test_cpu_percentage_maps_to_logical_threads() -> None:
    assert cpu_allocation(25, logical_processors=16).threads == 4
    assert cpu_allocation(50, logical_processors=16).threads == 8
    assert cpu_allocation(75, logical_processors=16).threads == 12
    assert cpu_allocation(100, logical_processors=16).threads == 16


def test_cpu_allocation_is_clamped_and_never_returns_zero_threads() -> None:
    assert cpu_allocation(0, logical_processors=1) == CpuAllocation(1, 1, 1)
    assert cpu_allocation(200, logical_processors=8) == CpuAllocation(100, 8, 8)


def test_thread_environment_configures_common_cpu_backends(monkeypatch) -> None:
    for variable in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        monkeypatch.delenv(variable, raising=False)

    configure_thread_environment(CpuAllocation(75, 16, 12))

    assert all(
        __import__("os").environ[variable] == "12"
        for variable in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        )
    )


def test_torch_uses_selected_intraop_threads_and_one_interop_worker() -> None:
    calls = []
    torch = SimpleNamespace(
        set_num_threads=lambda value: calls.append(("intra", value)),
        set_num_interop_threads=lambda value: calls.append(("interop", value)),
    )

    configure_torch_threads(torch, CpuAllocation(100, 16, 16))

    assert calls == [("intra", 16), ("interop", 1)]


def test_translation_batch_grows_on_cpu_without_unbounded_memory_use() -> None:
    assert translation_batch_size(CpuAllocation(25, 16, 4), "cpu") == 4
    assert translation_batch_size(CpuAllocation(100, 16, 16), "cpu") == 16
    assert translation_batch_size(CpuAllocation(100, 64, 64), "cpu") == 16
    assert translation_batch_size(CpuAllocation(100, 16, 16), "cuda:0") == 32


def test_accelerator_batch_uses_free_vram_and_model_specific_guardrail() -> None:
    gib = 1024**3
    torch = SimpleNamespace(
        cuda=SimpleNamespace(mem_get_info=lambda: (14 * gib, 16 * gib)),
    )

    # Lightweight M2M100/OPUS-style cap can use a very wide batch on a 16 GB card.
    assert accelerator_batch_size(torch, "cuda:0", 16) == 64
    # Large 1.3B checkpoints keep their conservative catalog cap as a 4x guardrail.
    assert accelerator_batch_size(torch, "cuda:0", 4) == 16


def test_accelerator_batch_stays_bounded_when_vram_is_tight() -> None:
    gib = 1024**3
    torch = SimpleNamespace(
        cuda=SimpleNamespace(mem_get_info=lambda: (3 * gib, 8 * gib)),
    )

    assert accelerator_batch_size(torch, "cuda:0", 16) == 16
