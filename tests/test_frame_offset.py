import pytest

from wastatus.pipeline import frame_offset as _frame_offset
from wastatus.timecode import TimecodeError


def test_mid_is_the_middle_of_the_clip():
    assert _frame_offset("mid", 15.0) == 7.5
    assert _frame_offset("mid", 30.0) == 15.0


@pytest.mark.parametrize(
    "value,expected", [("0", 0.0), ("8", 8.0), ("0:08", 8.0), ("2.5", 2.5)]
)
def test_an_explicit_offset_is_honoured(value, expected):
    assert _frame_offset(value, 15.0) == expected


def test_an_offset_past_the_end_is_clamped_inside_the_clip():
    """ffmpeg writes an empty file rather than failing, so this must not pass through."""
    assert _frame_offset("30", 15.0) == pytest.approx(14.95)
    assert _frame_offset("15", 15.0) == pytest.approx(14.95)


@pytest.mark.parametrize("value", ["banana", "-5", "1:2:3:4", ""])
def test_junk_is_rejected_rather_than_guessed(value):
    """A negative offset is junk, not something to clamp. argparse would read it
    as a flag anyway."""
    with pytest.raises(TimecodeError):
        _frame_offset(value, 15.0)


def test_a_zero_length_clip_does_not_produce_a_negative_offset():
    assert _frame_offset("mid", 0.0) == 0.0
    assert _frame_offset("5", 0.0) == 0.0
