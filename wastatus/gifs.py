"""GIF search, behind one seam, off unless it is switched on.

This is the only part of the tool that talks to anybody other than YouTube, so it
is a module you can delete. `WASTATUS_GIF_PROVIDER` empty, or missing, and nothing
here ever runs: the page shows no toggle, the server answers no routes, and no
search term leaves this machine. See DECISIONS.md D-043.

**Two providers, one shape.** GIPHY and KLIPY return completely different JSON.
Everything below `search` normalises both into the same small record, so the page,
the server and the tests only ever see one shape and adding a third provider is a
function rather than a change.

**Why a preview and a full copy are different sizes.** The shelf draws forty
thumbnails at once and a placed sticker is drawn at up to 90 per cent of a 1080
pixel frame. Asking for one size for both means either a blurry sticker or a shelf
that costs megabytes, so each provider names which of its renditions is which.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from itertools import zip_longest

log = logging.getLogger("wastatus")

TIMEOUT = 15.0
SEARCH_LIMIT = 30
UA = "wastatus/1.0 (+personal status tool)"

# One scale for both services, because the page should not have to know whose
# vocabulary it is speaking. `pg` is the default: `g` is narrow enough to strip out
# ordinary celebration and reaction GIFs, which is most of what gets used.
RATINGS = ("g", "pg", "pg-13", "r")
DEFAULT_RATING = "pg"

# KLIPY's own scale, and how ours maps onto it. Theirs is a safety level rather
# than an age rating, so this is a judgement, not a table they publish.
_KLIPY_FILTER = {"g": "high", "pg": "high", "pg-13": "medium", "r": "low"}


class GifError(RuntimeError):
    """Anything that went wrong reaching a provider. Always safe to show."""


@dataclass(frozen=True)
class Gif:
    """One search result, in the only shape the rest of the tool knows."""

    id: str            # provider's own id, no colon: it becomes `gif:<provider>-<id>`
    title: str
    preview: str       # a small still or animation for the shelf
    full: str          # what gets downloaded when this one is chosen
    width: int
    height: int
    bytes: int         # of `full`, as the provider reports it. 0 when unknown
    provider: str = ""  # whose result this is; a search of both mixes the two

    @property
    def key(self) -> str:
        """What the page names it by. Two services can both have an `abc123`, so
        once their results share a shelf the provider is part of the name."""
        return f"{self.provider}-{self.id}" if self.provider else self.id

    def as_json(self) -> dict:
        return {
            "id": self.key, "title": self.title, "preview": self.preview,
            "width": self.width, "height": self.height, "bytes": self.bytes,
            "provider": self.provider,
        }


# -- what is switched on ---------------------------------------------------

# Searching both services at once, results mixed: a name beside the providers'.
BOTH = "both"


@dataclass(frozen=True)
class Personal:
    """A person's own keys, and which of them to search, on the hosted page."""

    keys: dict
    choice: str = ""


# A person's own keys and choice, on the hosted page: every search there uses the
# keys the person gave, or none. Set per request; unset is the local tool, which
# reads `.env`. The owner's own keys are never used for anybody else. D-088.
personal: contextvars.ContextVar[Personal | None] = contextvars.ContextVar(
    "gifs_personal", default=None)


def _keys() -> dict[str, str]:
    own = personal.get()
    if own is not None:
        return {name: key for name, key in own.keys.items() if name in PROVIDERS and key}
    found = {}
    for name, entry in PROVIDERS.items():
        key = os.environ.get(entry.env_key) or ""
        if key:
            found[name] = key
    return found


