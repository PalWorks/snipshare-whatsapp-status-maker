"""The sticker library, and placing stickers on a frame.

Stickers are pixels, like the card's wording, so they are pasted by Pillow and
composited by ffmpeg along with everything else. `compose` calls `paste`; the page
calls `search` and `resolve`.

**Coordinates are fractions of the frame**, not pixels: `x` and `y` are the
sticker's centre and `size` is its width, each between 0 and 1. That is what lets
the browser drag a sticker over a 296 pixel preview and the renderer paste it onto a
1620 pixel canvas with no scale factor passed between them, and no second layout
engine to drift. See DECISIONS.md D-024.

Two words, deliberately: **stickers** is the library, and **decals** is the ones
placed on one frame. `Job.decals`, `compose(decals=...)`. Everything a person reads
says stickers.

The library itself is not in the repo. `scripts/setup_stickers.sh` downloads
OpenMoji, the same way the PO token provider is installed, and uploads land beside
it.
"""

from __future__ import annotations

import base64
import binascii
import contextvars
import io
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageSequence, UnidentifiedImageError

from . import freetext

log = logging.getLogger("wastatus")

# `openmoji:1F64F`, `mine:my-cat`, `gif:giphy-abc123`. No dots and no slashes, so
# an id can never address anything outside its own directory.
STICKER_ID = re.compile(r"^(openmoji|mine|gif):([A-Za-z0-9_-]{1,64})$")

# How many picked GIFs are kept. They arrive by browsing rather than by choosing to
# keep them, so an unbounded folder would be full of things nobody meant to save.
# Twenty is `keep_last`'s number for clips, and for the same reason: it is about as
# far back as anybody reaches for something they used before. See D-043.
GIF_KEEP = 20
SAFE_NAME = re.compile(r"^[A-Za-z0-9 _-]{1,60}$")

SEARCH_LIMIT = 60
# The sizes the page asks for: a shelf cell at twice the pixel density, and one
# step up for anything wanting a sharper copy without the whole drawing. Only these,
# so a caller cannot fill the disk with one image at a thousand sizes.
THUMB_WIDTHS = (96, 192)
UPLOAD_MAX_BYTES = 2_000_000
UPLOAD_MAX_EDGE = 2048  # anything larger is a photo, not a sticker

# An animated sticker is a different size of thing, and the numbers below are what
# keeps one from becoming a second video. A GIF off a phone's clipboard is routinely
# a few megabytes where a drawing is a few tens of kilobytes, so it gets its own
# ceiling; and it is pasted at a fraction of a 1080 pixel frame, so nothing above
# 720 pixels an edge can ever be seen.
ANIMATED_MAX_BYTES = 8_000_000
ANIMATED_MAX_EDGE = 720
ANIMATED_MAX_FRAMES = 240   # 20 seconds at 12 fps, well past a Status

# Animated stickers are stored as GIF, and the reason is measured rather than
# stylistic: ffmpeg 8.0.1 on this machine reads an animated GIF and refuses an
# animated WebP outright, `image data not found`. Pillow reads both. So Pillow is
# the doorman and GIF is the only animated form that reaches the disk. See
# MEMORY.md Table ME-5.
ANIMATED_SUFFIX = ".gif"

# What a new sticker arrives as: a fifth of the frame's width, in the middle of the
# space above the caption band.
DEFAULT_SIZE = 0.2
DEFAULT_X = 0.5
DEFAULT_Y = 0.45

MIN_SIZE, MAX_SIZE = 0.03, 1.0


@dataclass
class Sticker:
    """One placed sticker. Fractions of the frame, centre anchored."""

    id: str
    x: float = DEFAULT_X
    y: float = DEFAULT_Y
    size: float = DEFAULT_SIZE
    rotation: float = 0.0

    kind = "sticker"

    @property
    def label(self) -> str:
        """What the run record calls it."""
        return self.id

    @property
    def moving(self) -> bool:
        return motion(self.id)

    @property
    def aspect(self) -> float:
        """Height over width. OpenMoji drawings are square and this says so.

        A GIF need not be, and this has always answered as though it were: the one
        thing it is used for is the "WhatsApp will draw over this" warning, where
        being approximately right in the vertical is the whole requirement.
        """
        return 1.0

    def art(self, width: int) -> Image.Image | None:
        """The drawing, `width` pixels across. None when it cannot be drawn.

        Never raises: a sticker that has gone missing from the machine, or a file
        that turns out not to be an image, must not take a render down with it.
        """
        file = resolve(self.id)
        if file is None:
            log.warning("sticker %s is not on this machine, skipping", self.id)
            return None
        try:
            art = Image.open(file).convert("RGBA")
        except (UnidentifiedImageError, OSError):
            log.warning("sticker %s could not be opened, skipping", self.id)
            return None
        height = max(1, round(width * art.height / art.width))
        return art.resize((width, height), Image.LANCZOS)

    def as_json(self) -> dict:
        return {
            "id": self.id,
            "x": round(self.x, 5),
            "y": round(self.y, 5),
            "size": round(self.size, 5),
            "rotation": round(self.rotation, 2),
        }


