from pathlib import Path

from polysub.model_downloads import (
    IGNORED_MODEL_FILES,
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

