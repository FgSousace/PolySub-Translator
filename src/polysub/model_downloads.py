from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .translation_models import TranslationModelSpec

StatusCallback = Callable[[str], None]
Downloader = Callable[..., str]

IGNORED_MODEL_FILES = (
    "*.gguf",
    "*.h5",
    "*.msgpack",
    "*.onnx",
    "*.tflite",
    "*.ckpt",
    "flax_model*",
    "tf_model*",
    "rust_model.ot",
)


class ModelDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelStatus:
    installed: bool
    partial: bool
    size_bytes: int
    snapshot_path: Path | None
    cache_path: Path

    @property
    def status_label(self) -> str:
        if self.installed:
            return f"Pobrany · {format_bytes(self.size_bytes)}"
        if self.partial:
            return f"Nieukończony · {format_bytes(self.size_bytes)}"
        return "Niepobrany"


def default_model_cache_dir() -> Path:
    explicit = os.getenv("HF_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    hub_home = os.getenv("HF_HOME")
    if hub_home:
        return Path(hub_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def repo_cache_dir(
    model: TranslationModelSpec,
    *,
    cache_dir: Path | None = None,
) -> Path:
    cache_root = cache_dir or default_model_cache_dir()
    repo_folder = "models--" + model.repo_id.replace("/", "--")
    return cache_root / repo_folder


def model_status(
    model: TranslationModelSpec,
    *,
    cache_dir: Path | None = None,
) -> ModelStatus:
    repo_path = repo_cache_dir(model, cache_dir=cache_dir)
    snapshot = _latest_complete_snapshot(repo_path)
    size = _directory_size(repo_path) if repo_path.exists() else 0
    return ModelStatus(
        installed=snapshot is not None,
        partial=repo_path.exists() and snapshot is None and size > 0,
        size_bytes=size,
        snapshot_path=snapshot,
        cache_path=repo_path,
    )


def download_model(
    model: TranslationModelSpec,
    *,
    cache_dir: Path | None = None,
    status: StatusCallback | None = None,
    downloader: Downloader | None = None,
) -> Path:
    status = status or (lambda _message: None)
    cache_root = cache_dir or default_model_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    current = model_status(model, cache_dir=cache_root)
    _check_free_space(model, cache_root, current.size_bytes)
    status(
        f"Pobieranie {model.display_name} z oficjalnego repozytorium "
        f"{model.repo_id}. Przerwane pobieranie można później wznowić."
    )
    if downloader is None:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise ModelDownloadError(
                "W instalacji brakuje modułu huggingface_hub potrzebnego do pobierania modeli."
            ) from exc
        downloader = snapshot_download
    try:
        snapshot = Path(
            downloader(
                repo_id=model.repo_id,
                cache_dir=str(cache_root),
                ignore_patterns=list(IGNORED_MODEL_FILES),
                max_workers=4,
            )
        )
    except Exception as exc:
        raise ModelDownloadError(
            f"Nie udało się pobrać modelu {model.display_name}: {exc}"
        ) from exc
    if not _is_complete_snapshot(snapshot):
        refreshed = model_status(model, cache_dir=cache_root)
        snapshot = refreshed.snapshot_path or snapshot
    if not _is_complete_snapshot(snapshot):
        raise ModelDownloadError(
            f"Pobieranie {model.display_name} zakończyło się bez kompletu plików modelu."
        )
    status(f"Model {model.display_name} jest gotowy do użycia.")
    return snapshot


def remove_model(
    model: TranslationModelSpec,
    *,
    cache_dir: Path | None = None,
) -> int:
    cache_root = (cache_dir or default_model_cache_dir()).resolve()
    repo_path = repo_cache_dir(model, cache_dir=cache_root).resolve()
    if not repo_path.is_relative_to(cache_root):
        raise ModelDownloadError("Nieprawidłowa ścieżka pamięci modelu.")
    if not repo_path.exists():
        return 0
    size = _directory_size(repo_path)
    try:
        shutil.rmtree(repo_path)
    except OSError as exc:
        raise ModelDownloadError(
            "Nie udało się usunąć modelu. Zamknij trwające tłumaczenie i spróbuj ponownie."
        ) from exc
    return size


def format_bytes(size: int) -> str:
    value = float(max(size, 0))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if value < 1000 or unit == units[-1]:
            decimals = 0 if unit in {"B", "KB"} else 1
            return f"{value:.{decimals}f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def _latest_complete_snapshot(repo_path: Path) -> Path | None:
    snapshots = repo_path / "snapshots"
    if not snapshots.is_dir():
        return None
    preferred: list[Path] = []
    main_ref = repo_path / "refs" / "main"
    try:
        revision = main_ref.read_text(encoding="utf-8").strip()
    except OSError:
        revision = ""
    if revision:
        preferred.append(snapshots / revision)
    try:
        others = sorted(
            (path for path in snapshots.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        others = []
    preferred.extend(path for path in others if path not in preferred)
    return next((path for path in preferred if _is_complete_snapshot(path)), None)


def _is_complete_snapshot(snapshot: Path) -> bool:
    if not snapshot.is_dir() or not (snapshot / "config.json").is_file():
        return False
    weight_patterns = (
        "*.safetensors",
        "pytorch_model*.bin",
        "model*.bin",
    )
    return any(any(snapshot.glob(pattern)) for pattern in weight_patterns)


def _directory_size(path: Path) -> int:
    total = 0
    try:
        entries = path.rglob("*")
        for entry in entries:
            try:
                info = entry.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    except OSError:
        return total
    return total


def _check_free_space(model: TranslationModelSpec, cache_root: Path, existing_size: int) -> None:
    remaining = max(model.estimated_download_bytes - existing_size, 0)
    required = int(remaining * 1.05)
    try:
        free = shutil.disk_usage(cache_root).free
    except OSError:
        return
    if required > free:
        raise ModelDownloadError(
            f"Za mało miejsca na {model.display_name}. Potrzeba jeszcze około "
            f"{format_bytes(required)}, a wolne jest {format_bytes(free)}."
        )