# One placed thing: a drawing off the shelf, or a line you wrote. Both are a
# rectangle at a fraction of the frame with an `art` to paste into it, which is the
# whole of what anything downstream of here needs to know about either. See
# `freetext` for why the line is drawn by Pillow rather than by the browser.
Placed = Sticker | freetext.FreeText


def parse(raw: object) -> Placed:
    """Turn one item from a request or a job sidecar into a placed thing.

    A drawing off the shelf, or a line of free text: they are told apart by `kind`,
    and by what they carry when an older sidecar has no `kind` in it.

    Raises `ValueError` on anything that is not placeable, so a bad id never reaches
    the filesystem and a bad number never reaches Pillow.
    """
    if not isinstance(raw, dict):
        raise ValueError("a sticker has to be an object")

    def number(key: str, default: float, low: float, high: float) -> float:
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} has to be a number") from exc
        if value != value:  # NaN, which would survive both comparisons below
            raise ValueError(f"{key} has to be a number")
        return min(max(value, low), high)

    kind = str(raw.get("kind") or ("text" if "text" in raw else "sticker"))
    if kind == "text":
        return freetext.parse(raw, number, min_size=MIN_SIZE, max_size=MAX_SIZE)

    sticker_id = str(raw.get("id") or "")
    if not STICKER_ID.match(sticker_id):
        raise ValueError(f"not a sticker id: {sticker_id!r}")
    return Sticker(
        id=sticker_id,
        # Placement is clamped rather than rejected: a sticker half off the frame is
        # a choice, a sticker at x=900 is a bug in whatever sent it.
        x=number("x", DEFAULT_X, -0.5, 1.5),
        y=number("y", DEFAULT_Y, -0.5, 1.5),
        size=number("size", DEFAULT_SIZE, MIN_SIZE, MAX_SIZE),
        rotation=number("rotation", 0.0, -180.0, 180.0),
    )


def parse_all(raw: object) -> list[Placed]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise ValueError("stickers have to be a list")
    if len(raw) > 20:
        raise ValueError("twenty stickers on one frame is already too many")
    return [parse(item) for item in raw]


# -- where the library lives ----------------------------------------------

def install_dir() -> Path:
    override = os.environ.get("WASTATUS_STICKER_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":  # pragma: no cover - not the test platform
        return Path.home() / "Library" / "Application Support" / "wastatus" / "stickers"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "wastatus" / "stickers"


# Whose stickers these are. The local tool has one person and leaves this unset.
# The hosted page sets it to the person's own folder for the length of a request or
# a render, so their uploads, picked GIFs and thumbnails never mix with anybody
# else's; the OpenMoji library itself stays shared. D-087.
personal: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "stickers_personal", default=None)


def _own() -> Path:
    return personal.get() or install_dir()


def library_dir() -> Path:
    return install_dir() / "openmoji"


def uploads_dir() -> Path:
    return _own() / "mine"


def gifs_dir() -> Path:
    """Picked GIFs. Kept, but pruned: a rolling recent set, not a library.

    Separate from `mine` on purpose. An upload is something you decided to have;
    a picked GIF is something you passed through. Mixing them would mean either
    pruning things you meant to keep, or keeping everything you ever scrolled past.
    """
    return _own() / "gifs"


def cache_dir() -> Path:
    """Scaled copies. Derived files only: deleting this folder costs nothing."""
    return _own() / "cache"


def installed() -> bool:
    return (install_dir() / "openmoji.json").is_file() and library_dir().is_dir()


def install_hint() -> str:
    return (
        "the sticker library is not installed. Run bash scripts/setup_stickers.sh "
        "once, which downloads about 45 MB of OpenMoji drawings"
    )