def provider() -> str:
    """What a search asks: a provider's name, `both`, or "" when the feature is off.

    Off is the default and off is also what a half finished setup gets: a provider
    named with no key behind it is not a working feature, and failing closed here
    means the page never offers a search box that cannot answer.
    """
    keys = _keys()
    own = personal.get()
    if own is not None:
        # A person's choice falls back to what they have: a removed key must not
        # leave them with a search box that cannot answer.
        want = (own.choice or "").lower()
        if want == BOTH and len(keys) > 1:
            return BOTH
        if want in keys:
            return want
        return BOTH if len(keys) > 1 else next(iter(sorted(keys)), "")
    name = (os.environ.get("WASTATUS_GIF_PROVIDER") or "").strip().lower()
    if name in ("", "off", "none"):
        return ""
    if name == BOTH:
        if len(keys) > 1:
            return BOTH
        # One key is still a working search: use it, as the hosted page does.
        log.warning("WASTATUS_GIF_PROVIDER is both, but only %s has a key",
                    ", ".join(sorted(keys)) or "neither")
        return next(iter(sorted(keys)), "")
    if name not in PROVIDERS:
        log.warning("WASTATUS_GIF_PROVIDER is %r, which is not one of %s",
                    name, ", ".join(sorted(PROVIDERS)))
        return ""
    if not key_for(name):
        log.warning("%s is selected but %s is empty, so GIF search stays off",
                    name, PROVIDERS[name].env_key)
        return ""
    return name


def sources(name: str | None = None) -> list[str]:
    """The providers a search of `name` (default: the current choice) asks."""
    name = provider() if name is None else name
    if name == BOTH:
        return sorted(_keys())
    return [name] if name in PROVIDERS and key_for(name) else []


def key_for(name: str) -> str:
    return _keys().get(name, "")


def enabled() -> bool:
    return bool(provider())


def rating() -> str:
    """The content filter, in our vocabulary. An unknown value is refused.

    Guessing here would be the wrong way to be wrong: a typo becoming `off` is a
    setting that silently does the opposite of what it was written to do.
    """
    want = (os.environ.get("WASTATUS_GIF_RATING") or "").strip().lower()
    if not want:
        return DEFAULT_RATING
    if want not in RATINGS:
        log.warning("WASTATUS_GIF_RATING is %r, which is not one of %s. Using %s",
                    want, ", ".join(RATINGS), DEFAULT_RATING)
        return DEFAULT_RATING
    return want


def available() -> list[dict]:
    """Every provider that could be switched to, because its key has a value.

    A provider with no key is not an option: choosing it would turn the feature off
    and the page would have nothing to say about why. So the chooser only ever
    offers what would actually answer.
    """
    found = [
        {"name": name, "label": entry.credit}
        for name, entry in sorted(PROVIDERS.items())
        if key_for(name)
    ]
    if len(found) > 1:
        found.append({"name": BOTH, "label": "Both, mixed together"})
    return found


def choose(name: str) -> str:
    """Switch provider for this process. Returns the name now in force.

    **This does not touch `.env`.** The file is the default and stays the default,
    so a restart returns to whatever is written there. Editing a person's own
    settings file from a web request, to make a choice that is cheap to make again,
    is a trade this tool does not want: that file holds their API keys, and nothing
    here should be able to rewrite it.
    """
    want = (name or "").strip().lower()
    if want not in {one["name"] for one in available()}:
        raise GifError(f"{name!r} is not a provider this tool has a key for")
    os.environ["WASTATUS_GIF_PROVIDER"] = want
    log.info("gif provider switched to %s for this session", want)
    return want


def credit() -> dict:
    """The attribution the page has to show, and the words the search box needs.

    Not decoration and not optional. KLIPY's one hard requirement is the
    placeholder text; GIPHY's is a visible mark. Both are carried here so the page
    does not have to know whose rules it is following.
    """
    name = provider()
    if not name:
        return {}
    if name == BOTH:
        # Each service's own requirement, kept: KLIPY's words open the box, and
        # GIPHY's mark sits beside KLIPY's.
        return {"provider": BOTH,
                "label": " · ".join(PROVIDERS[one].credit for one in sources(BOTH)),
                "placeholder": "Search KLIPY and GIPHY",
                "url": PROVIDERS["giphy"].site, "choices": available()}
    entry = PROVIDERS[name]
    return {"provider": name, "label": entry.credit, "placeholder": entry.placeholder,
            "url": entry.site,
            # What else could be chosen right now. One entry means no choice worth
            # drawing, and the page draws none.
            "choices": available()}


