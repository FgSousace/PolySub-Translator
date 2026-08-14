from __future__ import annotations

import os
import shutil
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
Downloader = Callable[..., str]


class DownloadableModelSpec(Protocol):
    id: str
    repo_id: str
    display_name: str
    estimated_download_bytes: int


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
    "*.mp3",
    "*.mp4",
    "*.wav",
    "*.flac",
)


class ModelDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelStatus:
    installed: bool
    partial: bool
    size_bytes: int
    downloaded_bytes: int
    snapshot_path: Path | None
    cache_path: Path
    cache_error: str | None = None

    @property
    def status_label(self) -> str:
        if self.installed:
            return f"Pobrany · {format_bytes(self.downloaded_bytes)}"
        if self.cache_error:
            return "Cache niedostępny · usuń i pobierz ponownie"
        if self.partial:
            return f"Nieukończony · {format_bytes(self.downloaded_bytes)}"
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
    model: DownloadableModelSpec,
    *,
    cache_dir: Path | None = None,
) -> Path:
    cache_root = cache_dir or default_model_cache_dir()
    repo_folder = "models--" + model.repo_id.replace("/", "--")
    return cache_root / repo_folder


def model_status(
    model: DownloadableModelSpec,
    *,
    cache_dir: Path | None = None,
) -> ModelStatus:
    repo_path = repo_cache_dir(model, cache_dir=cache_dir)
    errors: list[str] = []
    snapshot = _latest_complete_snapshot(repo_path, model=model, errors=errors)
    repo_exists = _safe_exists(repo_path, errors=errors)
    size = _directory_size(repo_path) if repo_exists else 0
    downloaded = _downloaded_cache_size(repo_path, model=model) if repo_exists else 0
    cache_error = errors[-1] if errors else None
    if cache_error:
        _record_cache_error(model.repo_id, cache_error)
    return ModelStatus(
        installed=snapshot is not None,
        partial=snapshot is None and (downloaded > 0 or cache_error is not None),
        size_bytes=size,
        downloaded_bytes=downloaded,
        snapshot_path=snapshot,
        cache_path=repo_path,
        cache_error=cache_error,
    )


def download_model(
    model: DownloadableModelSpec,
    *,
    cache_dir: Path | None = None,
    status: StatusCallback | None = None,
    progress: ProgressCallback | None = None,
    downloader: Downloader | None = None,
) -> Path:
    status = status or (lambda _message: None)
    progress = progress or (lambda _downloaded, _total: None)
    cache_root = cache_dir or default_model_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    current = model_status(model, cache_dir=cache_root)
    _check_free_space(model, cache_root, current.downloaded_bytes)
    status(
        f"Pobieranie {model.display_name} z oficjalnego repozytorium "
        f"{model.repo_id}. Przerwane pobieranie można później wznowić."
    )
    remote_size = _resolve_remote_size(model) if downloader is None else 0
    total_size = max(remote_size or model.estimated_download_bytes, 1)
    initial_downloaded = min(
        _downloaded_cache_size(current.cache_path, model=model),
        total_size,
    )
    progress(initial_downloaded, total_size)
    if downloader is None:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise ModelDownloadError(
                "W instalacji brakuje modułu huggingface_hub potrzebnego do pobierania modeli."
            ) from exc
        downloader = snapshot_download
    completed = threading.Event()
    monitor = threading.Thread(
        target=_monitor_download,
        args=(current.cache_path, model, total_size, initial_downloaded, completed, progress),
        daemon=True,
    )
    monitor.start()
    download_patterns = tuple(getattr(model, "download_patterns", ()) or ())
    download_options = {
        "repo_id": model.repo_id,
        "cache_dir": str(cache_root),
        "ignore_patterns": list(IGNORED_MODEL_FILES),
        "max_workers": 4,
    }
    if download_patterns:
        download_options["allow_patterns"] = list(download_patterns)
    try:
        snapshot = Path(downloader(**download_options))
    except Exception as exc:
        raise ModelDownloadError(
            f"Nie udało się pobrać modelu {model.display_name}: {exc}"
        ) from exc
    finally:
        completed.set()
        monitor.join(timeout=1.0)
    if not _is_complete_snapshot(snapshot, model=model):
        refreshed = model_status(model, cache_dir=cache_root)
        snapshot = refreshed.snapshot_path or snapshot
    if not _is_complete_snapshot(snapshot, model=model):
        raise ModelDownloadError(
            f"Pobieranie {model.display_name} zakończyło się bez kompletu plików modelu."
        )
    final_size = _downloaded_cache_size(
        repo_cache_dir(model, cache_dir=cache_root),
        model=model,
    )
    progress(min(max(final_size, total_size), total_size), total_size)
    status(f"Model {model.display_name} jest gotowy do użycia.")
    return snapshot


