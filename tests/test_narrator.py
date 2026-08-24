import wave
from pathlib import Path
from types import SimpleNamespace

from polysub.narrator import (
    GIB,
    NARRATOR_PACE_BY_ID,
    ChatterboxNarrator,
    _NarratorWorker,
    build_narration_track,
    get_narrator_pace_profile,
    narrator_video_output_path,
    parse_srt_timing,
    recommended_narrator_worker_count,
)
from polysub.subtitles import SRTCue


def _write_clip(path, *, frames=2400, rate=24000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"\x01\x00" * frames)


def test_narration_track_inserts_silence_at_subtitle_timestamps(tmp_path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _write_clip(first)
    _write_clip(second)
    cues = (
        (SRTCue("1", "00:00:01,000 --> 00:00:02,000", "Pierwsza"), first),
        (SRTCue("2", "00:00:03,000 --> 00:00:04,000", "Druga"), second),
    )
    output = tmp_path / "narrator.wav"

    rate = build_narration_track(cues, output)

    assert rate == 24000
    with wave.open(str(output), "rb") as result:
        assert result.getnframes() == 3 * rate + 2400
        assert result.readframes(rate) == b"\0" * (rate * 2)


def test_narrator_paths_and_timestamps_are_stable(tmp_path) -> None:
    assert parse_srt_timing("01:02:03,500 --> 01:02:05,250") == (3723.5, 3725.25)
    assert narrator_video_output_path(tmp_path / "film.mp4") == (tmp_path / "film.pl.narrator.mkv")


def test_narrator_worker_ignores_dependency_logs_before_json(tmp_path) -> None:
    worker = _NarratorWorker(tmp_path / "python.exe", tmp_path / "model")
    worker.process = SimpleNamespace(
        stdout=iter(
            (
                "Loading checkpoint on CPU...\n",
                '{"library": "diagnostic"}\n',
                '{"ready": true, "sample_rate": 24000}\n',
            )
        )
    )

    payload = worker._read_payload()

    assert payload["ready"] is True
    assert worker._diagnostic_lines == [
        "Loading checkpoint on CPU...",
        '{"library": "diagnostic"}',
    ]


def test_narrator_worker_exposes_rocm_device_after_start(tmp_path, monkeypatch) -> None:
    script = tmp_path / "narrator_worker_entry.py"
    script.write_text("# test worker", encoding="utf-8")
    process = SimpleNamespace(
        stdout=iter(
            (
                '{"ready": true, "sample_rate": 24000, "device": "cuda:0", '
                '"requested_device": "cuda:0", "backend": "rocm", "fallback": null, '
                '"vram_total": 17179869184, "vram_free": 12884901888, '
                '"vram_reserved": 3221225472}\n',
            )
        ),
        stderr=iter(()),
    )
    monkeypatch.setattr("polysub.narrator.narrator_worker_script", lambda: script)
    monkeypatch.setattr("polysub.narrator.narrator_worker_environment", lambda _threads: {})
    monkeypatch.setattr("polysub.narrator.subprocess.Popen", lambda *_args, **_kwargs: process)

    worker = _NarratorWorker(tmp_path / "python.exe", tmp_path / "model")
    sample_rate = worker.start()

    assert sample_rate == 24000
    assert worker.backend == "rocm"
    assert worker.requested_device == "cuda:0"
    assert worker.active_device == "cuda:0"
    assert worker.last_fallback is None
    assert worker.vram_total == 16 * GIB
    assert worker.vram_free == 12 * GIB
    assert worker.vram_reserved == 3 * GIB


def test_narrator_worker_exposes_generation_fallback(tmp_path, monkeypatch) -> None:
    class FakeInput:
        def write(self, _value):
            return None

        def flush(self):
            return None

    output = tmp_path / "cue.wav"
    worker = _NarratorWorker(tmp_path / "python.exe", tmp_path / "model")
    worker.process = SimpleNamespace(stdin=FakeInput())
    worker.active_device = "cuda:0"

    def fake_payload():
        output.write_bytes(b"wav")
        return {
            "ok": True,
            "device": "cpu",
            "fallback": "HIP operation is not supported",
        }

    monkeypatch.setattr(worker, "_read_payload", fake_payload)

    fallback = worker.synthesize("Test", output)

    assert worker.active_device == "cpu"
    assert fallback == "HIP operation is not supported"
    assert worker.last_fallback == fallback


def test_narrator_mix_copies_video_and_mixes_quiet_original(tmp_path, monkeypatch) -> None:
    video = tmp_path / "film.mp4"
    narration = tmp_path / "voice.wav"
    subtitles = tmp_path / "film.pl.srt"
    output = tmp_path / "film.pl.narrator.mkv"
    video.write_bytes(b"video")
    _write_clip(narration)
    subtitles.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nTest.\n",
        encoding="utf-8",
    )
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if "-y" not in command:
            return SimpleNamespace(returncode=1, stderr="Stream #0:1: Audio: aac")
        with open(command[-1], "wb") as target:
            target.write(b"narrated")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("polysub.narrator.subprocess.run", fake_run)
    narrator = ChatterboxNarrator(ffmpeg_executable="ffmpeg")

    narrator._mix_video(
        "ffmpeg",
        video,
        narration,
        subtitles,
        output,
        original_volume=0.28,
    )

    mix_command = commands[-1]
    assert output.read_bytes() == b"narrated"
    assert mix_command[mix_command.index("-c:v") + 1] == "copy"
    filter_value = mix_command[mix_command.index("-filter_complex") + 1]
    assert "[0:a:0]volume=0.280" in filter_value
    assert "2:0" in mix_command
    assert "title=Polski lektor — Chatterbox V3" in mix_command