# -- the two providers -----------------------------------------------------

def _get(url: str, *, timeout: float = TIMEOUT) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise GifError(
                f"that GIF key was refused. Check it in "
                f"{'your account settings' if personal.get() else '.env'}, and that "
                "it is an API key rather than an SDK key"
            ) from exc
        if exc.code == 429:
            raise GifError(
                "the GIF service is rate limiting this key. A beta GIPHY key "
                "allows 100 calls an hour. Try again shortly"
            ) from exc
        raise GifError(f"the GIF service answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GifError("could not reach the GIF service") from exc
    except json.JSONDecodeError as exc:
        raise GifError("the GIF service sent something that was not JSON") from exc


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _giphy(query: str, limit: int, key: str, large: bool = False) -> list[Gif]:
    params = urllib.parse.urlencode({
        "api_key": key, "q": query, "limit": limit, "rating": rating(),
        "bundle": "messaging_non_clips",
    })
    payload = _get(f"https://api.giphy.com/v1/gifs/search?{params}")
    out = []
    for item in payload.get("data") or []:
        images = item.get("images") or {}
        # Measured 2026-08-22: `fixed_width_small` is 100x96 at 85 kB, and
        # `fixed_width_downsampled` is 200x190 at 121 kB. Twice the resolution for
        # a third more bytes is the best value GIPHY offers, so the wide shelf
        # takes it and the phone keeps the small one. `downsized` is capped at
        # 2 MB by GIPHY itself, so it can never break the animated ceiling.
        preview = (
            (images.get("fixed_width_downsampled") or images.get("fixed_width") or {})
            if large else
            (images.get("fixed_width_small") or images.get("fixed_width") or {})
        )
        full = (images.get("downsized") or images.get("fixed_width") or {})
        if not preview.get("url") or not full.get("url"):
            continue
        out.append(Gif(
            id=str(item.get("id") or ""),
            title=(item.get("title") or "").strip() or "GIF",
            preview=preview["url"],
            full=full["url"],
            width=_int(full.get("width")),
            height=_int(full.get("height")),
            bytes=_int(full.get("size")),
        ))
    return out


def _klipy(query: str, limit: int, key: str, large: bool = False) -> list[Gif]:
    params = urllib.parse.urlencode({
        "q": query, "per_page": max(8, min(50, limit)), "page": 1,
        "content_filter": _KLIPY_FILTER.get(rating(), "high"),
        # Their own docs ask for a stable identifier per user. This tool has one
        # user and no accounts, so it is a constant rather than anything of his.
        "customer_id": "wastatus",
    })
    root = f"https://api.klipy.co/api/v1/{urllib.parse.quote(key, safe='')}"
    payload = _get(f"{root}/gifs/search?{params}")
    data = payload.get("data")
    items = data.get("data") if isinstance(data, dict) else data
    out = []
    for item in items or []:
        files = item.get("file") or {}
        # Measured 2026-08-22: `xs` is 127x90 at 134 kB and `sm` is 220x157 at
        # 376 kB. `xs` is right for a phone's cell and is upscaled in the wide
        # shelf's 172 pixel one, so the wide shelf asks for `sm` and pays for it.
        # `md` is sharp at any size this tool places, and costs far more than
        # KLIPY's documentation implies: measured median 1296 kB, p90 3352 kB, and
        # about 1.5 per cent come back over the ceiling and are refused on picking.
        small = ((files.get("xs") or {}).get("gif") or {})
        preview = (((files.get("sm") or {}).get("gif") or small) if large else small)
        full = ((files.get("md") or {}).get("gif") or (files.get("hd") or {}).get("gif") or {})
        if not preview.get("url") or not full.get("url"):
            continue
        out.append(Gif(
            id=str(item.get("slug") or item.get("id") or ""),
            title=(item.get("title") or "").strip() or "GIF",
            preview=preview["url"],
            full=full["url"],
            width=_int(full.get("width")),
            height=_int(full.get("height")),
            bytes=_int(full.get("size")),
        ))
    return out


@dataclass(frozen=True)
class Provider:
    env_key: str
    search: object
    credit: str
    placeholder: str
    site: str


PROVIDERS: dict[str, Provider] = {
    "giphy": Provider(
        env_key="WASTATUS_GIPHY_KEY", search=_giphy,
        credit="Powered by GIPHY", placeholder="Search GIPHY",
        site="https://giphy.com",
    ),
    "klipy": Provider(
        env_key="WASTATUS_KLIPY_KEY", search=_klipy,
        # Their guidelines make exactly one thing mandatory, and it is this string
        # in the search box. The mark beside it is optional and is shown anyway,
        # because a search that reaches somebody else's service should say so.
        credit="Powered by KLIPY", placeholder="Search KLIPY",
        site="https://klipy.com",
    ),
}


# -- what the server calls -------------------------------------------------

def search(query: str, limit: int = SEARCH_LIMIT, large: bool = False) -> list[Gif]:
    """Search the configured provider. Raises `GifError`, which is safe to show.

    `large` asks for a thumbnail that suits a wide screen's bigger cell. The
    browser decides, because only the browser knows how big its cells are, and the
    phone reads this page over a tailnet where three times the bytes is felt.
    """
    names = sources()
    if not names:
        raise GifError("GIF search is switched off")
    query = (query or "").strip()
    if not query:
        return []
    if len(query) > 100:
        query = query[:100]
    # Keys are read here, on the request's own thread, where the person's are set;
    # the searches themselves may run on others.
    asks = [(name, key_for(name)) for name in names]

    def ask_some(name: str, key: str, count: int) -> list[Gif]:
        found = PROVIDERS[name].search(query, count, key, large)
        return [replace(one, provider=name) for one in found]

    def ask(name: str, key: str) -> list[Gif]:
        return ask_some(name, key, limit)

    if len(asks) == 1:
        found = ask(*asks[0])
    else:
        # Both at once, side by side: the slower one sets the wait, not the sum.
        # Half as many from each, so a shelf of both costs what a shelf of one does.
        # Each search runs in a copy of this request's context, so its errors speak
        # of the person's own settings rather than of `.env`.
        each = max(1, -(-limit // len(asks)))
        answers: list[list[Gif]] = []
        errors: list[Exception] = []
        with ThreadPoolExecutor(max_workers=len(asks)) as pool:
            futures = [pool.submit(contextvars.copy_context().run, ask_some, name, key, each)
                       for name, key in asks]
            for future in futures:
                try:
                    answers.append(future.result())
                except Exception as exc:  # noqa: BLE001 - one service down is not both
                    errors.append(exc if isinstance(exc, GifError)
                                  else GifError("the GIF service sent something unexpected"))
        if not answers:
            raise errors[0]
        for exc in errors:
            log.warning("one GIF service failed during a search of both: %s", exc)
        found = [one for row in zip_longest(*answers) for one in row if one is not None]
    log.info("gif search %r on %s: %d results, %s previews",
             query, "+".join(names), len(found), "large" if large else "small")
    return found


def fetch(url: str, *, ceiling: int) -> bytes:
    """Download one GIF, refusing anything over `ceiling` before reading it all.

    The provider's own byte count is not trusted for this. It is usually right and
    it is not a promise, and the thing being guarded is memory in this process.
    """
    if not url.startswith("https://"):
        raise GifError("that is not an address this tool will fetch")
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            declared = _int(response.headers.get("Content-Length"))
            if declared and declared > ceiling:
                raise GifError(
                    f"that GIF is {declared // 1000} kB, over the "
                    f"{ceiling // 1000} kB a sticker may be"
                )
            data = response.read(ceiling + 1)
    except urllib.error.HTTPError as exc:
        raise GifError(f"the GIF could not be downloaded ({exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GifError("the GIF could not be downloaded") from exc
    if len(data) > ceiling:
        raise GifError(f"that GIF is over the {ceiling // 1000} kB a sticker may be")
    return data
