"""The Recent strip's delete cross, and the contracts it leans on.

The strip is drawn by `app.js` from `/api/state` and styled by `app.css`, so
none of it is reachable from Python at run time. What these tests guard is the
handful of places where the page and the server have to agree, and the handful
of mistakes this control has already made once.

The delete itself is tested where it lives, in `test_serve.py`
`TestDeletingAClip`: the route, the file group, the 409 while WhatsApp is being
driven, and the token. Nothing here repeats that.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "wastatus" / "web"


@pytest.fixture(scope="module")
def script() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles() -> str:
    return (WEB / "app.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


def rule(styles: str, selector: str) -> str:
    """The declarations of one CSS rule, by exact selector text."""
    match = re.search(
        re.escape(selector) + r"\s*\{([^}]*)\}", styles, re.S)
    assert match, f"no rule for {selector}"
    return match.group(1)


class TestTheCrossAsksTheServerSomethingItAnswers:
    """The one thing here that can break without anyone touching this file.

    The cross posts to a route name written as a string in `app.js`. Rename the
    route in `serve.py` and nothing fails to compile, nothing fails to lint, and
    the page simply stops being able to delete. So the string and the route are
    checked against each other rather than each on its own.
    """

    def test_the_route_the_page_posts_to_is_a_route_the_server_has(self, script):
        from wastatus import serve

        posted = set(re.findall(r'post\("(/api/[a-z/]+)"', script))
        assert "/api/clip/delete" in posted, (
            "the strip no longer posts to the delete route")
        handler = Path(serve.__file__).read_text(encoding="utf-8")
        for route in posted:
            assert f'path == "{route}"' in handler, (
                f"the page posts to {route} and the server does not route it")


class TestATileIsNotAButtonInsideAButton:
    """Why the tile stopped being a `<button>` when the cross arrived.

    A button nested in a button is invalid, and no browser reports it: the parser
    silently unnests them into siblings. The cross would then be laid out beside
    the tile rather than on it, and `closest(".tile")` from the cross would find
    nothing. It looks like a styling bug and it is a markup one.
    """

    def test_the_tile_wrapper_is_not_itself_a_button(self, script):
        assert re.search(r'<div class="tile"', script), (
            "the tile wrapper must be a div, so the two buttons can be siblings")
        assert not re.search(r'<button class="tile"[ >]', script), (
            "the tile is a button again, and the cross inside it is now invalid")

    def test_the_open_action_and_the_cross_are_siblings(self, script):
        strip = script[script.index('<div class="tile"'):]
        strip = strip[:strip.index("</div>")]
        opens = strip.index('class="tile__open"')
        closes = strip.index("</button>")
        kill = strip.index('class="tile__kill"')
        assert opens < closes < kill, (
            "the cross is inside the open button, which the parser will unnest")

    def test_the_stem_is_on_the_wrapper_so_both_buttons_can_read_it(self, script):
        assert re.search(r'<div class="tile" data-stem=', script)


class TestTheCrossAndTheTickDoNotFightForACorner:
    """Both are 20-something pixel badges pinned to the thumbnail.

    They were both `top right` when the cross was added, which put the delete
    control underneath the "saved on this device" tick on every clip already
    downloaded: exactly the clips most likely to be the ones being cleared out.
    """

    def test_they_are_pinned_to_opposite_sides(self, styles):
        assert "left:" in rule(styles, ".tile__saved")
        assert "right:" in rule(styles, ".tile__kill")

    def test_neither_claims_both_sides(self, styles):
        for selector in (".tile__saved", ".tile__kill"):
            body = rule(styles, selector)
            assert not ("left:" in body and "right:" in body), (
                f"{selector} is pinned to both sides and will stretch")


class TestTheArmedStateStaysReadableInBothPalettes:
    """The mistake this caught, on 2026-08-25.

    `--danger` is a dark red in the light palette and a pale pink in the dark
    one, because it is used as ink on light and as ink on dark respectively. The
    armed cross uses it as a *fill*, so its text cannot be a fixed colour: white
    on `#b3261e` reads, and white on `#f2b8b5` does not. `--danger-bg` inverts in
    step with it, so the pair is legible either way round.
    """

    FILLED = (".tile__kill:hover, .tile__kill:focus-visible",
              '.tile__kill[data-armed="true"]')

    @pytest.mark.parametrize("selector", FILLED)
    def test_a_danger_fill_takes_its_ink_from_the_matching_token(
            self, selector, styles):
        body = rule(styles, selector)
        if "var(--danger)" not in body:
            pytest.skip(f"{selector} no longer fills with --danger")
        assert "color: var(--danger-bg)" in body, (
            f"{selector} fills with --danger but sets its own ink, which will "
            "be unreadable in one of the two palettes")

    def test_the_two_tokens_really_do_invert(self, styles):
        """Guards the assumption the rule above is built on."""
        light = styles[styles.index(":root {"):]
        light = light[:light.index("}")]
        dark = styles[styles.index(':root[data-theme="dark"]'):]
        dark = dark[:dark.index("}")]
        pick = lambda block, name: re.search(
            rf"--{name}:\s*([^;]+);", block).group(1).strip()
        assert pick(light, "danger") != pick(dark, "danger")
        assert pick(light, "danger-bg") != pick(dark, "danger-bg")

    def test_the_fill_does_not_fade_in(self, styles):
        """A safety signal you can press through before it arrives is not one."""
        assert "transition: opacity var(--duration);" in rule(styles, ".tile__kill")


class TestTheCrossCanBeHitByAFinger:
    """22 pixels is a mark, not a target.

    The disc is deliberately small: the tile is 116px wide and a quarter of it
    taken by a cross is a cross that has become the picture. The target is grown
    instead by a transparent `::before`, the same trick the sticker handles use,
    so the two numbers have to be read together to know whether a finger can
    land on it.
    """

    TOUCH = 44   # the same floor as `--touch` in app.css

    def coarse_block(self, styles: str) -> str:
        """The coarse-pointer rules for the cross, and no one else's.

        There are two `(hover: none) and (pointer: coarse)` blocks in the file
        and the sticker handles own the first one. Slicing from the first match
        read the handles' 10px pad against the cross's desktop 22px disc and
        called the result 42: a number belonging to neither control.
        """
        for start in [m.start() for m in re.finditer(
                r"@media \(hover: none\) and \(pointer: coarse\)", styles)]:
            block = styles[start:styles.index("\n}", start)]
            if ".tile__kill" in block:
                return block
        raise AssertionError("no coarse-pointer rules for the cross")

    def touch_size(self, styles: str) -> int:
        block = self.coarse_block(styles)
        width = int(re.search(r"\.tile__kill \{[^}]*width:\s*(\d+)px", block).group(1))
        pad = int(re.search(r"::before \{ inset: -(\d+)px", block).group(1))
        return width + pad * 2

    def test_a_finger_reaches_the_whole_target(self, styles):
        assert self.touch_size(styles) >= self.TOUCH

    def test_the_visible_disc_stays_small_enough_not_to_be_the_tile(self, styles):
        """The other half of the trade: the grown area must be doing the work."""
        block = self.coarse_block(styles)
        width = int(re.search(r"\.tile__kill \{[^}]*width:\s*(\d+)px", block).group(1))
        assert width <= 28, "the disc is eating the thumbnail it sits on"
        assert width < self.TOUCH, "the disc alone is the target, so it is too big"


class TestTheStripCanSayWhatWentWrong:
    """Delete can be refused, and the strip is nowhere near the Post panel.

    A 409 arrives whenever WhatsApp is being driven, which is a normal thing to
    hit, and before this the only place an error could be shown was in a panel
    that may be collapsed and is at the other end of the page on a phone.
    """

    def test_the_strip_has_its_own_error_line(self, page):
        assert 'id="recent-error"' in page

    def test_it_starts_hidden(self, page):
        assert re.search(r'id="recent-error"[^>]*\bhidden\b', page)

    def test_a_refused_delete_is_shown_there(self, script):
        block = script[script.index("async function killClip"):]
        block = block[:block.index("\n}\n")]
        assert 'fail($("recent-error")' in block

    def test_the_clip_on_show_is_cleared_when_it_is_the_one_deleted(self, script):
        block = script[script.index("async function killClip"):]
        block = block[:block.index("\n}\n")]
        assert "clearClip()" in block, (
            "deleting the clip on show would leave the player pointed at a file "
            "that is no longer on disk")


class TestOnlyOneTileCanBeAsking:
    """Two armed crosses is two ways to delete the one you did not mean to."""

    def test_arming_one_disarms_the_other(self, script):
        block = script[script.index("async function killClip"):]
        block = block[:block.index("\n}\n")]
        assert re.search(r"if \(killArmed !== stem\) \{\s*\n\s*disarmKill\(\);", block)

    def test_the_question_expires(self, script):
        block = script[script.index("async function killClip"):]
        block = block[:block.index("\n}\n")]
        assert re.search(r"setTimeout\(\(\) => disarmKill\(\), \d+\)", block), (
            "an armed cross that never disarms can be completed by a stray press "
            "minutes later")

    def test_which_tile_is_asking_survives_a_repaint(self, script):
        """The strip repaints itself on the poll, throwing the DOM away."""
        assert "if (stem === killArmed) armKill(kill);" in script, (
            "the armed tile is redrawn as a plain cross after a repaint, so the "
            "second press arms it again instead of deleting")
