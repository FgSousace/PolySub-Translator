from types import SimpleNamespace

from polysub.video import (
    VideoSubtitleImporter,
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
    assert format_media_duration(65) == "1 min 05 s"
    assert format_media_duration(3661) == "1 godz. 01 min 01 s"
