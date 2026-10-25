"""The download ladders.

Order is not cosmetic: every entry before the one that works is a failed yt-dlp run
the person waits through, and a warning in the log that reads like a problem.
"""

from __future__ import annotations

import json

import pytest

from wastatus import fetch


class TestTheLadders:
    def test_audio_leads_with_the_one_that_works(self):
        assert fetch.STRATEGIES_AUDIO[0] == ("mweb", "18")

    def test_video_leads_with_the_hd_renditions(self):
        """T-018. `default` serves HLS renditions that carry their own audio and can
        be section downloaded, measured 2026-08-20: a 5 second cut of format 95 came
        back 1280x720 h264 with aac, 1.79 MB, in 7.8 seconds. Video mode was 360p
        until then."""
        assert fetch.STRATEGIES_VIDEO[0] == ("default", "95/96")

    def test_the_360p_floor_is_still_underneath_it(self):
        """Not every video has HLS renditions: one of the two tried on 2026-08-20
        had none. The one that always works has to stay in the ladder."""
        assert ("mweb", "18") in fetch.STRATEGIES_VIDEO

    def test_the_dead_hls_ladder_is_last_not_first(self):
        """web_safari returned storyboards and nothing else on 2026-08-19, and had
        been failing on every video-mode run since. It stays as a probe in case
        YouTube restores it."""
        assert fetch.STRATEGIES_VIDEO[-1][0] == "web_safari"

    def test_nothing_asks_for_a_merge(self):
        """A format expression with a + in it cannot be section downloaded: ffmpeg
        fetches the parts itself, and googlevideo answers ffmpeg with 403. That is
        why video mode is capped at 360p. See LIMITATIONS.md."""
        for ladder in (fetch.STRATEGIES_AUDIO, fetch.STRATEGIES_VIDEO):
            assert not any("+" in fmt for _, fmt in ladder)

    def test_every_client_appears_once(self):
        for ladder in (fetch.STRATEGIES_AUDIO, fetch.STRATEGIES_VIDEO):
            clients = [client for client, _ in ladder]
            assert len(clients) == len(set(clients))


class TestAPlaylistIsRefused:
    """T-027. A playlist link used to be accepted and produce a dead caption link.

    `probe` took the playlist's id as the video id, so `watch_url` came out as
    `https://youtu.be/PL...`, which resolves to nothing, and that url is the caption
    that goes out with the Status. Measured on 2026-08-21 against a live playlist.
    """

    def _probe(self, monkeypatch, payload):
        monkeypatch.setattr(fetch, "_run", lambda _cmd, timeout=None: json.dumps(payload))
        return fetch.probe("https://www.youtube.com/playlist?list=PLbpi")

    def test_a_playlist_is_refused_rather_than_turned_into_a_dead_link(self, monkeypatch):
        with pytest.raises(fetch.FetchError) as raised:
            self._probe(monkeypatch, {
                "_type": "playlist",
                "id": "PLbpi6ZahtOH6Blw3RGYpWkSByi_T7Rygb",
                "title": "Top Trending Videos of the Week",
                "entries": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            })
        said = str(raised.value)
        assert "playlist" in said
        assert "Top Trending Videos of the Week" in said, "it should name what was pasted"
        assert "3 tracks" in said, "and how big it is"
        assert "Share on the track" in said, "and what to do instead"

    def test_a_playlist_without_a_title_is_still_refused(self, monkeypatch):
        with pytest.raises(fetch.FetchError, match="not one track"):
            self._probe(monkeypatch, {"_type": "playlist", "id": "PL1", "entries": []})

    def test_entries_alone_are_enough_to_refuse(self, monkeypatch):
        """Some extractors return the entries without labelling the type."""
        with pytest.raises(fetch.FetchError, match="playlist"):
            self._probe(monkeypatch, {"id": "PL1", "title": "x", "entries": [{"id": "a"}]})

    def test_an_ordinary_track_is_untouched(self, monkeypatch):
        monkeypatch.setattr(fetch, "_run", lambda _cmd, timeout=None: json.dumps({
            "_type": "video",
            "id": "n_VSKDuxDF0",
            "title": "Veyuru Tholipangan",
            "uploader": "Release - Topic",
            "artist": "Project Samskriti",
            "duration": 393.0,
        }))
        source = fetch.probe("https://music.youtube.com/watch?v=n_VSKDuxDF0")
        assert source.video_id == "n_VSKDuxDF0"
        assert source.watch_url == "https://youtu.be/n_VSKDuxDF0"
        assert source.artist == "Project Samskriti"

    def test_a_track_with_no_type_at_all_is_untouched(self, monkeypatch):
        monkeypatch.setattr(fetch, "_run", lambda _cmd, timeout=None: json.dumps({
            "id": "abc123", "title": "A song", "duration": 200.0,
        }))
        assert fetch.probe("https://youtu.be/abc123").video_id == "abc123"
