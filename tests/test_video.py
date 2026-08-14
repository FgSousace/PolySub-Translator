from types import SimpleNamespace

import pytest

from polysub.video import (
    VideoMuxError,
    VideoSubtitleBurner,
    VideoSubtitleImporter,
    VideoSubtitleMuxer,
    burned_video_output_path,
    fast_mux_output_path,
    format_media_duration,
    translated_video_subtitle_path,
)

SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Hello from the embedded track.
"""


def test_extracts_embedded_subtitles_before_loading_whisper(tmp_path, monkeypatch) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"video")

    def fake_run(command, **_kwargs):
        temporary = command[-1]
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(SAMPLE_SRT)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("polysub.video.subprocess.run", fake_run)

    def forbidden_model(*_args, **_kwargs):
        raise AssertionError("Whisper nie powinien uruchomić się dla wbudowanych napisów")

    result = VideoSubtitleImporter(
        ffmpeg_executable="ffmpeg",
        model_factory=forbidden_model,
    ).import_video(video)

    assert result.method == "embedded"
    assert result.subtitle_path == tmp_path / "movie.extracted.srt"
    assert result.document.cues[0].text == "Hello from the embedded track."


def test_transcribes_audio_when_video_has_no_text_subtitles(tmp_path, monkeypatch) -> None:
    video = tmp_path / "dialogue.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        "polysub.video.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr("polysub.performance.os.cpu_count", lambda: 16)

    words = [
        SimpleNamespace(start=0.5, end=0.9, word=" Hello"),
        SimpleNamespace(start=0.9, end=1.4, word=" world."),
    ]
    segment = SimpleNamespace(start=0.5, end=1.4, text=" Hello world.", words=words)
    info = SimpleNamespace(duration=10.0, language="en")

    class FakeModel:
        def transcribe(self, path, **kwargs):
            assert path == str(video)
            assert kwargs["task"] == "transcribe"
            assert kwargs["word_timestamps"] is True
            assert kwargs["beam_size"] == 7
            assert kwargs["patience"] == 1.2
            assert kwargs["vad_parameters"]["min_silence_duration_ms"] == 350
            assert kwargs["condition_on_previous_text"] is True
            return iter([segment]), info

    model_calls = []

    def model_factory(model_size, **kwargs):
        model_calls.append((model_size, kwargs))
        return FakeModel()

    updates = []
    statuses = []
    result = VideoSubtitleImporter(
        model_size="small",
        ffmpeg_executable="ffmpeg",
        model_factory=model_factory,
        cpu_usage_limit=50,
    ).import_video(
        video,
        progress=lambda done, total: updates.append((done, total)),
        status=statuses.append,
    )

    assert model_calls[0][0] == "small"
    assert model_calls[0][1]["device"] == "cpu"
    assert model_calls[0][1]["compute_type"] == "int8"
    assert model_calls[0][1]["cpu_threads"] == 8
    assert model_calls[0][1]["num_workers"] == 1
    assert result.method == "transcribed"
    assert result.detected_language == "en"
    assert result.subtitle_path == tmp_path / "dialogue.transcribed.srt"
    assert result.document.cues[0].timing == "00:00:00,500 --> 00:00:01,400"
    assert result.document.cues[0].text == "Hello world."
    assert updates[-1] == (1.4, 10.0)
    assert any("modelu Whisper small" in message for message in statuses)
    assert statuses[-1] == "Zapisywanie rozpoznanych napisów SRT..."


def test_transcription_uses_selected_gpu_index(tmp_path, monkeypatch) -> None:
    video = tmp_path / "gpu-dialogue.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        "polysub.video.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    segment = SimpleNamespace(start=0.0, end=1.0, text=" Test.", words=[])
    info = SimpleNamespace(duration=1.0, language="pl")
    calls = []

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return iter([segment]), info

    def model_factory(model_size, **kwargs):
        calls.append((model_size, kwargs))
        return FakeModel()

    VideoSubtitleImporter(
        model_size="small",
        ffmpeg_executable="ffmpeg",
        model_factory=model_factory,
        device="cuda:1",
    ).import_video(video)

    assert calls[0][1]["device"] == "cuda"
    assert calls[0][1]["device_index"] == 1
    assert calls[0][1]["compute_type"] == "float16"


def test_transcription_falls_back_to_cpu_after_gpu_error(tmp_path, monkeypatch) -> None:
    video = tmp_path / "fallback.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        "polysub.video.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    segment = SimpleNamespace(start=0.0, end=1.0, text=" Działa.", words=[])
    info = SimpleNamespace(duration=1.0, language="pl")
    calls = []

    class FakeModel:
        def __init__(self, device):
            self.device = device

        def transcribe(self, *_args, **_kwargs):
            if self.device == "cuda":
                raise RuntimeError("brak pamięci GPU")
            return iter([segment]), info

    def model_factory(_model_size, **kwargs):
        calls.append(kwargs)
        return FakeModel(kwargs["device"])

    statuses = []
    result = VideoSubtitleImporter(
        ffmpeg_executable="ffmpeg",
        model_factory=model_factory,
        device="cuda:0",
    ).import_video(video, status=statuses.append)

    assert [call["device"] for call in calls] == ["cuda", "cpu"]
    assert result.document.cues[0].text == "Działa."
    assert any("przełączanie" in status for status in statuses)


def test_video_output_name_and_readable_duration(tmp_path) -> None:
    assert translated_video_subtitle_path(tmp_path / "film.mp4", "PL") == tmp_path / "film.pl.srt"
    assert fast_mux_output_path(tmp_path / "film.mp4", "PL") == (
        tmp_path / "film.pl.subtitled.mp4"
    )
    assert fast_mux_output_path(tmp_path / "film.webm", "PL") == (
        tmp_path / "film.pl.subtitled.mkv"
    )
    assert burned_video_output_path(tmp_path / "film.mkv", "PL") == (
        tmp_path / "film.pl.burned.mp4"
    )
    assert format_media_duration(65) == "1 min 05 s"
    assert format_media_duration(3661) == "1 godz. 01 min 01 s"


def test_fast_mux_copies_video_and_audio_without_reencoding(tmp_path, monkeypatch) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"original video")
    subtitles = tmp_path / "movie.pl.srt"
    subtitles.write_text(SAMPLE_SRT, encoding="utf-8")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        temporary = command[-1]
        with open(temporary, "wb") as handle:
            handle.write(b"muxed video")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("polysub.video.subprocess.run", fake_run)
    statuses = []
    output = VideoSubtitleMuxer(ffmpeg_executable="ffmpeg").mux(
        video,
        subtitles,
        target_language="pl",
        subtitle_title="Polski",
        status=statuses.append,
    )

    command = commands[0]
    assert output == tmp_path / "movie.pl.subtitled.mp4"
    assert output.read_bytes() == b"muxed video"
    assert video.read_bytes() == b"original video"
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "mov_text"
    assert "title=Polski" in command
    assert statuses == [
        "Sprawdzanie filmu i przetłumaczonych napisów...",
        "Przygotowywanie programu FFmpeg...",
        "Kopiowanie obrazu, dźwięku i dołączanie ścieżki napisów...",
        "Finalizowanie pliku filmu...",
    ]


def test_fast_mux_uses_mkv_for_other_video_containers(tmp_path, monkeypatch) -> None:
    video = tmp_path / "movie.webm"
    video.write_bytes(b"video")
    subtitles = tmp_path / "movie.pl.srt"
    subtitles.write_text(SAMPLE_SRT, encoding="utf-8")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"muxed")
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("polysub.video.subprocess.run", fake_run)
    output = VideoSubtitleMuxer(ffmpeg_executable="ffmpeg").mux(
        video,
        subtitles,
        target_language="pl",
    )

    command = commands[0]
    assert output.suffix == ".mkv"
    assert command[command.index("-c:s") + 1] == "srt"


def test_fast_mux_removes_partial_file_when_ffmpeg_fails(tmp_path, monkeypatch) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"video")
    subtitles = tmp_path / "movie.pl.srt"
    subtitles.write_text(SAMPLE_SRT, encoding="utf-8")

    def fake_run(command, **_kwargs):
        with open(command[-1], "wb") as handle:
            handle.write(b"partial")
        return SimpleNamespace(returncode=1, stderr=b"unsupported stream")

    monkeypatch.setattr("polysub.video.subprocess.run", fake_run)

    with pytest.raises(VideoMuxError, match="unsupported stream"):
        VideoSubtitleMuxer(ffmpeg_executable="ffmpeg").mux(
            video,
            subtitles,
            target_language="pl",
        )

    assert not (tmp_path / "movie.pl.subtitled.mp4").exists()
    assert not (tmp_path / ".movie.pl.subtitled.tmp.mp4").exists()


def test_burn_falls_back_from_nvidia_to_cpu_and_reports_progress(
    tmp_path,
    monkeypatch,
) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"original video")
    subtitles = tmp_path / "movie.pl.srt"
    subtitles.write_text(SAMPLE_SRT, encoding="utf-8")
    monkeypatch.setattr("polysub.performance.os.cpu_count", lambda: 16)
    burner = VideoSubtitleBurner(
        ffmpeg_executable="ffmpeg",
        cpu_usage_limit=50,
    )
    monkeypatch.setattr(
        burner,
        "_available_encoders",
        lambda _ffmpeg: {"h264_nvenc", "libx264"},
    )
    monkeypatch.setattr(burner, "_probe_duration", lambda _ffmpeg, _video: 10.0)
    encoders = []
    progress_updates = []

    def fake_run(command, *, duration, progress):
        encoder = command[command.index("-c:v") + 1]
        encoders.append(encoder)
        progress(5.0, duration)
        if encoder == "h264_nvenc":
            return 1, "brak zgodnego urządzenia"
        with open(command[-1], "wb") as handle:
            handle.write(b"burned video")
        return 0, ""

    monkeypatch.setattr(burner, "_run_with_progress", fake_run)
    statuses = []
    result = burner.burn(
        video,
        subtitles,
        target_language="pl",
        preferred_vendor="NVIDIA",
        status=statuses.append,
        progress=lambda done, total: progress_updates.append((done, total)),
    )

    assert encoders == ["h264_nvenc", "libx264"]
    assert result.output_path == tmp_path / "movie.pl.burned.mp4"
    assert result.output_path.read_bytes() == b"burned video"
    assert result.encoder == "CPU (x264)"
    assert result.hardware_accelerated is False
    assert progress_updates[-1] == (10.0, 10.0)
    assert any("trybu CPU" in status for status in statuses)


def test_burn_uses_selected_hardware_encoder_and_cpu_thread_limit(
    tmp_path,
    monkeypatch,
) -> None:
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"video")
    subtitles = tmp_path / "movie.pl.srt"
    subtitles.write_text(SAMPLE_SRT, encoding="utf-8")
    monkeypatch.setattr("polysub.performance.os.cpu_count", lambda: 16)
    burner = VideoSubtitleBurner(
        ffmpeg_executable="ffmpeg",
        cpu_usage_limit=75,
    )
    monkeypatch.setattr(
        burner,
        "_available_encoders",
        lambda _ffmpeg: {"h264_nvenc", "h264_qsv", "libx264"},
    )
    monkeypatch.setattr(burner, "_probe_duration", lambda _ffmpeg, _video: 1.0)
    commands = []

    def fake_run(command, *, duration, progress):
        commands.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"gpu video")
        return 0, ""

    monkeypatch.setattr(burner, "_run_with_progress", fake_run)
    result = burner.burn(
        video,
        subtitles,
        target_language="pl",
        preferred_vendor="NVIDIA",
    )

    command = commands[0]
    assert command[command.index("-c:v") + 1] == "h264_nvenc"
    assert command[command.index("-filter_threads") + 1] == "12"
    assert "subtitles=filename=" in command[command.index("-vf") + 1]
    assert result.hardware_accelerated is True
    assert result.encoder == "NVIDIA NVENC"


def test_burn_respects_manual_cpu_choice() -> None:
    burner = VideoSubtitleBurner(ffmpeg_executable="ffmpeg")

    assert burner._encoder_candidates(
        {"h264_nvenc", "h264_qsv", "h264_amf", "libx264"},
        "CPU",
    ) == ["libx264"]
