"""Keeping a clip inside the size WhatsApp will accept.

WhatsApp refuses media it will not take silently: the composer takes the file and
never opens its editor. The line was bisected against the real composer on
2026-08-20 with 90 second probes that differed only in size, and it is **10 MiB**:
10,452,278 bytes was accepted and 10,519,352 was refused, 33 kB either side of
10,485,760. Not the 16 MB the platform documents, and not a length limit.

So the bitrate ceiling comes from the duration, and the budget sits below the real
ceiling by more than the encoder's measured overshoot. See TASKS.md T-014.
"""

from __future__ import annotations

import pytest

from wastatus.pipeline import MAX_DURATION
from wastatus.render import (
    AUDIO_BITRATE,
    MAXRATE_CEILING,
    MAXRATE_FLOOR,
    PLATFORM_MAX_BYTES,
    SIZE_BUDGET_BYTES,
    video_maxrate,
)

# The largest file the composer was measured to accept, and the smallest it was
# measured to refuse, both at 90 seconds on 2026-08-20.
MEASURED_ACCEPTED_BYTES = 10_452_278
MEASURED_REFUSED_BYTES = 10_519_352

# A 9.5 MB budget produced 9,684,891 bytes at 90 seconds and 9,690,149 at 60. The
# budget sets a maxrate; it does not cap the file.
MEASURED_OVERSHOOT = 1.02


def estimated_bytes(duration: float) -> float:
    return (video_maxrate(duration) + AUDIO_BITRATE) * 1000 * duration / 8


@pytest.mark.parametrize("duration", [1, 5, 10, 15, 30, 45, 60, 75, 90])
def test_every_allowed_length_fits_under_the_measured_ceiling(duration):
    """With the encoder's overshoot included, because the budget is not a cap."""
    assert estimated_bytes(duration) * MEASURED_OVERSHOOT < PLATFORM_MAX_BYTES


def test_the_longest_allowed_clip_fits():
    assert estimated_bytes(MAX_DURATION) * MEASURED_OVERSHOOT < PLATFORM_MAX_BYTES


@pytest.mark.parametrize("duration", [1, 5, 10, 15, 30, 45, 60, 75, 90])
def test_every_allowed_length_stays_inside_a_size_that_was_accepted(duration):
    """The budget comes from sizes measured to work, not the documented limit."""
    assert estimated_bytes(duration) * MEASURED_OVERSHOOT <= MEASURED_ACCEPTED_BYTES


def test_short_clips_keep_the_quality_ceiling():
    """A 15 second clip is nowhere near the budget, so nothing is given up."""
    assert video_maxrate(15) == MAXRATE_CEILING


def test_the_budget_starts_biting_around_half_a_minute():
    assert video_maxrate(30) < MAXRATE_CEILING


def test_long_clips_are_limited_by_the_budget_not_the_ceiling():
    assert video_maxrate(60) < MAXRATE_CEILING
    assert video_maxrate(90) < video_maxrate(60)


def test_the_bitrate_never_falls_below_the_floor():
    """Even an absurd duration produces something watchable rather than mush."""
    assert video_maxrate(3600) == MAXRATE_FLOOR


def test_a_nonsense_duration_is_survivable():
    assert video_maxrate(0) == MAXRATE_CEILING
    assert video_maxrate(-5) == MAXRATE_CEILING


def test_the_budget_leaves_more_headroom_than_the_encoder_overshoots():
    """The failure this guards against: raising the budget to the ceiling itself,
    which the 2 percent overshoot would then carry straight over it, silently."""
    assert SIZE_BUDGET_BYTES * MEASURED_OVERSHOOT < PLATFORM_MAX_BYTES

    headroom = 1 - SIZE_BUDGET_BYTES / PLATFORM_MAX_BYTES
    assert headroom > (MEASURED_OVERSHOOT - 1) * 2, "less than twice the overshoot"


def test_the_ceiling_is_the_one_that_was_measured():
    """10 MiB exactly, bracketed by two probes 33 kB either side of it."""
    assert PLATFORM_MAX_BYTES == 10 * 1024 * 1024
    assert MEASURED_ACCEPTED_BYTES < PLATFORM_MAX_BYTES < MEASURED_REFUSED_BYTES


def test_the_duration_cap_matches_the_platform():
    """WhatsApp takes 90 seconds. The tool used to stop at 60."""
    assert MAX_DURATION == 90.0


class TestSilentAudioDoesNotKillARender:
    """`loudnorm` handed digital silence measures -inf, divides by it, and feeds the
    encoder NaN. The message names neither the filter nor the cause. A reel with the
    music stripped out is still a clip somebody wants, so the render is run again
    without that one filter rather than failing."""

    def test_the_chain_can_be_asked_for_without_levelling(self):
        from wastatus import render

        assert "loudnorm" in render._audio_chain(30)
        assert "loudnorm" not in render._audio_chain(30, normalise=False)
        # and everything else about it is the same
        assert "afade=t=in" in render._audio_chain(30, normalise=False)
        assert "afade=t=out" in render._audio_chain(30, normalise=False)

    def test_a_silent_render_is_run_again_without_it(self, monkeypatch):
        from wastatus import render

        tries = []

        def fails_on_silence(cmd):
            tries.append(cmd)
            if len(tries) == 1:
                raise render.RenderError(
                    "ffmpeg failed:\n  [aac] Input contains (near) NaN/+-Inf")

        monkeypatch.setattr(render, "_run", fails_on_silence)
        render._run_with_audio(lambda chain: ["ffmpeg", chain], 30)
        assert len(tries) == 2, "a silent clip was not tried again"
        assert "loudnorm" in tries[0][1] and "loudnorm" not in tries[1][1]

    def test_any_other_failure_is_still_a_failure(self, monkeypatch):
        """Only the one signature is retried. A missing file, a bad filter or a
        killed process must not be run twice and must not be swallowed."""
        from wastatus import render

        tries = []

        def always_fails(cmd):
            tries.append(cmd)
            raise render.RenderError("ffmpeg failed:\n  No such file or directory")

        monkeypatch.setattr(render, "_run", always_fails)
        with pytest.raises(render.RenderError, match="No such file"):
            render._run_with_audio(lambda chain: ["ffmpeg", chain], 30)
        assert len(tries) == 1

    def test_a_cancelled_render_is_never_retried(self, monkeypatch):
        """`proc.Cancelled` is not a `RenderError`, and a render somebody stopped
        must not quietly start again."""
        from wastatus import proc, render

        tries = []

        def cancelled(cmd):
            tries.append(cmd)
            raise proc.Cancelled()

        monkeypatch.setattr(render, "_run", cancelled)
        with pytest.raises(proc.Cancelled):
            render._run_with_audio(lambda chain: ["ffmpeg", chain], 30)
        assert len(tries) == 1
