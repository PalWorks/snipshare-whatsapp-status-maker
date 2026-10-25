from datetime import date

import pytest

from wastatus import fetch
import threading

from wastatus.naming import build_stem, slugify

ON = date(2026, 8, 18)


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Sinna Sinna Murugaiyaa", "sinna-sinna-murugaiyaa"),
        ("Kandha Sashti Kavacham | Murugan", "kandha-sashti-kavacham-murugan"),
        ("Rick Astley - Never Gonna Give You Up", "rick-astley-never-gonna-give-you-up"),
        ("  spaces   everywhere  ", "spaces-everywhere"),
        ("Punctuation!!! ...here", "punctuation-here"),
    ],
)
def test_slug_is_lowercase_ascii_hyphenated(title, expected):
    assert slugify(title) == expected


def test_slug_never_exceeds_the_cap_and_cuts_on_a_word_boundary():
    slug = slugify("one two three four five six seven eight nine ten eleven")
    assert len(slug) <= 48
    assert not slug.endswith("-")
    assert slug.split("-")[-1] in {"one", "two", "three", "four", "five", "six",
                                   "seven", "eight", "nine", "ten", "eleven"}


def test_slug_survives_input_with_nothing_usable():
    assert slugify("!!!") == "clip"
    assert slugify("") == "clip"


def test_stem_leads_with_the_date_then_the_song():
    assert build_stem("Sinna Sinna Murugaiyaa", 70, 85, on=ON) == (
        "20260818_sinna-sinna-murugaiyaa_70-85"
    )


def test_video_mode_gets_its_own_stem():
    card = build_stem("Some Song", 70, 85, on=ON)
    video = build_stem("Some Song", 70, 85, video=True, on=ON)
    assert video != card
    assert video.endswith("_video")


def test_stem_is_human_readable_and_sorts_by_date():
    early = build_stem("B Song", 0, 15, on=date(2026, 1, 2))
    late = build_stem("A Song", 0, 15, on=date(2026, 11, 3))
    assert early < late


class TestArtistPreferredOverChannel:
    """An auto-generated music upload has a channel that says nothing.

    `Veyuru Tholipangan` is uploaded by `Release - Topic`, which cleans up to the
    meaningless `Release`, while its artist field says `Project Samskriti`.
    """

    def test_the_artist_field_wins(self):
        assert fetch._artist({"artist": "Project Samskriti"}) == "Project Samskriti"

    def test_the_artists_list_is_used_when_there_is_no_artist(self):
        assert fetch._artist({"artists": ["Project Samskriti"]}) == "Project Samskriti"

    def test_creator_is_the_last_resort(self):
        assert fetch._artist({"creator": "Yaazh Music"}) == "Yaazh Music"

    def test_nothing_known_means_the_channel_is_used(self):
        assert fetch._artist({}) == ""
        assert fetch._artist({"artists": []}) == ""

    def test_whitespace_is_trimmed(self):
        assert fetch._artist({"artist": "  Project Samskriti "}) == "Project Samskriti"


class TestClaimingAName:
    """T-017. A check that asks and does not act on the answer lets two renders
    that ask at the same moment agree on a name, and one overwrites the other.
    `reserve_stem` claims it instead."""

    STEM = "20260820_thiruppugazh_0-15"

    def test_a_free_name_is_returned_and_claimed(self, tmp_path):
        from wastatus.naming import reserve_stem

        assert reserve_stem(tmp_path, self.STEM) == self.STEM
        assert (tmp_path / f"{self.STEM}.mp4.part").exists(), "the name was not claimed"

    def test_the_claim_is_invisible_to_the_page(self, tmp_path):
        """The page lists `*.mp4`, so a claim must not look like a clip."""
        from wastatus.naming import reserve_stem

        reserve_stem(tmp_path, self.STEM)
        assert list(tmp_path.glob("*.mp4")) == []

    def test_a_second_claim_on_the_same_name_gets_the_next_one(self, tmp_path):
        from wastatus.naming import reserve_stem

        first = reserve_stem(tmp_path, self.STEM)
        second = reserve_stem(tmp_path, self.STEM)
        assert (first, second) == (self.STEM, f"{self.STEM}-2")

    def test_an_existing_clip_is_still_stepped_over(self, tmp_path):
        from wastatus.naming import reserve_stem

        (tmp_path / f"{self.STEM}.mp4").write_bytes(b"an earlier clip")
        assert reserve_stem(tmp_path, self.STEM) == f"{self.STEM}-2"

    def test_a_claim_left_behind_by_a_killed_render_blocks_that_name(self, tmp_path, caplog):
        """It shifts the name rather than overwriting, and says so, because a clip
        that quietly becomes `-2` is the kind of thing nobody notices."""
        from wastatus.naming import reserve_stem

        (tmp_path / f"{self.STEM}.mp4.part").write_bytes(b"")
        with caplog.at_level("WARNING"):
            assert reserve_stem(tmp_path, self.STEM) == f"{self.STEM}-2"
        assert "claimed by another render" in caplog.text

    def test_eight_at_once_get_eight_different_names(self, tmp_path):
        """The race the task is about, run for real rather than reasoned about."""
        from concurrent.futures import ThreadPoolExecutor

        from wastatus.naming import reserve_stem

        ready = threading.Barrier(8)

        def claim():
            ready.wait()                      # everybody asks in the same instant
            return reserve_stem(tmp_path, self.STEM)

        with ThreadPoolExecutor(max_workers=8) as pool:
            names = [future.result() for future in [pool.submit(claim) for _ in range(8)]]

        assert len(set(names)) == 8, f"two renders agreed on one name: {sorted(names)}"
