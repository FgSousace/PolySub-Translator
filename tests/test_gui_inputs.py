from polysub.gui import INPUT_FILE_TYPES, SUPPORTED_INPUT_EXTENSIONS
from polysub.video import VIDEO_EXTENSIONS


def test_file_picker_exposes_every_supported_input_and_all_files() -> None:
    assert SUPPORTED_INPUT_EXTENSIONS == {".srt", *VIDEO_EXTENSIONS}
    first_label, first_pattern = INPUT_FILE_TYPES[0]
    assert "Wszystkie obsługiwane" in first_label
    for extension in SUPPORTED_INPUT_EXTENSIONS:
        assert f"*{extension}" in first_pattern.split()
    assert INPUT_FILE_TYPES[-1] == ("Wszystkie pliki", "*.*")