def thumbnail(sticker_id: str, width: int) -> Path | None:
    """A scaled copy of a sticker, made once and then kept.

    The picker draws 618 pixel artwork in 44 pixel cells. Measured on 2026-08-19,
    the opening shelf of 40 costs 402 kB at full size and 191 kB at `w=96`: a 52
    percent saving rather than the order of magnitude TASKS.md T-020 guessed at,
    because flat OpenMoji artwork already compresses well. Worth having over a phone
    connection, and free after the first paint, but it is a halving and not a cure.

    Only the widths the page actually asks for are made, so a caller cannot fill the
    disk with one image at a thousand sizes.
    """
    if width not in THUMB_WIDTHS:
        return None
    source = resolve(sticker_id)
    if source is None:
        return None

    kind, name = sticker_id.split(":", 1)
    cached = cache_dir() / str(width) / f"{kind}-{name}.png"
    # Deleting an upload and adding another under the same name reuses the file
    # name, so a copy older than its source is stale rather than a hit.
    if cached.is_file() and cached.stat().st_mtime >= source.stat().st_mtime:
        return cached

    try:
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError):
        log.warning("cannot read sticker %s to scale it", sticker_id)
        return None
    if image.width > width:
        height = max(1, round(image.height * width / image.width))
        image = image.resize((width, height), Image.LANCZOS)
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        image.save(cached, "PNG")
    except OSError:
        # A read only or full data directory should cost you a few kilobytes of
        # bandwidth, not the sticker itself.
        log.warning("cannot write a thumbnail into %s", cache_dir())
        return source
    return cached


def resolve(sticker_id: str) -> Path | None:
    """The file behind an id, or None. The regex is what keeps this safe.

    A still sticker is a `.png` and an animated one is a `.gif`, under the same
    name, so an id says nothing about which it is and every caller that only wants
    pixels keeps working: Pillow opens a GIF and gives its first frame.
    """
    found = STICKER_ID.match(sticker_id or "")
    if not found:
        return None
    source, name = found.groups()
    folder = {"openmoji": library_dir(), "mine": uploads_dir()}.get(source, gifs_dir())
    for suffix in (".png", ANIMATED_SUFFIX):
        file = folder / f"{name}{suffix}"
        if file.is_file():
            return file
    return None


def is_animated(file: Path | None) -> bool:
    """Does this file hold more than one frame."""
    if file is None or not file.is_file():
        return False
    try:
        with Image.open(file) as opened:
            return getattr(opened, "n_frames", 1) > 1
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def motion(sticker_id: str) -> Path | None:
    """The file behind an id if it moves, otherwise None.

    This is the seam between the two mechanisms. A still sticker is pasted into the
    frame by Pillow before ffmpeg ever runs; an animated one is a second video input
    in the filter graph, because a paste has no time axis. See DECISIONS.md D-036.
    """
    file = resolve(sticker_id)
    return file if is_animated(file) else None


def split(placed: list[Placed]) -> tuple[list[Placed], list[Placed]]:
    """The placed things, divided by which mechanism draws them.

    Returns `(still, moving)`. The caller pastes the first list and hands the second
    to the renderer. Splitting here rather than in either of them keeps the rule in
    one place: a sticker whose file has more than one frame moves, and nothing else
    does. Free text never does, whatever it is written over.
    """
    still, moving = [], []
    for one in placed:
        (moving if one.moving else still).append(one)
    return still, moving


# -- searching ------------------------------------------------------------

@lru_cache(maxsize=1)
def _catalogue() -> list[dict]:
    """OpenMoji's keyword file, reduced to what a search needs.

    Cached for the life of the process: it is 2 MB of json and it never changes
    under us. Skin tone variants are dropped, because five near identical results
    for every gesture is a worse picker, and the base emoji is still there.
    """
    meta = install_dir() / "openmoji.json"
    if not meta.is_file():
        return []
    try:
        raw = json.loads(meta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        log.warning("the sticker keyword file could not be read")
        return []

    catalogue: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict) or entry.get("skintone"):
            continue
        hexcode = str(entry.get("hexcode") or "")
        if not hexcode or not (library_dir() / f"{hexcode}.png").is_file():
            continue
        name = str(entry.get("annotation") or "").strip()
        catalogue.append({
            "id": f"openmoji:{hexcode}",
            "name": name,
            "group": str(entry.get("group") or ""),
            "words": _words(
                entry.get("annotation"), entry.get("tags"),
                entry.get("openmoji_tags"), entry.get("subgroups"),
            ),
            "order": entry.get("order") or 10_000,
        })
    return catalogue