def test_narrator_pace_uses_free_gap_and_never_returns_to_old_135x(
    tmp_path,
    monkeypatch,
) -> None:
    clip = tmp_path / "voice.wav"
    _write_clip(clip, frames=48000)
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"fitted")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("polysub.narrator.subprocess.run", fake_run)
    narrator = ChatterboxNarrator(ffmpeg_executable="ffmpeg")
    cue = SRTCue("1", "00:00:01,000 --> 00:00:02,000", "Spokojnie")

    narrator._fit_clip(
        "ffmpeg",
        clip,
        cue,
        tmp_path,
        pace="comfortable",
        next_cue_start=4.0,
    )
    gap_tempo = float(commands[-1][commands[-1].index("-filter:a") + 1].split("=")[1])
    assert gap_tempo == NARRATOR_PACE_BY_ID["comfortable"].speech_rate

    narrator._fit_clip("ffmpeg", clip, cue, tmp_path, pace="comfortable")
    fitted_tempo = float(commands[-1][commands[-1].index("-filter:a") + 1].split("=")[1])
    assert fitted_tempo == NARRATOR_PACE_BY_ID["comfortable"].max_fit_speed
    assert fitted_tempo < 1.35


def test_narrator_worker_count_uses_detected_free_vram_conservatively() -> None:
    assert (
        recommended_narrator_worker_count(
            cue_count=30,
            active_device="cuda:0",
            vram_total=16 * GIB,
            vram_free=12 * GIB,
            vram_reserved=4 * GIB,
        )
        == 2
    )
    assert (
        recommended_narrator_worker_count(
            cue_count=30,
            active_device="cuda:0",
            vram_total=8 * GIB,
            vram_free=5 * GIB,
            vram_reserved=3 * GIB,
        )
        == 1
    )
    assert (
        recommended_narrator_worker_count(
            cue_count=30,
            active_device="cpu",
            vram_total=32 * GIB,
            vram_free=30 * GIB,
            vram_reserved=1 * GIB,
        )
        == 1
    )
    assert get_narrator_pace_profile("Spokojny — około 0,90× (zalecany)").id == (
        "comfortable"
    )
