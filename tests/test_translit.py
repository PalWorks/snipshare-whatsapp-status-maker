import pytest

from difflib import SequenceMatcher

import wastatus.translit as translit
from wastatus.translit import clean_channel, clean_title, to_latin


def test_aksharamukha_is_available():
    """Guards the shim in translit.py. If this fails, Tamil titles degrade."""
    assert translit._ak is not None, (
        "aksharamukha did not import; Tamil titles will fall back to Unidecode. "
        "See RUNBOOK.md, Transliteration degraded."
    )


@pytest.mark.parametrize(
    "tamil,expected",
    [
        ("சின்ன சின்ன முருகையா", "Sinna Sinna Murugaiyaa"),
        ("கந்த சஷ்டி கவசம்", "Kandha Sashti Kavasam"),
        ("திருப்பாவை", "Thiruppaavai"),
        ("திருவாசகம்", "Thiruvaasagam"),
        ("வேல் முருகா", "Vel Murugaa"),
    ],
)
def test_tamil_is_transcribed_phonetically(tamil, expected):
    """Baseline from DECISIONS.md D-006. Letter mapping gives 'cinnnnnn'."""
    assert to_latin(tamil) == expected


def test_output_is_always_ascii():
    for text in ["சின்ன சின்ன முருகையா", "कन्द", "日本語", "Ünïcodé"]:
        assert to_latin(text).isascii()


def test_latin_titles_keep_their_own_casing():
    assert clean_title("Rick Astley - Never Gonna Give You Up") == (
        "Rick Astley - Never Gonna Give You Up"
    )
    assert clean_title("VARA LEELA") == "VARA LEELA"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Song Name (Official Video)", "Song Name"),
        ("Song Name (Official Music Video)", "Song Name"),
        ("Song Name [HD]", "Song Name"),
        ("Song Name [Lyrical]", "Song Name"),
        ("Song Name #tamil #devotional", "Song Name"),
        ("Song Name | Official", "Song Name"),
    ],
)
def test_upload_noise_is_stripped(raw, expected):
    assert clean_title(raw) == expected


def test_titles_repeated_once_per_script_are_collapsed():
    raw = "Kandha Sashti Kavacham | Murugan | கந்த சஷ்டி கவசம் | Original Full Video"
    assert clean_title(raw) == "Kandha Sashti Kavacham | Murugan"


def test_at_most_two_segments_survive():
    assert clean_title("One | Two | Three | Four").count("|") <= 1


def test_channel_topic_suffix_is_dropped():
    assert clean_channel("Some Artist - Topic") == "Some Artist"
    assert clean_channel("சதாசிவம் - Topic") == "Sadhaasivam"


def test_empty_input_is_survivable():
    assert to_latin("") == ""
    assert clean_title("") == ""
    assert clean_channel("") == ""


class TestSegmentDedupe:
    """Tamil uploads carry the same name twice, once per script.

    After transliteration the two spellings rarely match character for character:
    `போற்றித் திருத்தாண்டகம்` romanises as `Potrith Thiruththaandagam` next to the
    uploader's own `Potri Thiruthandagam`. Comparing phonetic skeletons catches
    what comparing letters cannot. Both cases below are real, from 2026-08-18.
    """

    def test_a_dash_separated_duplicate_is_dropped(self):
        assert translit.clean_title(
            "Potri Thiruthandagam - போற்றித் திருத்தாண்டகம் | Thevaram Vol II"
        ) == "Potri Thiruthandagam | Thevaram Vol II"

    def test_a_duplicate_with_a_bracketed_place_name_is_dropped(self):
        assert translit.clean_title(
            "Thiruppugazh viRalmAranaindhu  (thiruchchendhUr) - "
            "திருப்புகழ் விறல்மாரன் ஐந்து  (திருச்செந்தூர்)"
        ) == "Thiruppugazh Viralmaranaindhu (Thiruchchendhur)"

    def test_separators_survive_when_nothing_is_dropped(self):
        """Rewriting `A - B` as `A | B` would change a title that was fine."""
        assert translit.clean_title(
            "RAMANA MAHARSHI - ARUNACHALA SHIVA"
        ) == "RAMANA MAHARSHI - ARUNACHALA SHIVA"

    def test_a_dash_inside_a_word_is_not_a_separator(self):
        assert translit.clean_title(
            "Prince Rama Varma-VARA LEELA GANA LOLA"
        ) == "Prince Rama Varma-VARA LEELA GANA LOLA"

    def test_spelling_variants_of_one_name_are_one_name(self):
        """Near identical skeletons, not identical ones: `kavasam` vs `kavacam`."""
        assert translit.clean_title(
            "Kandha Sashti Kavasam | Kanda Sashti Kavacham"
        ) == "Kandha Sashti Kavasam"

    def test_numbers_are_not_collapsed(self):
        """`Part 1` and `Part 2` are different parts, not two spellings."""
        assert translit.clean_title("Thevaram Part 1 | Thevaram Part 2") == (
            "Thevaram Part 1 | Thevaram Part 2"
        )

    def test_roman_numerals_are_not_collapsed(self):
        """These score 0.92 on skeleton similarity and are different volumes."""
        assert translit.clean_title("Thevaram Vol I | Thevaram Vol II") == (
            "Thevaram Vol I | Thevaram Vol II"
        )

    def test_at_most_two_segments_are_kept(self):
        assert translit.clean_title("Alpha | Beta | Gamma") == "Alpha | Beta"


