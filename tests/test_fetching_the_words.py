"""Asking the video what it is called, before the clip is made. D-064.

The two boxes on the page have always meant "leave me empty and the video answers
this". The answer only ever appeared in the finished pixels, so a title worth
correcting cost a whole render to find and another to fix. Fetch asks the same
question early.

The property that matters is that it is the **same** question. What Fetch puts in
the boxes comes back to `title_and_channel` as an override, and if the two paths
disagreed by so much as a stripped dash, pressing Fetch would quietly change the
card. So the test is not that the words look right: it is that fetching them and
then rendering with them lands exactly where rendering without them would have.
"""

from __future__ import annotations

import json

import pytest

from wastatus import fetch, pipeline


def source(title: str, channel: str = "Prince Rama Varma", artist: str = "",
           video_id: str = "1d_3JUY_UrM") -> fetch.Source:
    return fetch.Source(
        video_id=video_id, title=title, channel=channel, duration=300.0,
        watch_url=f"https://youtu.be/{video_id}", artist=artist,
    )


def job(**words) -> pipeline.Job:
    return pipeline.Job(url="https://youtu.be/1d_3JUY_UrM", start=0.0, end=15.0,
                        **words)


# Real shapes this tool meets: an upload with the noise it always carries, a
# romanised Tamil title, an auto-generated music upload whose channel says nothing
# and whose artist says everything, and a title that romanises to nothing at all.
VIDEOS = [
    source("Vara Leela Gana Lola | Prince Rama Varma (Official Video)"),
    source("விறல்மாறனைந்து", channel="Thevaram"),
    source("Thiruppavai", channel="M S Subbulakshmi - Topic",
           artist="M S Subbulakshmi"),
    source("🎵🎵🎵", channel="Some Channel"),
    source("Thevaram Vol I - Thevaram Vol II"),
]


class TestItIsTheSameQuestion:
    @pytest.mark.parametrize("video", VIDEOS, ids=lambda one: one.title[:24])
    def test_fetched_words_are_what_an_empty_pair_of_boxes_means(self, video):
        assert pipeline.words_from_video(video) == \
            pipeline.title_and_channel(job(), video)

    @pytest.mark.parametrize("video", VIDEOS, ids=lambda one: one.title[:24])
    def test_and_they_resolve_to_themselves_when_they_come_back(self, video):
        """The whole no-change promise. Fetch fills the boxes, so the next render
        is an override render rather than a "read it from the video" one, and the
        two have to produce the same card. `to_latin` runs over an override and
        `clean_title` over a fetch, and this is what pins them together."""
        title, channel = pipeline.words_from_video(video)
        assert pipeline.title_and_channel(
            job(title=title, channel=channel), video) == (title, channel)

    def test_an_override_still_wins_over_the_video(self):
        """Fetch is not a new way to lose what you typed on the next render."""
        assert pipeline.title_and_channel(
            job(title="Mine", channel="Also mine"), VIDEOS[0]) == ("Mine", "Also mine")

    def test_a_title_that_romanises_to_nothing_falls_back_to_the_channel(self):
        title, channel = pipeline.words_from_video(VIDEOS[3])
        assert title == channel == "Some Channel"


class TestTheProbeBehindIt:
    def test_a_probe_asked_for_by_hand_does_not_wait_five_minutes(self):
        """Somebody is watching a spinning icon. `RUN_TIMEOUT` is for a render,
        where the wait has already been paid for."""
        assert fetch.PROBE_TIMEOUT < fetch.RUN_TIMEOUT

    def test_the_timeout_reaches_yt_dlp(self, monkeypatch):
        seen = {}

        def spy(cmd, timeout=fetch.RUN_TIMEOUT):
            seen["timeout"] = timeout
            return json.dumps({"id": "abc123", "title": "T", "uploader": "C"})

        monkeypatch.setattr(fetch, "_run", spy)
        fetch.probe("https://youtu.be/abc123", timeout=9.0)
        assert seen["timeout"] == 9.0

    def test_a_render_still_gets_the_long_one(self, monkeypatch):
        """The default is the render's, so nothing that already called `probe`
        picked up a shorter patience without asking for it."""
        seen = {}

        def spy(cmd, timeout=fetch.RUN_TIMEOUT):
            seen["timeout"] = timeout
            return json.dumps({"id": "abc123", "title": "T", "uploader": "C"})

        monkeypatch.setattr(fetch, "_run", spy)
        fetch.probe("https://youtu.be/abc123")
        assert seen["timeout"] == fetch.RUN_TIMEOUT
