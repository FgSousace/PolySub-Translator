from pathlib import Path

import polysub.model_downloads as model_downloads
from polysub.model_downloads import (
    IGNORED_MODEL_FILES,
    configure_safe_huggingface_cache,
    download_model,
    model_status,
    remove_model,
    repo_cache_dir,
)
from polysub.translation_models import get_model_spec


def _write_snapshot(cache_dir: Path, revision: str = "test-revision") -> Path:
    model = get_model_spec("opus-en-pl")
    repo = repo_cache_dir(model, cache_dir=cache_dir)
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"model-weights")
    return snapshot


def test_model_status_finds_complete_huggingface_snapshot(tmp_path: Path) -> None:
    model = get_model_spec("opus-en-pl")
    snapshot = _write_snapshot(tmp_path)

    status = model_status(model, cache_dir=tmp_path)

    assert status.installed
    assert not status.partial
    assert status.snapshot_path == snapshot
    assert status.size_bytes > 0


def test_windows_downloads_default_to_huggingface_no_symlink_mode(monkeypatch) -> None:
    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS", raising=False)

    configure_safe_huggingface_cache(windows=True)

    assert model_downloads.os.environ["HF_HUB_DISABLE_SYMLINKS"] == "1"


def test_explicit_huggingface_symlink_setting_is_preserved(monkeypatch) -> None:
    monkeypatch.setenv("HF_HUB_DISABLE_SYMLINKS", "0")

    configure_safe_huggingface_cache(windows=True)

    assert model_downloads.os.environ["HF_HUB_DISABLE_SYMLINKS"] == "0"


def test_model_status_marks_incomplete_download(tmp_path: Path) -> None:
    model = get_model_spec("opus-en-pl")
    repo = repo_cache_dir(model, cache_dir=tmp_path)
    repo.mkdir(parents=True)
    (repo / "unfinished.tmp").write_bytes(b"partial")

    status = model_status(model, cache_dir=tmp_path)

    assert not status.installed
    assert status.partial


def test_download_uses_official_repo_and_ignores_other_weight_formats(tmp_path: Path) -> None:
    model = get_model_spec("opus-en-pl")
    calls = []

    def fake_downloader(**kwargs):
        calls.append(kwargs)
        return str(_write_snapshot(Path(kwargs["cache_dir"])))

    snapshot = download_model(model, cache_dir=tmp_path, downloader=fake_downloader)

    assert snapshot.is_dir()
    assert calls[0]["repo_id"] == model.repo_id
    assert calls[0]["max_workers"] == 4
    assert set(calls[0]["ignore_patterns"]) == set(IGNORED_MODEL_FILES)


def test_remove_model_only_removes_selected_repository(tmp_path: Path) -> None:
    model = get_model_spec("opus-en-pl")
    other = get_model_spec("opus-pl-en")
    _write_snapshot(tmp_path)
    other_repo = repo_cache_dir(other, cache_dir=tmp_path)
    other_repo.mkdir(parents=True)
    (other_repo / "keep.txt").write_text("keep", encoding="utf-8")

    removed = remove_model(model, cache_dir=tmp_path)

    assert removed > 0
    assert not repo_cache_dir(model, cache_dir=tmp_path).exists()
    assert (other_repo / "keep.txt").is_file()


def test_model_status_survives_windows_untrusted_mount_point(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model = get_model_spec("opus-en-pl")
    snapshot = _write_snapshot(tmp_path)
    config_path = snapshot / "config.json"
    original_is_file = Path.is_file
    recorded: list[tuple[str, str]] = []

    def fake_is_file(path: Path) -> bool:
        if path == config_path:
            raise OSError(448, "Nie można przejść przez niezaufany punkt instalacji")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(
        model_downloads,
        "_record_cache_error",
        lambda repo_id, detail: recorded.append((repo_id, detail)),
    )

    status = model_status(model, cache_dir=tmp_path)

    assert not status.installed
    assert status.partial
    assert status.cache_error is not None
    assert "448" in status.cache_error
    assert status.status_label == "Cache niedostępny · usuń i pobierz ponownie"
    assert recorded and recorded[0][0] == model.repo_id


def test_broken_preferred_snapshot_does_not_hide_a_valid_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model = get_model_spec("opus-en-pl")
    broken = _write_snapshot(tmp_path, revision="broken")
    repo = repo_cache_dir(model, cache_dir=tmp_path)
    valid = repo / "snapshots" / "valid"
    valid.mkdir(parents=True)
    (valid / "config.json").write_text("{}", encoding="utf-8")
    (valid / "model.safetensors").write_bytes(b"valid-weights")
    original_is_file = Path.is_file

    def fake_is_file(path: Path) -> bool:
        if path == broken / "config.json":
            raise OSError(448, "Nie można przejść przez niezaufany punkt instalacji")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(model_downloads, "_record_cache_error", lambda *_args: None)

    status = model_status(model, cache_dir=tmp_path)

    assert status.installed
    assert status.snapshot_path == valid