def _words(*parts: object) -> set[str]:
    """Every searchable word, split so a hyphenated tag is two words."""
    joined = " ".join(str(part or "") for part in parts).lower()
    return {word for word in re.split(r"[^a-z0-9]+", joined) if word}


def _matches(words: set[str], query: list[str]) -> bool:
    """Every query word has to start some word of the sticker.

    Prefix, not substring: searching `om` should find `om`, not every emoji whose
    tags happen to contain `mouth`.
    """
    return all(any(word.startswith(part) for word in words) for part in query)


def _folder_items(folder: Path, group: str) -> list[dict]:
    """Everything in one of our own folders, newest first.

    Both extensions, because an animated one is a GIF. Listing only `.png` here is
    a bug that hides nothing at upload time and everything afterwards: the sticker
    is stored, it goes onto the frame, and it is never in the picker again.
    """
    if not folder.is_dir():
        return []
    found = [*folder.glob("*.png"), *folder.glob(f"*{ANIMATED_SUFFIX}")]
    files = sorted(found, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    return [
        {
            "id": f"{group}:{file.stem}",
            "name": file.stem.replace("-", " "),
            "group": group,
            "words": _words(file.stem),
            "order": 0,
            "moving": file.suffix == ANIMATED_SUFFIX,
        }
        for file in files
    ]


def _mine() -> list[dict]:
    """Uploaded stickers. They always come before the library."""
    return _folder_items(uploads_dir(), "mine")


def _gifs() -> list[dict]:
    """Picked GIFs, newest first. Between your uploads and the library.

    A GIF you used last week is more likely to be wanted than a drawing you have
    never used, and less likely than something you deliberately uploaded.
    """
    return _folder_items(gifs_dir(), "gif")


# The shelf an empty search box shows. Sixty grinning faces is what the catalogue
# order gives you; this is what actually goes on a music status. Keep it free of
# repeats: `search` drops them, and a repeat costs a slot rather than adding one.
OPENING_SHELF = (
    "1F64F", "1FA94", "1F549", "1F6D5", "1F3B5", "1F3B6", "1F3BC", "1F3B8",
    "1F3BB", "1FA95", "1F941", "1F4FF", "1FAD6", "1F338", "1F3F5", "1F490",
    "1FAB7", "1F31F", "2728", "1F525", "2764", "1F9E1", "1F495", "1F64C",
    "1F44F", "1F919", "1F6D0", "1F9D8", "1F56F", "1F31E", "1F319", "1F320",
    "1F3AF", "1F3AC", "1F399", "1F3A7", "1F4FB", "1F4E3", "1F517", "2B50",
)


def search(query: str = "", limit: int = SEARCH_LIMIT) -> list[dict]:
    """Stickers matching `query`. An empty query gives a sensible starting shelf."""
    parts = [word for word in re.split(r"[^a-z0-9]+", (query or "").lower()) if word]
    mine, catalogue = _mine() + _gifs(), _catalogue()

    if not parts:
        by_id = {item["id"]: item for item in catalogue}
        # `dict.fromkeys` rather than a set: it keeps the hand written order and
        # drops a repeat. A shelf of forty that names one sticker twice is a shelf
        # of thirty nine, and the second copy is a dead slot on a phone screen.
        shelf = [by_id[f"openmoji:{code}"] for code in dict.fromkeys(OPENING_SHELF)
                 if f"openmoji:{code}" in by_id]
        return [_public(item) for item in (mine + shelf)[:limit]]

    hits = [item for item in mine + catalogue if _matches(item["words"], parts)]
    whole = " ".join(parts)

    def rank(item: dict) -> tuple:
        name = item["name"].lower()
        return (
            0 if item["group"] == "mine" else 1 if item["group"] == "gif" else 2,
            0 if name == whole else 1 if name.startswith(whole) else 2,
            len(name),
            item["order"],
        )

    hits.sort(key=rank)
    return [_public(item) for item in hits[:limit]]


def _public(item: dict) -> dict:
    """What the picker is told. `moving` is there because the shelf shows a still
    thumbnail of an animated sticker, and without a mark nothing on screen says
    which of your own stickers move."""
    return {
        "id": item["id"],
        "name": item["name"],
        # A picked GIF counts as yours for every purpose the page has: it is in
        # your shelf, it is deletable, and it is not part of the OpenMoji library.
        "mine": item["group"] in ("mine", "gif"),
        "moving": bool(item.get("moving")),
    }


# -- uploads --------------------------------------------------------------

def save_upload(name: str, encoded: str) -> dict:
    """Store an uploaded or pasted image as a sticker. Returns its catalogue entry.

    Whatever arrives is decoded by Pillow and written back out by Pillow. Nothing
    of the original file survives that round trip, which is the point: the bytes on
    disk are ones we produced, not ones we were handed. That holds for an animated
    file too, frame by frame, which is also what turns an animated WebP the renderer
    cannot read into a GIF it can.
    """
    if not SAFE_NAME.match(name or ""):
        raise ValueError("a sticker name is letters, numbers, spaces, - and _")
    payload = (encoded or "").split(",")[-1]  # tolerate a data: url prefix
    # The generous ceiling first, because whether this is animated is not known
    # until Pillow has opened it. The tighter still-image one is applied below.
    if len(payload) > ANIMATED_MAX_BYTES * 4 // 3 + 8:
        raise ValueError(f"a sticker has to be under {ANIMATED_MAX_BYTES // 1000} kB")
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("that upload is not valid base64") from exc
    if len(data) > ANIMATED_MAX_BYTES:
        raise ValueError(f"a sticker has to be under {ANIMATED_MAX_BYTES // 1000} kB")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("that file is not an image Pillow can read") from exc

    moving = getattr(image, "n_frames", 1) > 1
    if not moving and len(data) > UPLOAD_MAX_BYTES:
        raise ValueError(f"a still sticker has to be under {UPLOAD_MAX_BYTES // 1000} kB")

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name.strip()).strip("-").lower() or "sticker"
    folder = uploads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    suffix = ANIMATED_SUFFIX if moving else ".png"
    file = folder / f"{slug}{suffix}"
    for attempt in range(2, 100):
        # Either extension counts as taken, so a still and an animated sticker can
        # never share a name and leave `resolve` picking one of them arbitrarily.
        if not (folder / f"{file.stem}.png").exists() and \
           not (folder / f"{file.stem}{ANIMATED_SUFFIX}").exists():
            break
        file = folder / f"{slug}-{attempt}{suffix}"

    if moving:
        _save_animated(image, file)
    else:
        if max(image.size) > UPLOAD_MAX_EDGE:
            image.thumbnail((UPLOAD_MAX_EDGE, UPLOAD_MAX_EDGE), Image.LANCZOS)
        image.convert("RGBA").save(file, "PNG")
    log.info("saved sticker %s (%d bytes in, %d out, %s)", file.name, len(data),
             file.stat().st_size, "animated" if moving else "still")
    return {
        "id": f"mine:{file.stem}",
        "name": file.stem.replace("-", " "),
        "mine": True,
        "moving": moving,
    }