class TestCapitalisation:
    """Academic romanisation capitalises mid-word, which reads as broken."""

    def test_internal_capitals_are_normalised(self):
        assert translit._normalise_caps("viRalmAranaindhu") == "Viralmaranaindhu"

    def test_punctuation_is_preserved(self):
        assert translit._normalise_caps("(thiruchchendhUr)") == "(Thiruchchendhur)"

    def test_deliberate_all_caps_is_left_alone(self):
        assert translit._normalise_caps("ARUNACHALA SHIVA") == "ARUNACHALA SHIVA"

    def test_an_all_caps_run_beside_a_normal_one_survives(self):
        """The regression that judging whole words instead of runs introduced."""
        assert translit._normalise_caps("Varma-VARA") == "Varma-VARA"

    def test_short_camel_case_survives(self):
        assert translit._normalise_caps("YouTube iPhone") == "YouTube iPhone"

    def test_ordinary_titles_are_untouched(self):
        assert translit._normalise_caps("Sinna Sinna Murugaiyaa") == (
            "Sinna Sinna Murugaiyaa"
        )


class TestATitleThatIsEntirelyNoise:
    """T-008. `(Official Video)` is noise by every rule here except the one that
    matters, so stripping it leaves a blank line on the card."""

    @pytest.mark.parametrize(
        "raw", ["(Official Video)", "#shorts", "[HD]", "| Official", "(Lyrical)"]
    )
    def test_the_raw_title_is_kept_rather_than_nothing(self, raw):
        assert clean_title(raw).strip(), f"{raw!r} stripped to nothing"

    def test_a_title_with_something_left_still_loses_the_noise(self):
        """The fallback must not swallow the ordinary case."""
        assert clean_title("Song Name (Official Video)") == "Song Name"

    def test_a_title_that_romanises_to_nothing_still_comes_back_empty(self):
        """Which is what leaves `pipeline.card_text` to fall back to the channel."""
        assert clean_title("\N{CLAPPER BOARD}") == ""


class TestTheDuplicateThreshold:
    """T-009. `_SAME_NAME` is 0.85 because it worked on the titles to hand. These
    pin what it actually does, so moving it is a visible decision.

    The ratios are skeleton similarity, measured 2026-08-20.
    """

    SAME = [
        ("Potri Thiruthandagam", "Potrith Thiruththaandagam", 1.000),
        ("Bhaja Govindam", "Baja Govindham", 1.000),
        ("Sivapuranam", "Shivapuranam", 1.000),
        ("Kandha Sashti Kavasam", "Kanda Sasti Kavacham", 0.941),
        ("Thiruppugazh", "Thirupugal", 0.889),
        ("Vinayagar Agaval", "Vinayakar Ahaval", 0.857),
        ("Thevaram", "Devaram", 0.857),
    ]
    DIFFERENT = [
        ("Abirami Andhadhi", "Abirami Ammai", 0.833),
        ("Vinayagar Agaval", "Vinayagar Kavasam", 0.774),
        ("Kanda Sashti", "Kanda Sashti Kavasam", 0.741),
        ("Kandha Sashti Kavasam", "Kandha Guru Kavasam", 0.727),
        ("Thiruppugazh", "Thiruvasagam", 0.600),
    ]

    @pytest.mark.parametrize("one,other,ratio", SAME)
    def test_two_spellings_of_one_name_are_one_name(self, one, other, ratio):
        assert translit._same_name(one, other)

    @pytest.mark.parametrize("one,other,ratio", DIFFERENT)
    def test_two_different_names_stay_two(self, one, other, ratio):
        assert not translit._same_name(one, other)

    @pytest.mark.parametrize("one,other,ratio", SAME + DIFFERENT)
    def test_the_measured_ratios_are_still_what_they_were(self, one, other, ratio):
        """If a change to `_skeleton` moves a pair, this says which one and by how
        much, rather than leaving a threshold that no longer means what it did."""
        measured = SequenceMatcher(
            None, translit._skeleton(one), translit._skeleton(other)
        ).ratio()
        assert measured == pytest.approx(ratio, abs=0.001)

    def test_the_threshold_itself_is_pinned(self):
        assert translit._SAME_NAME == 0.85

    def test_no_threshold_separates_these_two_pairs(self):
        """The finding that matters, and the reason 0.85 is not worth tuning.

        `Abirami Andhadhi` and `Abhirami Anthathi` are one name spelled two ways and
        score **0.846**. `Sivapuranam` and `Sivapuram` are two different words and
        score **0.900**. A duplicate scoring lower than a non duplicate means no
        single number gets both right: lowering the threshold to catch the first
        keeps collapsing the second, and raising it to protect the second loses more
        real duplicates. The current 0.85 gets the second wrong and leaves the first
        alone, which is the safer of the two failures: a title that keeps both
        spellings is untidy, a title that loses a word is wrong.
        """
        duplicate = SequenceMatcher(
            None, translit._skeleton("Abirami Andhadhi"),
            translit._skeleton("Abhirami Anthathi"),
        ).ratio()
        distinct = SequenceMatcher(
            None, translit._skeleton("Sivapuranam"), translit._skeleton("Sivapuram")
        ).ratio()

        assert duplicate < distinct, "the overlap has closed, so the threshold is worth revisiting"
        assert not translit._same_name("Abirami Andhadhi", "Abhirami Anthathi")
        assert translit._same_name("Sivapuranam", "Sivapuram")

    def test_a_volume_number_still_protects_a_series(self):
        """The guard that already exists for exactly this reason."""
        assert not translit._same_name("Thevaram Vol I", "Thevaram Vol II")
        assert not translit._same_name("Thiruppugazh 1", "Thiruppugazh 2")
