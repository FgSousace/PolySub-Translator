from types import SimpleNamespace

import pytest

from polysub.video import (
    VideoMuxError,
    VideoSubtitleImporter,
    VideoSubtitleMuxer,
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
            return iter([segment]), info

    model_calls = []

    def model_factory(model_size, **kwargs):
        model_calls.append((model_size, kwargs))
        return FakeModel()

    updates = []
    result = VideoSubtitleImporter(
        model_size="small",
        ffmpeg_executable="ffmpeg",
        model_factory=model_factory,
    ).import_video(video, progress=lambda done, total: updates.append((done, total)))

    assert model_calls[0][0] == "small"
    assert model_calls[0][1]["device"] == "cpu"
    assert model_calls[0][1]["compute_type"] == "int8"
    assert result.method == "transcribed"
    assert result.detected_language == "en"
    assert result.subtitle_path == tmp_path / "dialogue.transcribed.srt"
    assert result.document.cues[0].timing == "00:00:00,500 --> 00:00:01,400"
    assert result.document.cues[0].text == "Hello world."
    assert updates[-1] == (1.4, 10.0)


def test_video_output_name_and_readable_duration(tmp_path) -> None:
    assert translated_video_subtitle_path(tmp_path / "film.mp4", "PL") == tmp_path / "film.pl.srt"
    assert fast_mux_output_path(tmp_path / "film.mp4", "PL") == (
        tmp_path / "film.pl.subtitled.mp4"
    )
    assert fast_mux_output_path(tmp_path / "film.webm", "PL") == (
        tmp_path / "film.pl.subtitled.mkv"
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
    output = VideoSubtitleMuxer(ffmpeg_executable="ffmpeg").mux(
        video,
        subtitles,
        target_language="pl",
        subtitle_title="Polski",
    )

    command = commands[0]
    assert output == tmp_path / "movie.pl.subtitled.mp4"
    assert output.read_bytes() == b"muxed video"
    assert video.read_bytes() == b"original video"
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-c:s") + 1] == "mov_text"
    assert "title=Polski" in command


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