def _save_animated(image: Image.Image, dest: Path) -> None:
    """Every frame through Pillow and back out as a GIF.

    The frames are read in whatever the source was, WebP included, and written as
    the one animated form this project's ffmpeg can read. Frames beyond the cap are
    dropped rather than the file refused: a sticker that loops for eight seconds
    instead of twenty is still the sticker somebody chose.
    """
    frames: list[Image.Image] = []
    for frame in ImageSequence.Iterator(image):
        art = frame.convert("RGBA")
        if max(art.size) > ANIMATED_MAX_EDGE:
            art.thumbnail((ANIMATED_MAX_EDGE, ANIMATED_MAX_EDGE), Image.LANCZOS)
        frames.append(art)
        if len(frames) >= ANIMATED_MAX_FRAMES:
            break
    if not frames:
        raise ValueError("that file has no frames in it")
    # `disposal=2` clears each frame before the next, without which a shape that
    # shrinks leaves the larger one behind it showing through the transparency.
    frames[0].save(
        dest, "GIF", save_all=True, append_images=frames[1:],
        duration=image.info.get("duration", 100), loop=0, disposal=2,
    )


def save_gif(provider: str, ident: str, title: str, data: bytes) -> dict:
    """Store a GIF picked from a search, and prune the folder back to `GIF_KEEP`.

    The bytes go through Pillow like any upload, D-036's rule: what lands on disk
    is what we wrote, never what somebody else handed us. A still image is stored
    as a `.png`, because a GIF service will happily return something that does not
    move and there is no reason to keep it as a GIF if it does not.

    The name carries the provider and its id rather than the title. Two services
    will eventually both have a `thank-you`, and a title is not unique even within
    one of them, so a title based name would silently overwrite.
    """
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", f"{provider}-{ident}").strip("-").lower()
    if not slug:
        raise ValueError("that GIF has no id to file it under")
    slug = slug[:64]
    if len(data) > ANIMATED_MAX_BYTES:
        raise ValueError(f"a sticker has to be under {ANIMATED_MAX_BYTES // 1000} kB")

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("that download is not an image Pillow can read") from exc

    moving = getattr(image, "n_frames", 1) > 1
    folder = gifs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{slug}{ANIMATED_SUFFIX if moving else '.png'}"

    if moving:
        _save_animated(image, file)
    else:
        flat = image.convert("RGBA")
        if max(flat.size) > UPLOAD_MAX_EDGE:
            flat.thumbnail((UPLOAD_MAX_EDGE, UPLOAD_MAX_EDGE), Image.LANCZOS)
        flat.save(file, "PNG")
    prune_gifs()
    log.info("kept gif %s from %s (%s, %d bytes in)",
             slug, provider, "animated" if moving else "still", len(data))
    return {
        "id": f"gif:{file.stem}",
        "name": (title or file.stem).strip()[:60] or file.stem,
        "mine": True,
        "moving": moving,
    }


