import pytest

from wastatus.timecode import (
    TimecodeError,
    format_timecode,
    parse_timecode,
    start_from_url,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("93", 93.0),
        ("1:33", 93.0),
        ("01:33", 93.0),
        ("1:02:03", 3723.0),
        ("90.5", 90.5),
        ("0:00", 0.0),
        ("  1:33  ", 93.0),
        ("2:00:00", 7200.0),
    ],
)
def test_parse_accepts_every_documented_form(text, expected):
    assert parse_timecode(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "1:2:3:4", "1:", ":30", "1;33", "-5"])
def test_parse_rejects_junk(text):
    with pytest.raises(TimecodeError):
        parse_timecode(text)


def test_format_round_trips_through_parse():
    for seconds in (0, 7.5, 93, 3723.25):
        assert parse_timecode(format_timecode(seconds)) == pytest.approx(seconds)


def test_format_is_the_shape_ytdlp_wants():
    assert format_timecode(93) == "0:01:33.000"
    assert format_timecode(3723.5) == "1:02:03.500"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://youtu.be/x?t=90", 90),
        ("https://youtu.be/x?t=1m30s", 90),
        ("https://youtu.be/x?t=1h2m3s", 3723),
        ("https://youtu.be/x?t=45s", 45),
        ("https://www.youtube.com/watch?v=x&t=120", 120),
        ("https://youtu.be/x#t=30", 30),
    ],
)
def test_start_from_url_reads_the_t_parameter(url, expected):
    assert start_from_url(url) == expected


@pytest.mark.parametrize(
    "url", ["https://youtu.be/x", "https://youtu.be/x?v=1", "https://youtu.be/x?t="]
)
def test_start_from_url_returns_none_without_a_usable_t(url):
    assert start_from_url(url) is None