def remove_model(
    model: DownloadableModelSpec,
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


def format_download_progress(downloaded: int, total: int) -> str:
    safe_total = max(total, 1)
    safe_downloaded = min(max(downloaded, 0), safe_total)
    percent = safe_downloaded / safe_total * 100
    return f"{percent:.1f}% · {format_bytes(safe_downloaded)} / {format_bytes(safe_total)}"


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
    model: DownloadableModelSpec,
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
        (path for path in preferred if _is_complete_snapshot(path, model=model, errors=errors)),
        None,
    )


def _is_complete_snapshot(
    snapshot: Path,
    *,
    model: DownloadableModelSpec,
    errors: list[str] | None = None,
) -> bool:
    if not _safe_is_dir(snapshot, errors=errors):
        return False
    required_files = tuple(getattr(model, "required_files", ()) or ())
    if required_files:
        return all(_safe_is_file(snapshot / filename, errors=errors) for filename in required_files)
    if not _safe_is_file(snapshot / "config.json", errors=errors):
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


def _downloaded_cache_size(
    repo_path: Path,
    *,
    model: DownloadableModelSpec | None = None,
) -> int:
    required_files = tuple(getattr(model, "required_files", ()) or ()) if model else ()
    if required_files:
        completed_sizes = {filename: 0 for filename in required_files}
        snapshots = repo_path / "snapshots"
        if _safe_is_dir(snapshots):
            try:
                snapshot_paths = tuple(snapshots.iterdir())
            except OSError:
                snapshot_paths = ()
            for snapshot in snapshot_paths:
                if not _safe_is_dir(snapshot):
                    continue
                for filename in required_files:
                    candidate = snapshot / filename
                    if not _safe_is_file(candidate):
                        continue
                    try:
                        completed_sizes[filename] = max(
                            completed_sizes[filename],
                            candidate.stat().st_size,
                        )
                    except OSError:
                        continue
        # huggingface_hub writes resumable temporary files with this suffix.
        # Count their real on-disk growth without including completed historical
        # variants from a shared repository such as ResembleAI/chatterbox.
        incomplete_size = 0
        try:
            incomplete = tuple(repo_path.rglob("*.incomplete"))
        except OSError:
            incomplete = ()
        for candidate in incomplete:
            try:
                if candidate.is_file():
                    incomplete_size += candidate.stat().st_size
            except OSError:
                continue
        return sum(completed_sizes.values()) + incomplete_size
    blobs = repo_path / "blobs"
    if _safe_is_dir(blobs):
        size = _directory_size(blobs)
        if size:
            return size
    return _directory_size(repo_path)


def _monitor_download(
    repo_path: Path,
    model: DownloadableModelSpec,
    total_size: int,
    initial_downloaded: int,
    completed: threading.Event,
    progress: ProgressCallback,
) -> None:
    last_reported = initial_downloaded
    while not completed.wait(0.25):
        downloaded = min(_downloaded_cache_size(repo_path, model=model), total_size)
        downloaded = max(downloaded, last_reported)
        if downloaded != last_reported:
            progress(downloaded, total_size)
            last_reported = downloaded


def _resolve_remote_size(model: DownloadableModelSpec) -> int:
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(model.repo_id, files_metadata=True)
    except Exception:
        return 0
    allowed = tuple(getattr(model, "download_patterns", ()) or ())
    total = 0
    matched = 0
    unknown_size = False
    for sibling in getattr(info, "siblings", ()) or ():
        filename = str(getattr(sibling, "rfilename", "") or "")
        if not filename:
            continue
        if allowed and not any(fnmatch(filename, pattern) for pattern in allowed):
            continue
        if any(fnmatch(filename, pattern) for pattern in IGNORED_MODEL_FILES):
            continue
        matched += 1
        size = getattr(sibling, "size", None)
        if size is None:
            unknown_size = True
            continue
        try:
            total += max(int(size), 0)
        except (TypeError, ValueError):
            unknown_size = True
            continue
    return total if matched and total and not unknown_size else 0


def _check_free_space(
    model: DownloadableModelSpec,
    cache_root: Path,
    existing_size: int,
) -> None:
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