def prune_gifs(keep: int | None = None) -> int:
    """Drop the oldest picked GIFs past `keep`. Returns how many went.

    Uploads are never touched by this. Only the folder that fills up by browsing
    is pruned, which is the whole reason it is a separate folder.

    `keep` is read here rather than defaulted in the signature, because a default
    argument binds once when the module is imported and would then ignore anybody
    who changed `GIF_KEEP` afterwards, tests included.
    """
    keep = GIF_KEEP if keep is None else keep
    folder = gifs_dir()
    if not folder.is_dir():
        return 0
    # Nanoseconds, and the name to break a tie. Several of these can be written
    # inside one clock tick, and "the newest twenty" has to mean something exact
    # or pruning deletes an arbitrary one of them.
    files = sorted(
        [*folder.glob("*.png"), *folder.glob(f"*{ANIMATED_SUFFIX}")],
        key=lambda f: (f.stat().st_mtime_ns, f.name), reverse=True,
    )
    gone = 0
    for file in files[keep:]:
        _forget(file, "gif")
        gone += 1
    if gone:
        log.info("pruned %d picked gif(s), keeping the newest %d", gone, keep)
    return gone


def _forget(file: Path, group: str) -> None:
    """Delete a sticker file and every scaled copy made from it."""
    file.unlink(missing_ok=True)
    for width in THUMB_WIDTHS:
        (cache_dir() / str(width) / f"{group}-{file.stem}.png").unlink(missing_ok=True)


def delete_upload(sticker_id: str) -> bool:
    """Remove one of your own stickers. The OpenMoji library is never touched.

    A picked GIF counts as yours: it is in your shelf and the page offers the same
    delete on it, so refusing here would leave a visible sticker nothing can remove.
    """
    found = STICKER_ID.match(sticker_id or "")
    if not found or found.group(1) not in ("mine", "gif"):
        raise ValueError("only your own stickers can be deleted")
    group = found.group(1)
    file = resolve(sticker_id)
    home = uploads_dir() if group == "mine" else gifs_dir()
    if file is None or file.parent != home:
        return False
    _forget(file, group)
    return True


# -- painting -------------------------------------------------------------

def paste(canvas: Image.Image, stickers: list[Placed]) -> int:
    """Paste placed things onto an RGBA canvas, in order. Returns how many landed.

    The canvas may be the 1620 pixel card or the 1080 pixel overlay: coordinates
    are fractions, so nothing here needs to know which. Nor does it need to know
    what it is pasting: each one draws itself at the width it was given, which is
    what lets a line of free text through this without a second code path.
    """
    landed = 0
    for sticker in stickers:
        width = max(1, round(sticker.size * canvas.width))
        try:
            art = sticker.art(width)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            log.warning("%s could not be drawn, skipping (%s)", sticker.label, exc)
            continue
        if art is None:
            continue
        if sticker.rotation:
            # expand keeps the corners, and the transparent margin it adds costs
            # nothing because the paste is alpha composited.
            art = art.rotate(sticker.rotation, resample=Image.BICUBIC, expand=True)

        left = round(sticker.x * canvas.width - art.width / 2)
        top = round(sticker.y * canvas.height - art.height / 2)
        canvas.alpha_composite(art, (left, top))
        landed += 1
    return landed
