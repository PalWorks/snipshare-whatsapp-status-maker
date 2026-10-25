"""Title normalisation: everything on the card renders in Latin script."""

from __future__ import annotations

import ast
import re
from difflib import SequenceMatcher
import unicodedata

try:
    from unidecode import unidecode as _unidecode
except ImportError:  # pragma: no cover - dependency is declared in requirements
    _unidecode = None

# aksharamukha still imports ast.Str, which went away in Python 3.12. The name is
# not used at runtime, so a shim is enough and keeps us on the current Python.
if not hasattr(ast, "Str"):  # pragma: no cover - depends on interpreter version
    ast.Str = str

try:
    from aksharamukha import transliterate as _ak
except Exception:  # noqa: BLE001 - any import failure falls back to unidecode
    _ak = None

TAMIL_RUN = re.compile(r"[஀-௿‌‍]+")

# Upload titles are noisy. These add nothing to a 15 second status card.
_NOISE = re.compile(
    r"""
      \s*[\(\[][^)\]]*(?:official|video|audio|lyric|lyrical|hd|4k|full\s*song|
        with\s*lyrics|music\s*video|remaster(?:ed)?)[^)\]]*[\)\]]
    | \s*\|\s*(?:official|hd|4k)\b.*$
    | \s*\#\w+
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _strip_marks(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )


def _tamil_to_latin(run: str) -> str:
    """Phonetic Tamil romanisation, the way Tamil speakers actually spell it."""
    if _ak is not None:
        try:
            out = _ak.process(
                "Tamil", "RomanReadable", run, pre_options=["TamilTranscribe"]
            )
            out = _strip_marks(out).replace("'", "")
            if out.strip():
                return out.title()
        except Exception:  # noqa: BLE001 - fall through to the generic path
            pass
    if _unidecode is not None:
        return _unidecode(run).title()
    return ""


def to_latin(text: str) -> str:
    """Transliterate any script to Latin and collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = TAMIL_RUN.sub(lambda m: _tamil_to_latin(m.group()), text)
    if _needs_transliteration(text):
        if _unidecode is None:
            raise RuntimeError("Unidecode is required to transliterate non-Latin text")
        text = _unidecode(text)
    return re.sub(r"\s+", " ", text).strip(" |-_")


def _needs_transliteration(text: str) -> bool:
    # Anything outside ASCII, accented Latin included. The Tamil path already
    # strips its own diacritics, so holding the whole pipeline to ASCII keeps the
    # invariant simple: captions, filenames and card text are all plain Latin.
    return not text.isascii()


def clean_title(title: str) -> str:
    """Strip upload noise, transliterate, drop repeated segments, fix the casing.

    Tamil uploads routinely carry the same name twice, once per script, which
    after transliteration reads as an accidental stutter.

    A title that is *entirely* noise strips to nothing: `(Official Video)` and
    `#shorts` are both noise by every rule here and the title by the only rule that
    matters. The raw title is kept in that case, because a silly line on the card
    beats a blank one, and the caller can fall back further still. See
    [TASKS.md](TASKS.md) T-008.
    """
    stripped = _NOISE.sub("", title or "").strip(" -|_")
    if not stripped:
        stripped = (title or "").strip()
    return _normalise_caps(_dedupe_segments(to_latin(stripped)))


# Consonant digraphs that romanisation schemes disagree about. Folding them, then
# dropping any remaining `h` and collapsing repeats, reduces two spellings of the
# same Tamil name to the same skeleton: `Potri Thiruthandagam` and
# `Potrith Thiruththaandagam` both become `potritirutandagam`.
_DIGRAPHS = (
    ("zh", "z"), ("ch", "c"), ("sh", "s"), ("th", "t"),
    ("dh", "d"), ("kh", "k"), ("gh", "g"), ("ph", "p"), ("bh", "b"),
)

# Segments are separated by a pipe, or by a dash with space around it. A dash
# without spaces is part of a word, as in `Varma-VARA`, and must not split.
_SEPARATOR = re.compile(r"(\s*\|\s*|\s+-\s+)")

_SAME_NAME = 0.85  # skeleton similarity above which two segments are one name

# Two segments that differ only by a number are different parts of a series, not
# two spellings of one name. `Thevaram Vol I` and `Thevaram Vol II` score 0.92 on
# skeleton similarity, and collapsing them would silently drop a volume.
_ROMAN = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|xi{0,3}|x)$")


def _skeleton(text: str) -> str:
    """A spelling-insensitive key for a romanised name."""
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    for digraph, single in _DIGRAPHS:
        key = key.replace(digraph, single)
    key = key.replace("h", "")
    # Collapse doubled letters only: `aa` and `tt` are spelling choices, while
    # `11` and `22` are different numbers.
    return re.sub(r"([a-z])\1+", r"\1", key)


def _ordinals(text: str) -> list[str]:
    """The digits and roman numerals in a segment, in order."""
    found = re.findall(r"\d+", text)
    found += [
        word for word in re.findall(r"[a-z]+", text.lower()) if _ROMAN.match(word)
    ]
    return found


def _same_name(one: str, other: str) -> bool:
    """Whether two segments are the same name spelled differently."""
    if _ordinals(one) != _ordinals(other):
        return False
    key, other_key = _skeleton(one), _skeleton(other)
    if key == other_key:
        return True
    return SequenceMatcher(None, key, other_key).ratio() >= _SAME_NAME


def _dedupe_segments(title: str, keep: int = 2) -> str:
    """Drop segments that are the same name spelled another way.

    Separators are preserved for the segments that survive, so a title where
    nothing was dropped comes out exactly as it went in. Rewriting `A - B` as
    `A | B` would be a gratuitous change to a title that was already fine.
    """
    parts = _SEPARATOR.split(title)
    if not parts:
        return title

    segments: list[tuple[str, str]] = [("", parts[0].strip())]
    for index in range(1, len(parts) - 1, 2):
        segments.append((parts[index], parts[index + 1].strip()))
    segments = [(sep, seg) for sep, seg in segments if seg]

    kept: list[tuple[str, str]] = []
    for separator, segment in segments:
        if any(_same_name(segment, other) for _, other in kept):
            continue
        kept.append((separator, segment))
        if len(kept) == keep:
            break
    if not kept:
        return title
    out = kept[0][1]
    for separator, segment in kept[1:]:
        out += (separator if separator.strip() else " | ") + segment
    return out


# Academic romanisation capitalises letters mid-word, as in `viRalmAranaindhu`,
# which reads as broken on a card. Each run of letters is judged on its own, not
# each whitespace separated word: `Varma-VARA` is two runs, one of them
# deliberately all caps, and judging the pair together mangled it into
# `Varma-Vara`. Only long runs are touched, so `YouTube` survives.
_CAPS_MIN_LENGTH = 8


def _normalise_caps(text: str) -> str:
    def fix(match: re.Match[str]) -> str:
        run = match.group()
        if len(run) < _CAPS_MIN_LENGTH or run.isupper():
            return run
        if not any(character.isupper() for character in run[1:]):
            return run
        return run.capitalize()

    return re.sub(r"[A-Za-z]+", fix, text)


def clean_channel(name: str) -> str:
    name = to_latin(name or "")
    return re.sub(r"\s*-\s*Topic$", "", name).strip()
