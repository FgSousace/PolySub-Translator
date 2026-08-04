from polysub.gui import format_elapsed, recommended_window_size


def test_window_size_fits_common_small_screen() -> None:
    width, height = recommended_window_size(1366, 768)

    assert (width, height) == (1000, 688)
    assert width <= 1366
    assert height <= 768


def test_window_size_does_not_grow_past_desktop_target() -> None:
    assert recommended_window_size(3840, 2160) == (1000, 900)


def test_window_size_never_exceeds_tiny_screen() -> None:
    width, height = recommended_window_size(640, 480)

    assert width <= 640
    assert height <= 480


def test_elapsed_time_is_readable() -> None:
    assert format_elapsed(0) == "00:00:00"
    assert format_elapsed(3661.9) == "01:01:01"
