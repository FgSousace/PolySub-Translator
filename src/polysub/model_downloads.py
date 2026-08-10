from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
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
    cache_error: str | None = None

    @property
    def status_label(self) -> str:
        if self.installed:
            return f"Pobrany · {format_bytes(self.size_bytes)}"
        if self.cache_error:
            return "Cache niedostępny · usuń i pobierz ponownie"
        if self.partial:
            return f"Nieukończony · {format_bytes(self.size_bytes)}"
        return "Niepobrany"


_RECORDED_CACHE_ERRORS: set[str] = set()


def configure_safe_huggingface_cache(*, windows: bool | None = None) -> None:
    """Avoid Windows reparse points that can trigger WinError 448.

    Recent huggingface_hub releases support an official no-symlink cache mode.
    Preserve an explicit user override, but default packaged/source Windows runs
    to ordinary files so a freshly downloaded model remains traversable.
    """

    if windows is None:
        windows = os.name == "nt"
    if windows:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")


configure_safe_huggingface_cache()


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
    errors: list[str] = []
    snapshot = _latest_complete_snapshot(repo_path, errors=errors)
    repo_exists = _safe_exists(repo_path, errors=errors)
    size = _directory_size(repo_path) if repo_exists else 0
    cache_error = errors[-1] if errors else None
    if cache_error:
        _record_cache_error(model.repo_id, cache_error)
    return ModelStatus(
        installed=snapshot is not None,
        partial=repo_exists and snapshot is None and (size > 0 or cache_error is not None),
        size_bytes=size,
        snapshot_path=snapshot,
        cache_path=repo_path,
        cache_error=cache_error,
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


def model_cache_log_path() -> Path:
    base = os.getenv("LOCALAPPDATA")
    parent = Path(base) / "PolySub Translator" if base else Path.home() / ".polysub-translator"
    return parent / "model-cache-diagnostics.log"


def _record_cache_error(repo_id: str, detail: str) -> None:
    key = f"{repo_id}: {detail}"
    if key in _RECORDED_CACHE_ERRORS:
        return
    _RECORDED_CACHE_ERRORS.add(key)
    try:
        path = model_cache_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as output:
            output.write(f"[{timestamp}] {key}\n")
    except OSError:
        pass


def _latest_complete_snapshot(
    repo_path: Path,
    *,
    errors: list[str] | None = None,
) -> Path | None:
    snapshots = repo_path / "snapshots"
    if not _safe_is_dir(snapshots, errors=errors):
        return None
    preferred: list[Path] = []
    main_ref = repo_path / "refs" / "main"
    try:
        revision = main_ref.read_text(encoding="utf-8").strip()
    except OSError:
        revision = ""
    if revision:
        preferred.append(snapshots / revision)
    others_with_mtime: list[tuple[float, Path]] = []
    try:
        entries = tuple(snapshots.iterdir())
    except OSError as exc:
        _append_path_error(errors, snapshots, exc)
        entries = ()
    for path in entries:
        if not _safe_is_dir(path, errors=errors):
            continue
        try:
            modified = path.stat().st_mtime
        except OSError as exc:
            _append_path_error(errors, path, exc)
            modified = 0.0
        others_with_mtime.append((modified, path))
    others = [path for _modified, path in sorted(others_with_mtime, reverse=True)]
    preferred.extend(path for path in others if path not in preferred)
    return next(
        (
            path
            for path in preferred
            if _is_complete_snapshot(path, errors=errors)
        ),
        None,
    )


def _is_complete_snapshot(
    snapshot: Path,
    *,
    errors: list[str] | None = None,
) -> bool:
    if not _safe_is_dir(snapshot, errors=errors) or not _safe_is_file(
        snapshot / "config.json",
        errors=errors,
    ):
        return False
    weight_patterns = (
        "*.safetensors",
        "pytorch_model*.bin",
        "model*.bin",
    )
    for pattern in weight_patterns:
        try:
            candidates = tuple(snapshot.glob(pattern))
        except OSError as exc:
            _append_path_error(errors, snapshot, exc)
            continue
        if any(_safe_is_file(candidate, errors=errors) for candidate in candidates):
            return True
    return False


def _safe_exists(path: Path, *, errors: list[str] | None = None) -> bool:
    try:
        return path.exists()
    except OSError as exc:
        _append_path_error(errors, path, exc)
        return False


def _safe_is_dir(path: Path, *, errors: list[str] | None = None) -> bool:
    try:
        return path.is_dir()
    except OSError as exc:
        _append_path_error(errors, path, exc)
        return False


def _safe_is_file(path: Path, *, errors: list[str] | None = None) -> bool:
    try:
        return path.is_file()
    except OSError as exc:
        _append_path_error(errors, path, exc)
        return False


def _append_path_error(
    errors: list[str] | None,
    path: Path,
    error: OSError,
) -> None:
    if errors is None:
        return
    message = f"{path}: {error}"
    if message not in errors:
        errors.append(message)


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
