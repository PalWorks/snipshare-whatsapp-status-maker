"""Where the page's panels live, and the wiring that a move can quietly cut.

None of this is reachable from Python at run time: it is `index.html`, `app.css`
and `app.js`. What is guarded here is the handful of couplings that break without
raising anything, which is what makes them worth a test rather than a look.

The panels were rearranged on 2026-08-25 (D-057): Stickers moved into the form's
column and Make the clip moved into Post it. Both moves cross a boundary that
something depended on.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parent.parent / "wastatus" / "web"


@pytest.fixture(scope="module")
def page() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def script() -> str:
    return (WEB / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles() -> str:
    return (WEB / "app.css").read_text(encoding="utf-8")


def inside(page: str, outer_open: str, outer_close: str, needle: str) -> bool:
    """Whether `needle` falls between the first `outer_open` and its close."""
    start = page.index(outer_open)
    end = page.index(outer_close, start)
    return start < page.index(needle) < end


class TestMakeTheClipStillReachesItsForm:
    """The move that can break the only button on the page that matters.

    `Make the clip` is a submit button, and a submit button only submits the form
    it belongs to. Inside `<form>` that is implicit. It now sits in the Post it
    panel, which is outside, so the association has to be written down with
    `form=`. Drop that attribute and the button still renders, still looks
    identical, still takes the press, and does nothing at all.
    """

    def test_it_is_outside_the_form_now(self, page):
        assert not inside(page, "<form", "</form>", 'id="make"'), (
            "the make button is back inside the form; the `form=` attribute below "
            "is then redundant but harmless, and this test should be reconsidered")

    def test_and_therefore_says_which_form_it_submits(self, page):
        tag = re.search(r"<button[^>]*id=\"make\"[^>]*>", page, re.S)
        assert tag, "no make button"
        assert re.search(r'form="form"', tag.group(0)), (
            "a submit button outside its form submits nothing without `form=`")
        assert re.search(r'type="submit"', tag.group(0))

    def test_the_form_it_names_exists(self, page):
        """Attribute order is not the point, so it is not read in order."""
        tag = re.search(r"<button[^>]*id=\"make\"[^>]*>", page, re.S).group(0)
        named = re.search(r'form="([^"]+)"', tag)
        assert named, "the make button names no form"
        assert f'<form id="{named.group(1)}"' in page

    def test_it_landed_in_the_post_panel(self, page):
        assert inside(page, 'id="sec-post"', "</details>", 'id="make"')

    def test_the_keyboard_shortcut_goes_through_the_form_not_the_button(self, script):
        """`requestSubmit()` on the form, so it is unaffected by where the button
        is. A handler that clicked `#make` instead would have been the second
        thing this move broke."""
        assert '$("form").requestSubmit()' in script


class TestStickersStayedOutOfTheForm:
    """Why Stickers went beside the form rather than into it.

    The panel holds a text input, `#sticker-search`. A single text input inside a
    form makes Enter submit it, so searching for a sticker and pressing Enter
    would have started a render. It sits next to the form instead, which puts it
    in the same column without putting it in the same form.
    """

    def test_the_panel_is_not_in_the_form(self, page):
        assert not inside(page, "<form", "</form>", 'id="sec-stickers"')

    def test_the_search_box_that_is_the_reason_is_still_there(self, page):
        assert 'id="sticker-search"' in page
        assert not inside(page, "<form", "</form>", 'id="sticker-search"')

    def test_it_is_in_the_same_column_as_the_form(self, page):
        assert inside(page, 'id="left"', 'id="clipside"', 'id="sec-stickers"')


class TestTheFreeTextBoxDoesNotMakeAClip:
    """`#text-line` is a text input inside the form, which is the exact hazard the
    Stickers panel was moved out of the form to avoid.

    It stays inside, because it belongs beside the other three boxes that put words
    on the frame. What makes that safe is that the Enter which would otherwise
    submit the form is caught and used to insert a line instead. Take that handler
    away and pressing Enter after typing a line starts a render.
    """

    def test_the_box_is_in_the_form_with_the_other_words(self, page):
        assert inside(page, "<form", "</form>", 'id="text-line"')

    def test_and_enter_therefore_inserts_rather_than_renders(self, script):
        block = script[script.index('$("text-line").addEventListener("keydown"'):]
        block = block[:block.index("\n});")]
        assert "preventDefault" in block, (
            "Enter in this box submits the form it is in, which makes a clip")
        assert "insertText()" in block

    def test_the_insert_button_is_not_a_submit_button(self, page):
        tag = re.search(r"<button[^>]*id=\"text-add\"[^>]*>", page, re.S)
        assert tag, "no insert button"
        assert 'type="button"' in tag.group(0), (
            "a button inside a form submits it unless it says otherwise")


class TestTheBackgroundChoiceIsWhereItActs:
    """It changes the clip, so it sits in Look with the other thing that changes the
    clip. Safe areas changes only the preview, and two toggles that look alike and
    act differently teach the wrong thing. See D-059."""

    def test_it_is_in_the_look_panel(self, page):
        assert inside(page, 'id="sec-look"', "</details>", 'id="fill-field"')

    def test_it_is_not_beside_the_safe_areas_toggle(self, page):
        assert not inside(page, 'id="sec-preview"', "</details>", 'id="fill-field"')

    def test_the_request_carries_it(self, script):
        block = script[script.index("const body = {"):]
        block = block[:block.index("};")]
        assert "fill," in block, "the renderer is never told which background to draw"

    def test_the_card_never_offers_it(self, script):
        """A card composes its own background, scrim and shadow together."""
        block = script[script.index("function setMode"):]
        block = block[:block.index("\n}")]
        assert '$("fill-field").hidden' in block


class TestTheKeyboardReachesTheFrame:
    """Placed things could be driven by a hand and only by a hand.

    Three things are load bearing here and none of them is visible in a screenshot.
    The keys must not fire while somebody is typing, or Delete in the free text box
    deletes the text box's line. Every removal must go through one door, or ⌘Z
    brings back only the ones that went through it. And a box has to be reachable
    without a pointer at all, which means being a tab stop.
    """

    def test_typing_is_never_a_command(self, script):
        block = script[script.index("document.addEventListener(\"keydown\""):]
        block = block[:block.index("\n});")]
        assert "inAField(event.target)" in block, (
            "Delete inside the free text box has to stay Delete")

    def test_the_keys_a_hand_reaches_for(self, script):
        block = script[script.index("const KEY_MOVES"):]
        block = block[:block.index("$(\"decals\").addEventListener(\"pointerdown\"")]
        for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
                    "Delete", "Backspace", "Escape"):
            assert key in block, f"{key} does nothing on the frame"

    def test_every_way_of_removing_one_goes_through_the_same_door(self, script):
        """The cross, the Remove button and the Delete key. One undo slot is only
        one undo if all three fill it. Deleting one of your own stickers is the
        fourth caller, and empties the slot after, since its picture is gone."""
        # Four callers and the one definition.
        assert script.count("removeDecal(") == 5
        removals = [line for line in script.splitlines()
                    if "decals.splice(" in line and ", 1)" in line]
        assert len(removals) == 1, (
            f"a placed thing is removed in {len(removals)} places, so ⌘Z can only "
            "bring back the ones that went through removeDecal")

    def test_a_placed_thing_is_a_tab_stop(self, script):
        block = script[script.index("function paintDecals"):]
        block = block[:block.index("\n}")]
        assert "box.tabIndex = 0" in block
        assert "aria-label" in block, "a box nobody can name is a box nobody can find"


class TestPlacingThePictureOnThePage:
    """D-061. The picture becomes a placed thing, and the one hazard in that is what
    it must not become: a `.decal`. The sticker gestures find their target with
    `closest(".decal")`, so a picture box carrying that class would be dragged,
    turned, deleted and posted as a sticker."""

    def test_the_box_is_not_a_sticker(self, page):
        tag = re.search(r"<div[^>]*id=\"picture-box\"[^>]*>", page, re.S)
        assert tag, "no picture box"
        assert "decal" not in tag.group(0), (
            "the picture box answers to the sticker gestures")

    def test_it_sits_under_the_stickers_and_over_the_still(self, page):
        at = {name: page.index(f'id="{name}"')
              for name in ("wordshot", "picture-box", "decals")}
        assert at["wordshot"] < at["picture-box"] < at["decals"]

    def test_the_choice_is_in_the_look_panel(self, page):
        assert inside(page, 'id="sec-look"', "</details>", 'id="picture-field"')

    def test_the_request_carries_the_placement(self, script):
        block = script[script.index("const body = {"):]
        block = block[:block.index("};")]
        assert "framing," in block, "the renderer is never told where the picture goes"

    def test_and_so_does_the_preview(self, script):
        block = script[script.index("async function drawPreview"):]
        block = block[:block.index("\n}")]
        assert "framing" in block

    def test_both_modes_offer_it_and_only_one_offers_a_background(self, script):
        """D-062. The artwork panel is placed the same way the frames are, and the
        control is the same control. The background is not: a card composes its own,
        so that one field is still video mode's alone."""
        block = script[script.index("function setMode"):]
        block = block[:block.index("\n}")]
        assert '$("picture-field").hidden' not in block, (
            "the artwork panel cannot be placed in card mode")
        assert '$("fill-field").hidden = next !== "video"' in block

    def test_switching_mode_re_asks_the_control(self, script):
        """The clip on screen may be the other kind, and a placement belongs to one
        shape of picture. Leaving Placed lit would draw the box around a rectangle
        that is not this mode's."""
        block = script[script.index("function setMode"):]
        block = block[:block.index("\n}")]
        assert "setPlacing(" in block

    def test_the_mode_switch_leaves_the_other_controls_alone(self, script):
        """It used to uncheck every segmented option on the page, and Background has
        nothing that puts its own back: switching the mode left it showing neither
        of its two options until one was clicked."""
        block = script[script.index("function setMode"):]
        block = block[:block.index("\n}")]
        assert '.segmented__option[data-mode]' in block

    def test_a_placement_belongs_to_the_mode_that_made_it(self, script):
        """A video clip's rectangle is the frames and a card's is the artwork panel,
        and neither is the other's shape."""
        block = script[script.index("const sameKind"):]
        block = block[:block.index(";\n")]
        assert 'current.video' in block and 'mode === "video"' in block
        block = script[script.index("const placeable"):]
        block = block[:block.index(";\n")]
        assert "sameKind()" in block

    def test_choosing_placed_opens_the_section_the_box_is_in(self, script):
        """The control is in Look and the box is in the preview. Folded, that box
        is inside a closed `details`, which is `display: none`: pressing Placed
        looked like it did nothing, and the box could not even be focused."""
        block = script[script.index("function setPlacing(next)"):]
        block = block[:block.index("\n}")]
        assert '$("sec-preview")' in block and "rememberOpen()" in block

    def test_the_frame_holds_one_selection(self, script):
        """Two things selected is two answers to an arrow key."""
        block = script[script.index("function select(at)"):]
        block = block[:block.index("\n}")]
        assert "pickedPicture = false" in block
        block = script[script.index("function selectPicture"):]
        block = block[:block.index("\n}")]
        assert "deselect()" in block

    def test_the_placement_is_settled_before_the_mode_re_asks_it(self, script):
        """`setMode` re-asks the placement control, and it reads whatever `framing`
        holds at that moment. Asked before this clip's own placement was put there,
        it would answer about a rectangle belonging to the clip before it."""
        block = script[script.index("function recall(clip)"):]
        block = block[:block.index("\n}")]
        assert block.index("framing = job.framing") < block.index("setMode(")

    def test_the_clips_own_record_is_copied_rather_than_held(self, script):
        """Held by reference, the first nudge edits the clip's own placement through
        it, and the page is then comparing the placement against itself: the clip
        can never be called stale, and it goes out without the change in it. The
        stickers are copied one by one a few lines above for the same reason."""
        block = script[script.index("function recall(clip)"):]
        block = block[:block.index("\n}")]
        assert "{ ...job.framing }" in block, (
            "the placement is aliased to the clip's own record")

    def test_the_press_never_reaches_the_frames_own_handler(self, script):
        """That one reads a press outside a sticker as "put the selection down"."""
        block = script[script.index('$("picture-box").addEventListener("pointerdown"'):]
        block = block[:block.index("\n});")]
        assert "stopPropagation" in block


class TestExtrasReadsDownTheFrame:
    """Three boxes that each put a line somewhere, listed in the order they land on
    the frame rather than the order they were built. Finding the one you wanted used
    to mean reading all three."""

    def test_top_of_the_frame_first_and_the_footer_last(self, page):
        at = {name: page.index(f'id="{name}"')
              for name in ("topline", "eyebrow", "footer", "text-line")}
        assert at["topline"] < at["eyebrow"] < at["footer"] < at["text-line"]


class TestThePhoneKeepsItsOwnRunningOrder:
    """One column on a phone, and the DOM's two columns are the wrong sequence.

    Read straight through, the DOM gives form, stickers, recent, preview, post:
    the sticker shelf lands above the frame it decorates and Recent lands in the
    middle of the run. Both wrappers dissolve to `display: contents` so that every
    panel is a grid item in its own right, and `order` puts them back.
    """

    PANELS = ["#form", "#sec-preview", "#sec-stickers", "#sec-post", "#sec-recent"]

    def orders(self, styles: str) -> dict[str, int]:
        head = styles[:styles.index("@media (min-width: 600px)")]
        found = {}
        for panel in self.PANELS:
            match = re.search(re.escape(panel) + r"\s*\{[^}]*order:\s*(\d+)", head)
            assert match, f"{panel} has no order on a phone"
            found[panel] = int(match.group(1))
        return found

    def test_both_wrappers_dissolve_so_order_can_reach_the_panels(self, styles):
        head = styles[:styles.index("@media (min-width: 600px)")]
        assert re.search(r"#left,\s*#clipside\s*\{\s*display:\s*contents", head), (
            "`order` only moves grid items, so a panel inside a wrapper that is "
            "still a block cannot be reordered out of it")

    def test_every_panel_has_its_own_place(self, styles):
        places = self.orders(styles)
        assert len(set(places.values())) == len(places), (
            f"two panels share an order and the tie is resolved by DOM position: "
            f"{places}")

    def test_the_shelf_sits_between_the_frame_and_the_making_of_it(self, styles):
        """The reason the orders exist at all: you look, you decorate, you make."""
        at = self.orders(styles)
        assert at["#form"] < at["#sec-preview"] < at["#sec-stickers"] < at["#sec-post"]

    def test_the_old_clips_come_last(self, styles):
        at = self.orders(styles)
        assert at["#sec-recent"] == max(at.values())

    def test_the_columns_come_back_when_there_is_room(self, styles):
        wide = styles[styles.index("@media (min-width: 901px)"):]
        assert re.search(r"#clipside\s*\{[^}]*display:\s*grid", wide), (
            "left as `display: contents`, the clip column's panels would be placed "
            "into the grid one per row and pair up with the form's panels beside "
            "them, which is the row coupling the wrapper columns exist to avoid")
        assert re.search(r"#clipside\s*\{[^}]*grid-column:\s*2", wide)




class TestTheCardsAreOneRhythm:
    """D-070, reported on 2026-08-27 as "can you equi-space all these sections?"

    Every card on the page is the same card, and they read as one run. They were
    not spaced like one: the four inside the form are a `.stack` and the four
    around it are items of the page grid, and the two used different tokens. From
    600px that was 12 pixels between the first four and 20 between the rest, on an
    unbroken column of identical boxes.
    """

    def gap(self, block: str, selector: str) -> str:
        found = re.search(re.escape(selector) + r"\s*\{[^}]*gap:\s*([^;]+);", block)
        assert found, f"{selector} has no gap"
        return found.group(1).strip()

    def test_a_phone_spaces_them_all_the_same(self, styles):
        head = styles[:styles.index("@media (min-width: 600px)")]
        assert self.gap(head, ".grid") == self.gap(head, ".stack")

    def test_and_so_does_everything_wider(self, styles):
        """The one that was wrong. Both tokens have to move together, or the run
        of cards has a seam in it where the form ends."""
        wider = styles[styles.index("@media (min-width: 600px)"):]
        wider = wider[:wider.index("@media (min-width: 901px)")]
        assert self.gap(wider, ".grid") == self.gap(wider, ".stack")

    def test_the_frame_column_keeps_step_with_them(self, styles):
        """It declares its own, being a real column again at 901px."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        assert self.gap(wide, "#left") == self.gap(wide, "#clipside")

class TestTheDesktopKeepsTheFrameInFront:
    """D-067, asked for on 2026-08-27. Two columns on a laptop: everything you
    answer on the left, scrolling as long as it likes, and the frame it is all
    about stuck to the top of the screen on the right.

    The reason is a real failure, not a preference. The sticker shelf is halfway
    down the left column and a sticker is dragged from it onto the frame; before
    this, scrolling far enough to reach the shelf scrolled the frame off the
    screen. Same for the buttons that send.
    """

    def test_post_it_moved_into_the_scrolling_column(self, page):
        assert inside(page, 'id="left"', 'id="clipside"', 'id="sec-post"')

    def test_and_sits_above_the_old_clips_where_the_run_ends(self, page):
        assert page.index('id="sec-post"') < page.index('id="sec-recent"')

    def test_the_stuck_column_holds_the_frame_and_nothing_else(self, page):
        """Anything else in there is height, and height is what stops a stuck
        column fitting on the screen at all."""
        rest = page[page.index('id="clipside"'):page.index("</main>")]
        assert re.findall(r'id="(sec-\w+)"', rest) == ["sec-preview"]

    def test_it_is_stuck_only_where_there_are_two_columns(self, styles):
        head = styles[:styles.index("@media (min-width: 901px)")]
        assert "position: sticky" not in head[head.index("#left, #clipside"):], (
            "a phone has one column and nothing to stick beside")

    def test_and_it_is_stuck_under_the_top_bar_rather_than_over_it(self, styles):
        """The top bar is sticky itself. Stick this at 0 and the card slides under
        a bar that is already there."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        rule = wide[wide.index("#clipside {"):]
        rule = rule[:rule.index("\n  }")]
        assert "position: sticky" in rule
        assert re.search(r"top:\s*calc\(\s*var\(--topbar", rule), (
            "the offset has to be the bar's own height, which only the script "
            "knows: it grows a tagline at 600px")

    def test_the_bar_is_measured_rather_than_guessed(self, script):
        assert 'setProperty(\n    "--topbar"' in script or \
               'setProperty("--topbar"' in script
        assert ".topbar" in script[:script.index("measureTopbar")]

    def test_and_the_stylesheet_still_works_if_the_script_never_runs(self, styles):
        """Every read of it carries a fallback, so the frame is the right size on
        the first paint and stays right if the script dies."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        uses = re.findall(r"var\(--topbar[^)]*\)", wide)
        assert uses, "nothing reads the measurement"
        assert all("," in use for use in uses), f"a read with no fallback: {uses}"

    def test_the_frame_shrinks_to_what_is_left_of_the_screen(self, styles):
        """A stuck card taller than the screen is a card whose bottom, which is the
        player, cannot be reached. So on a short screen the frame takes the height
        that is left and `aspect-ratio` turns it back into a width."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        rule = wide[wide.index(".phone__screen, .player {"):]
        rule = rule[:rule.index("\n  }")]
        assert "clamp(" in rule and "100vh" in rule
        assert "300px" in rule, "the frame is still never bigger than it was"

    def test_the_frame_grows_where_the_page_has_reached_its_full_width(self, styles):
        """Asked for on 2026-08-27 as "slightly bigger". 360 is exactly a third of
        the 1080 the clip is drawn at, and about the width of a real phone.

        Not at 901px, where the extra 60 pixels would come out of the column that
        holds every field: around there that is the difference between two fields
        on a row and one. So it is its own query at the grid's own `max-width`.
        """
        wide = styles[styles.index("@media (min-width: 901px)"):]
        assert "--frame-max" in wide[:wide.index("@media (min-width: 1180px)")], (
            "the ceiling has to be a variable for a later query to raise it")
        bigger = wide[wide.index("@media (min-width: 1180px)"):]
        assert re.search(r"--frame-max:\s*360px", bigger)
        assert re.search(r"\.grid\s*\{[^}]*minmax\(0,\s*394px\)", bigger), (
            "a wider frame needs a wider column, or it is clipped by the one it "
            "is in")

    def test_and_a_narrow_laptop_keeps_the_frame_it_had(self, styles):
        """The whole reason for the second query."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        at_901 = wide[:wide.index("@media (min-width: 1180px)")]
        assert re.search(r"--frame-max:\s*300px", at_901)
        assert re.search(r"\.grid\s*\{[^}]*minmax\(0,\s*334px\)", at_901)

    def test_the_frame_column_is_sized_to_the_frame(self, styles):
        """Half the page, with only the preview left in it, is a column of empty
        space taken from the fields on the other side."""
        wide = styles[styles.index("@media (min-width: 901px)"):]
        cols = re.search(r"\.grid\s*\{[^}]*grid-template-columns:\s*([^;]+);", wide)
        assert cols, "the two column rule has gone"
        assert "1fr) minmax(0, 1fr)" not in cols.group(1), (
            "an even split leaves the frame's column half empty")



class TestThePageSaysEachThingOnce:
    """D-069, reported on 2026-08-27 looking at the footer.

    Two lines sat at the bottom of every page. One named the output folder and the
    retention, a long way from the strip of clips it describes. The other named the
    address a phone can reach, which the health chip at the top of the page already
    says, in a row that names the port with it.
    """

    def test_where_the_clips_are_is_under_the_clips(self, page):
        assert inside(page, 'id="sec-recent"', "</details>", 'id="foot-out"')

    def test_and_no_longer_in_the_footer(self, page):
        assert not inside(page, "<footer", "</footer>", 'id="foot-out"'), (
            "it is in both places now, which is the thing that was reported")

    def test_it_comes_after_the_strip_it_is_about(self, page):
        assert page.index('id="recent"') < page.index('id="foot-out"')

    def test_the_script_still_finds_it(self, script):
        """It moved and changed tag. The lookup is by id, so this is a check that
        the id survived the move rather than a check on the move."""
        assert '$("foot-out").textContent' in script

    def test_the_address_a_phone_is_given_carries_the_port(self, script):
        """An address with no port is not something anybody can type in. The status
        panel's own row has always said it this way; this line had not."""
        block = script[script.index('$("foot-reach").textContent'):]
        block = block[:block.index("$(\"status-where\")")]
        assert "location.port" in block, (
            "the reachable line names a bare address again")

    def test_the_footer_is_folded_away_where_the_chip_is_always_on_screen(self, styles):
        wide = styles[styles.index("@media (min-width: 901px)"):]
        assert re.search(r"\.foot\s*\{\s*display:\s*none", wide)

    def test_but_a_phone_keeps_it(self, styles):
        """The top of the page is a long way from the bottom on a phone, and the
        bottom is where you are when you want the address."""
        head = styles[:styles.index("@media (min-width: 600px)")]
        rule = head[head.index(".foot {"):]
        rule = rule[:rule.index("\n}")]
        assert "display: flex" in rule

class TestTheFoldControlIsBigEnoughToAimAt:
    """Reported on 2026-08-27 as too small. It was an 18px filled triangle; it is a
    24px chevron in a 32px round target. D-068."""

    def test_it_is_a_chevron_now(self, page):
        assert 'd="M7 10l5 5 5-5z"' not in re.sub(
            r'<svg class="statuschip__caret".*?</svg>', "", page, flags=re.S), (
            "a card still carries the old filled triangle")

    def test_every_card_has_one(self, page):
        assert page.count('class="accordion__caret"') == page.count("<details")

    def test_the_top_bar_s_own_caret_is_left_alone(self, page):
        """It says a panel drops down, not that a card is folded, and it is not
        the thing anybody complained about."""
        assert 'class="statuschip__caret"' in page

    def test_the_glyph_and_its_target_are_both_bigger(self, styles):
        rule = styles[styles.index(".accordion__caret {"):]
        rule = rule[:rule.index("\n}")]
        assert "32px" in rule and "padding: 4px" in rule, (
            "32 less 4 of padding each side is the 24px glyph that was asked for")
        assert "border-box" in rule, "without it the padding makes the target 40px"

    def test_it_still_turns_over_to_say_the_card_is_open(self, styles):
        assert re.search(r"\.accordion\[open\][^{]*\.accordion__caret\s*\{[^}]*"
                         r"rotate\(180deg\)", styles)


class TestTheWarningIsWhereTheActionIs:
    """D-056. The Stickers panel already said "make the clip again"; it is in a
    different card from the buttons that send, and on 2026-08-25 the owner posted
    a clip made before the GIF was placed. The notice is beside the buttons now.
    """

    ACTIONS = ["load", "send", "download"]

    def test_the_notice_lives_in_the_post_panel(self, page):
        assert inside(page, 'id="sec-post"', "</details>", 'id="post-stale"')

    def test_it_comes_before_the_buttons_it_is_about(self, page):
        assert page.index('id="post-stale"') < page.index('class="doers"')

    def test_it_starts_hidden(self, page):
        assert re.search(r'id="post-stale"[^>]*\bhidden\b', page)

    @pytest.mark.parametrize("action", ACTIONS)
    def test_every_acting_button_is_guarded(self, action, script):
        assert re.search(rf'\$\("{action}"\)\.addEventListener\("click",[^;]*?'
                         rf'pastStale\(\$\("{action}"\)', script, re.S), (
            f"{action} can act on a clip that no longer matches the form")

    def test_download_is_given_the_event_because_it_is_a_link(self, script):
        """The other two are buttons whose handlers simply return early. Download
        is an anchor, and the browser follows it unless the event is cancelled."""
        block = script[script.index('$("download").addEventListener'):]
        block = block[:block.index("\n});")]
        assert "event" in block and "pastStale($(\"download\"), event)" in block
        assert "event.preventDefault" in script[script.index("function pastStale"):]

    def test_the_link_and_the_window_are_deliberately_not_drift(self, script):
        """Pasting the next link with a finished clip still on show is ordinary
        work, and a warning that fires on ordinary work is learned as noise."""
        block = script[script.index("const DRIFTABLE"):]
        block = block[:block.index("];")]
        for field in ("url", "start", "end", "duration"):
            assert f'"{field}"' not in block, (
                f"{field} counts as drift, which will fire while setting up the "
                "next clip rather than when about to send the wrong one")

    def test_what_does_count_is_what_is_drawn_into_the_pixels(self, script):
        block = script[script.index("const DRIFTABLE"):]
        block = block[:block.index("];")]
        for field in ("title", "channel", "footer", "eyebrow", "topline"):
            assert f'"{field}"' in block, f"{field} is drawn on the clip but is not drift"
        after = script[script.index("function drifted"):]
        after = after[:after.index("\n}")]
        assert "sameStickers" in after and "wave" in after and "mode" in after


class TestThePencilOnALineOfWords:
    """Asked for on 2026-08-27: a pencil on hover, over text on the preview, that
    opens the same editing the box below does. D-063.

    The whole of it rests on there being one box that writes free text, whether the
    line is new or being retyped. The pencil takes the hand to that box; it does not
    open a second editor over the frame.
    """

    def test_only_free_text_carries_one(self, script):
        block = script[script.index("function handles(decal)"):]
        block = block[:block.index("\n}")]
        assert "isText(decal)" in block and '"edit"' in block

    def test_the_box_says_which_kind_it_is(self, script):
        """The stylesheet is what asks, and it can only ask of a class."""
        block = script[script.index("const box = document.createElement"):]
        block = block[:block.index("box.dataset.at")]
        assert "decal--text" in block

    def test_a_press_on_it_never_starts_a_drag(self, script):
        """Every other handle falls through into the resize and rotate gesture. A
        pencil that did would resize the line by however far the hand moved."""
        block = script[script.index("function onHandleDown"):]
        block = block[:block.index("const centre = centreOf(box)")]
        assert 'handle.dataset.handle === "edit"' in block
        assert "editText(at)" in block

    def test_it_opens_an_editor_on_the_line_itself(self, script):
        """D-076: the pencil edits where the line is, not somewhere down the page."""
        block = script[script.index("function editText(at)"):]
        block = block[:block.index("\n}\n")]
        assert 'createElement("input")' in block
        assert "decal__edit" in block
        assert ".focus(" in block and ".select()" in block
        # The drawing is hidden while the input is over it, or the words are on the
        # frame twice.
        assert "decal--editing" in block

    def test_it_still_has_the_box_to_fall_back_on(self, script):
        """The decal layer is folded away once a clip is made, and there is then
        nothing on the frame to type into."""
        block = script[script.index("function editText(at)"):]
        block = block[:block.index("\n}\n")]
        assert "openTextField(one)" in block
        field = script[script.index("function openTextField(one)"):]
        field = field[:field.index("\n}\n")]
        for wanted in ('$("sec-extras")', '$("text-line")', ".focus(", ".select()"):
            assert wanted in field, wanted

    def test_both_boxes_write_one_string(self, script):
        """Typing in either has to reach the other, and neither may be rewritten
        under its own caret: that sends the cursor to the end."""
        block = script[script.index("function applyText(value, from)"):]
        block = block[:block.index("\n}\n")]
        assert 'from !== "field"' in block and 'from !== "inline"' in block
        assert "one.text = value" in block
        handler = script[script.index('$("text-line").addEventListener("input"'):]
        handler = handler[:handler.index("});")]
        assert 'applyText($("text-line").value, "field")' in handler

    def test_it_is_offered_on_hover_and_only_where_there_is_a_mouse(self, styles):
        """The same query the dashed outline uses, for the same reason. A phone
        reports `hover: none` and never matches it."""
        blocks = [chunk for chunk in styles.split("@media (hover: hover)")[1:]
                  if not chunk.lstrip().startswith("and")]
        assert any(".decal--text:hover .decal__handle--edit" in chunk[:chunk.index("\n}\n")]
                   for chunk in blocks)

    def test_a_touch_screen_keeps_the_cross_and_nothing_else(self, styles):
        """D-038: a default sticker is 76 pixels to hit and two fingertip targets
        need 88 between them, so there is room for exactly one handle."""
        block = styles[styles.index("@media (hover: none) and (pointer: coarse)"):]
        block = block[:block.index("\n}\n")]
        assert "--edit { display: none; }" in block or "--edit," in block

    def test_the_pale_icons_are_not_drawn_on_a_light_page(self, styles):
        """`:root:not([data-theme=\"light\"])` matches a page whose theme is left on
        system, which is the default. Unguarded, it drew a near-white pencil on a
        near-white circle for anybody who had never touched the theme button."""
        for handle in ("edit", "rotate"):
            bare = f':root:not([data-theme="light"]) .decal__handle--{handle}'
            at = styles.index(bare)
            before = styles[:at]
            opened = before.rindex("@media (prefers-color-scheme: dark)")
            assert "\n}" not in styles[opened:at].rsplit("{", 1)[-1], (
                f"the pale {handle} icon is outside the dark media query")



class TestTheFetchIconInTheWordsHeader:
    """Asked for on 2026-08-27: an icon that reads the title and second line off
    the video, so they can be corrected before the clip rather than after it.
    D-064.

    It sits in a `<summary>`, which is the interesting part: everything in there is
    the accordion's own control surface, so a press that is not stopped folds the
    card as it acts. `Clear` in the clip header already had to solve this, and this
    test class exists because the next icon put in a header will not.
    """

    def test_it_lives_in_the_header_of_the_card_it_fills(self, page):
        block = page[page.index('id="sec-words"'):]
        summary = block[block.index("<summary>"):block.index("</summary>")]
        assert 'id="words-fetch"' in summary, (
            "the fetch icon has left the header; a folded card can no longer reach it")

    def test_the_answer_appears_beside_it(self, page):
        """The value in the same row is the fetched words, so a press on a folded
        card is answered without opening it."""
        block = page[page.index('id="sec-words"'):]
        summary = block[block.index("<summary>"):block.index("</summary>")]
        assert summary.index('id="words-fetch"') < summary.index('id="val-words"')

    def test_an_icon_with_no_words_says_what_it_is_for(self, page):
        tag = re.search(r'<button[^>]*id="words-fetch"[^>]*>', page, re.S)
        assert tag and "aria-label=" in tag.group(0), (
            "an icon button with no label is unreadable to a screen reader")

    def test_the_press_never_folds_the_card_it_is_in(self, script):
        block = script[script.index('$("words-fetch").addEventListener'):]
        block = block[:block.index("\n});")]
        assert "preventDefault()" in block and "stopPropagation()" in block

    def test_filling_the_boxes_by_hand_still_reaches_everything_typing_does(
            self, script):
        """Setting `.value` fires no `input` event, so the three things a keystroke
        would have done have to be called. Miss `wordsChanged` and the frame above
        shows the old words; miss `remember` and a reload loses the new ones."""
        block = script[script.index("async function fetchWords()"):]
        block = block[:block.index("\n}\n")]
        for wanted in ("remember()", "wordsChanged()", "wordsBelongTo("):
            assert wanted in block, wanted

    def test_the_words_are_stamped_with_the_video_they_came_from(self, script):
        """Without this they are words with no owner, and the link changing under
        them leaves one song's title on another song's card."""
        block = script[script.index("async function fetchWords()"):]
        block = block[:block.index("\n}\n")]
        assert "wordsBelongTo($(\"url\").value)" in block

    def test_a_slow_answer_cannot_land_on_a_link_that_has_moved_on(self, script):
        """Two guards, and both are needed. The counter throws away an older press
        that finishes second; the key throws away an answer for a video that is no
        longer in the box, which a counter cannot see."""
        block = script[script.index("async function fetchWords()"):]
        block = block[:block.index("\n}\n")]
        assert "mine !== fetchingWords" in block
        assert "videoKey($(\"url\").value) !== asked" in block

    def test_the_spinner_belongs_to_the_press_that_started_it(self, script):
        block = script[script.index("async function fetchWords()"):]
        block = block[:block.index("\n}\n")]
        finally_block = block[block.index("} finally {"):]
        assert "mine === fetchingWords" in finally_block, (
            "an older press finishing late would stop a newer press's spinner")

    def test_a_failure_is_shown_where_the_boxes_are(self, page, script):
        """The card may be folded, and an alert inside a folded card is a silence."""
        assert 'id="words-error"' in page
        assert 'hidden' in re.search(r'<p[^>]*id="words-error"[^>]*>', page).group(0)
        block = script[script.index("async function fetchWords()"):]
        block = block[:block.index("\n}\n")]
        assert 'openSection("words", true)' in block
        assert 'fail($("words-error")' in block

    def test_the_working_state_survives_a_page_that_refuses_animation(self, styles):
        """The reduced-motion rule at the top of the stylesheet turns off every
        animation on the page, so a spin is not on its own enough to say working."""
        block = styles[styles.index('.headeraction[data-working="true"]'):]
        block = block[:block.index("@keyframes spin")]
        assert "@media (prefers-reduced-motion: reduce)" in block
        assert "opacity" in block.split("@media (prefers-reduced-motion: reduce)")[1]

    def test_the_icon_is_a_thumb_sized_target(self, styles):
        block = styles[styles.index(".headeraction {"):]
        block = block[:block.index("\n}")]
        assert "36px" in block

    def test_it_does_not_share_a_class_with_the_top_bar_s_buttons(self, styles):
        """It did, until 2026-08-27. `.iconbutton` is the top bar's theme and
        health buttons, which are bordered and sit on a surface; this one is a bare
        glyph in a card header. Written second and with the same selector, it took
        the border and the background off the theme button in the top bar, where
        nobody was looking. Two buttons, two names. D-068.
        """
        rules = re.findall(r"^\.iconbutton\s*\{", styles, re.M)
        assert rules, ("the top bar's own `.iconbutton` rule has gone; if it was "
                       "renamed, this test is asking about the wrong name")
        assert len(rules) == 1, (
            "two rules named `.iconbutton`: the later one wins for both buttons, "
            "and one of them is not the button it was written for")


class TestTheButtonGoesQuietWhenThereIsNothingToDo:
    """Asked for on 2026-08-27: grey Make the clip out once the clip is made, and
    bring it back the moment anything changes. D-066.

    The trap is that the page already had a "has anything changed" function, and it
    answers a different question: `drifted` leaves the link and the window out on
    purpose, so a button wired to it alone would stay grey after a new link was
    pasted, which is the most ordinary thing anybody does here.
    """

    def test_the_link_and_the_window_are_what_drifted_does_not_cover(self, script):
        block = script[script.index("function settled()"):]
        block = block[:block.index("\n}\n")]
        assert "videoKey($(\"url\").value)" in block, "a new link must bring it back"
        for wanted in ('seconds($("start").value)', "job.start", "job.end"):
            assert wanted in block, wanted

    def test_and_everything_drifted_does_cover_is_still_counted(self, script):
        block = script[script.index("function settled()"):]
        block = block[:block.index("\n}\n")]
        assert "drifted().length" in block

    def test_it_is_only_ever_grey_when_there_is_a_clip_on_screen(self, script):
        block = script[script.index("function settled()"):]
        block = block[:block.index("\n}\n")]
        assert "if (!job || !current.stem) return false;" in block

    def test_the_keyboard_cannot_get_past_a_grey_button(self, script):
        """`requestSubmit` does not ask the button whether it is enabled, so
        Ctrl+Enter would still start a render nobody could see the point of."""
        block = script[script.index('$("form").addEventListener("submit"'):]
        block = block[:block.index("hide($(\"error\"))")]
        assert "if (working || settled()) return;" in block, (
            "a render in flight, or nothing to do, must both stop the keyboard")

    def test_the_repaint_hangs_off_the_one_place_every_change_reaches(self, script):
        """`paintStale` is called by `paintSummaries`, which is called by `remember`,
        which every control on the page calls. Hooking it there is what makes
        "anywhere else" true rather than a list to keep up to date."""
        block = script[script.index("function paintStale()"):]
        block = block[:block.index("\n}\n")]
        assert "paintMake()" in block

    def test_a_render_in_flight_still_disables_it(self, script):
        block = script[script.index("function paintMake()"):]
        block = block[:block.index("\n}\n")]
        assert "working" in block

    def test_the_grey_button_says_why(self, page, script):
        """A dead control with no explanation is a bug report waiting to happen."""
        assert 'id="make-note"' in page
        block = script[script.index("function paintMake()"):]
        block = block[:block.index("\n}\n")]
        assert '$("make-note").hidden' in block

    def test_the_safe_area_guides_are_deliberately_not_a_change(self, script):
        """They change the preview and never the pixels, so making the clip again
        for them would produce the same file."""
        block = script[script.index("function settled()"):]
        block = block[:block.index("\n}\n")]
        assert "guides" not in block


class TestThePreviewSaysWhatItCannotShow:
    """Reported 2026-08-31: placing a GIF warned in the Post it panel and said
    nothing in the preview pane beside it, while changing a word warned in both.
    One clip, two stories. See DECISIONS.md D-077."""

    def test_a_sticker_change_reaches_the_preview_pane(self, script):
        block = script[script.index("function changed()"):]
        block = block[:block.index("\n}\n")]
        assert "wordsChanged()" in block

    def test_the_waveform_reaches_it_too(self, script):
        assert 'wordsChanged(); });' in script[
            script.index('$("wave").addEventListener'):][:200]

    def test_it_names_what_it_cannot_draw_rather_than_going_quiet(self, script):
        block = script[script.index("function sayUndrawable()"):]
        block = block[:block.index("\n}\n")]
        assert "drifted()" in block
        assert "UNDRAWABLE" in block
        table = script[script.index("const UNDRAWABLE = {"):]
        table = table[:table.index("};")]
        # The three the server cannot put in a still: the page draws stickers over
        # the frame itself, ffmpeg draws the waveform, and the mode changes both.
        for wanted in ("the stickers", "the waveform", "the look"):
            assert wanted in table, wanted

    def test_nothing_drifting_says_nothing(self, script):
        """A pane that talks when there is nothing to say is noise."""
        block = script[script.index("function sayUndrawable()"):]
        block = block[:block.index("\n}\n")]
        assert "if (!cannot.length) return hide(note);" in block


class TestTopTextThatDoesNotFit:
    """It used to be drawn as nothing, with the words still in the box and still in
    the sidecar, so the page reported the clip up to date with a line it had never
    drawn. See DECISIONS.md D-075."""

    def test_the_pane_says_so_before_anything_else(self, script):
        block = script[script.index("const lost = Number(answer.headers"):]
        block = block[:block.index("say($(\"wordshot-note\"),\n      !wordsDiffer()")]
        assert "X-Dropped-Toplines" in block
        assert "does not fit" in block
        assert "Move it down" in block
        # `return`, so the "preview of the words" line never overwrites it.
        assert "return say(" in block


class TestSchedulingControls:
    """Scheduled Statuses on the hosted page (docs/scheduling.md, FR-1, U9, U10).

    The controls are in `index.html`, which the local tool serves too, so what
    keeps them out of the local tool is that they start hidden and only the hosted
    script (`window.SnipShare`) ever shows them. A control that starts visible, or
    a submit button that loses its form, breaks without raising anything.
    """

    HIDDEN_AT_START = ("doer-schedule", "sched", "sched-phone", "upnext")

    @pytest.mark.parametrize("name", HIDDEN_AT_START)
    def test_it_starts_hidden(self, page, name):
        tag = re.search(rf"<[a-z]+[^>]*id=\"{name}\"[^>]*>", page, re.S)
        assert tag and re.search(r"\shidden[\s>]", tag.group(0)), (
            f"{name} must start hidden: the local tool never shows it")

    def test_the_primary_stays_load_into_whatsapp(self, page):
        assert 'id="load">Load into WhatsApp</button>' in page
        assert re.search(r'id="schedule"[^>]*>Schedule</button>', page, re.S)
        # It is not the filled button: only #load and the picker's own save are.
        doer = re.search(r'<div class="doer" id="doer-schedule".*?</div>', page, re.S).group(0)
        assert "button--primary" not in doer

    def test_one_schedule_button_and_no_separate_add_to_queue(self, page, script):
        """The owner's choice, 2026-10-31: one Schedule button, whose picker offers
        the queue first, rather than Schedule and Add to queue side by side."""
        doer = re.search(r'<div class="doer" id="doer-schedule".*?</div>', page, re.S).group(0)
        assert doer.count("<button") == 1
        assert 'id="queue-add"' not in page and "Add to queue" not in page
        assert "queue-add" not in script and "schedMode" not in script
        assert ("Puts the clip in WhatsApp at the time you choose, or next in your queue. "
                "You press Send.") in re.sub(r"\s+", " ", doer)
        css = (WEB.parent / "pages" / "hosted.css").read_text(encoding="utf-8")
        assert "schedbtns" not in css and "schedbtns" not in page
        styles = (WEB / "app.css").read_text(encoding="utf-8")
        assert ".doer .button { width: 100%; }" in styles, "full width of its cell"

    def test_next_in_queue_is_the_first_preset_and_the_one_chosen(self, script):
        body = script[script.index("function schedPresets"):script.index("const localValue")]
        assert 'list.unshift({ key: "last"' in body
        assert "Next in queue \\u00b7 ${shortDue(next, now.getTime())}" in body
        assert '"Next in queue", date: null' in body, "an older extension: no time"
        opened = script[script.index("function openSched"):script.index("function closeSched")]
        assert "chooseSched(schedPresets()[0].key)" in opened
        assert "HOSTED.peek()" in opened, "the queue is asked afresh when the picker opens"
        read = script[script.index("function readSched"):script.index("function chooseSched")]
        assert '"After your last scheduled post"' in read
        assert "return { afterLast: true };" in read

    def test_the_next_in_queue_time_follows_the_extensions_own_rule(self, script):
        """Q.afterLast in src/queue.js: after the last pending post by the gap, never
        under the minimum lead, moved out of quiet hours to where they end. The
        fields are the extension's (`queue-peek`), since the page cannot read the
        person's settings; src/test/schedule.test.js checks the two agree."""
        body = script[script.index("function nextInQueue"):script.index("function quietSpan")]
        assert '!("lastDue" in found) || !Number(found.gapMinutes)' in body
        assert "Math.max(now, Number(found.lastDue) || 0)" in body
        assert "Math.max(last + Number(found.gapMinutes) * 60000, now + SCHED_MIN_MS)" in body
        assert "quietSpan(found.quiet)" in body
        assert "if (found) schedPeek = found;" in script, "Up next's answer is kept for it"
        worker = (WEB.parent.parent / "src" / "schedule.js").read_text(encoding="utf-8")
        peek = worker[worker.index("async function peek()"):]
        peek = peek[:peek.index("\n    }\n")]
        for field in ("lastDue:", "gapMinutes:", "quiet: quietOf(s)"):
            assert field in peek, field

    def test_the_save_button_is_inside_the_picker_form(self, page):
        assert inside(page, '<form class="sched" id="sched"', "</form>", 'id="sched-save"')
        tag = re.search(r'<button[^>]*id="sched-save"[^>]*>', page, re.S).group(0)
        assert 'type="submit"' in tag

    def test_the_picker_says_what_it_does(self, page):
        form = page[page.index('id="sched"'):page.index("</form>", page.index('id="sched"'))]
        assert "Puts it in WhatsApp for you to send" in form
        assert "Keep Chrome open" in form and "computer awake" in form
        assert 'type="datetime-local"' in form
        assert 'id="sched-words"' in form, "the interpreted time in words"
        assert 'for="sched-caption"' in form

    def test_the_phone_line_is_the_one_the_plan_words(self, page):
        assert ("Scheduling works in Chrome on a computer with the extension"
                in re.sub(r"\s+", " ", page))

    def test_the_scripts_ask_only_the_hosted_bridge(self, script):
        # Every entry point goes through HOSTED, which the local page does not have.
        assert "HOSTED.canSchedule()" in script
        for call in ("HOSTED.schedule(", "HOSTED.peek()", "HOSTED.openQueue()"):
            assert call in script
        assert 'id="schedule"' not in script, "the buttons are markup, not built by script"
        for name in ("schedule", "queue-open", "sched-cancel"):
            assert f'$("{name}").addEventListener("click"' in script

    def test_up_next_goes_to_the_accounts_scheduled_section(self, script):
        """One queue UI: Up next's Scheduled opens the account's Scheduled Statuses
        section in this tab, as the Account link does (docs/account-page.md, AP-8).
        The extension's own tab stays for the toast and for the section's fallback."""
        assert ('$("queue-open").addEventListener("click", () => '
                'location.assign("/account#scheduled"));') in script
        assert '$("queue-open").addEventListener("click", openQueuePage)' not in script
        assert 'run: () => openQueuePage()' in script
        account = (WEB.parent / "pages" / "account.js").read_text(encoding="utf-8")
        assert 'cmd: "open-queue"' in account

    def test_the_account_frames_the_queue_from_its_extension_alone(self):
        account = (WEB.parent / "pages" / "account.js").read_text(encoding="utf-8")
        page = (WEB.parent / "pages" / "account.html").read_text(encoding="utf-8")
        assert '"history", "scheduled", "keys"' in account, "after History"
        assert "event.origin !== EXT_ORIGIN || event.source !== frame.contentWindow" in account
        assert "/queue.html?embed=1&theme=" in account
        assert "frame.title = " in account
        assert re.search(r'postMessage\(\{ snipshareTheme: [^}]*\}, EXT_ORIGIN\)', account)
        assert '"*"' not in account
        assert 'href="#scheduled" data-section="scheduled"' in page
        assert page.index('data-section="history"') < page.index('data-section="scheduled"') \
            < page.index('data-section="keys"')
        for line in ("Scheduling works in Chrome on a computer with the extension",
                     "Get the extension", "Update the extension", "Open the queue in its own tab"):
            assert line in account + page, line

    def test_every_error_code_the_worker_gives_has_words(self, script):
        body = script[script.index("function schedProblem"):script.index('$("schedule").addEventListener')]
        for code in ("past", "far", "limit", "budget", "quota", "network", "gone",
                     "size", "stopped"):
            assert re.search(rf"\b{code}:", body), code

    def test_presets_that_have_passed_are_not_offered(self, script):
        assert ".filter((p) => p.date.getTime() - now.getTime() >= SCHED_MIN_MS)" in script
        assert '"quiet hours"' in script

    def test_prepare_is_the_only_action(self):
        hosted = (WEB.parent / "pages" / "hosted.js").read_text(encoding="utf-8")
        assert 'action: "prepare"' in hosted
        assert 'action: "send"' not in hosted

    def test_the_bridge_checks_the_extension_feature_and_the_pilot(self):
        hosted = (WEB.parent / "pages" / "hosted.js").read_text(encoding="utf-8")
        assert 'extension.features.includes("schedule")' in hosted
        assert "scheduling.enabled" in hosted
        assert "!mobile" in hosted or "mobile" in hosted
        for cmd in ('cmd: "schedule"', 'cmd: "queue-peek"', 'cmd: "open-queue"'):
            assert cmd in hosted

    def test_the_styles_keep_the_hidden_attribute_in_force(self):
        css = (WEB.parent / "pages" / "hosted.css").read_text(encoding="utf-8")
        assert "#doer-schedule[hidden]" in css and ".sched[hidden]" in css

    def test_a_stale_clip_holds_back_the_schedule_button_once(self, script):
        assert 'download: "Download",\n                      schedule: "Schedule" };' in script
        assert 'pastStale($("schedule"), event)' in script
        # Closing an open picker is checked before the stale press, so it is never held.
        body = script[script.index('$("schedule").addEventListener("click"'):]
        assert body.index("closeSched()") < body.index('pastStale($("schedule")')


class TestTheSiteFooterHasNoFinePrint:
    """The owner's review, 2026-10-31: the footer's "independent, experimental
    project" paragraph is gone from every site page. The same statement stays where
    it is asked about, in the Terms and the home page's questions."""

    PAGES = WEB.parent / "pages"

    def test_the_footer_carries_no_affiliation_paragraph(self):
        layout = (self.PAGES / "layout.html").read_text(encoding="utf-8")
        footer = layout[layout.index("<footer"):layout.index("</footer>")]
        assert "foot__fine" not in layout
        assert "experimental" not in footer and "affiliated" not in footer
        assert "Contact:" in footer and 'href="/terms"' in footer

    def test_its_style_went_with_it(self):
        assert "foot__fine" not in (self.PAGES / "site.css").read_text(encoding="utf-8")

    def test_the_terms_and_the_questions_still_say_it(self):
        terms = (self.PAGES / "terms.html").read_text(encoding="utf-8")
        assert "<h2>Not affiliated</h2>" in terms
        home = (self.PAGES / "home.html").read_text(encoding="utf-8")
        assert "independent experiment" in home


@pytest.fixture(scope="module")
def hosted() -> str:
    return (WEB.parent / "pages" / "hosted.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css() -> str:
    return (WEB.parent / "pages" / "hosted.css").read_text(encoding="utf-8")


class TestTheAccountMenu:
    """The app page's Account chip opens a menu of the account page's sections
    (owner's review, 2026-10-31), on the WAI-ARIA menu button pattern. The site
    pages' own avatar is a plain link with no menu (nav.js), so there was nothing to
    share, and this lives in hosted.js alone."""

    def test_the_chip_is_a_menu_button(self, hosted):
        body = hosted[hosted.index("function accountMenu"):]
        assert 'document.createElement("button")' in body
        assert 'chip.type = "button"' in body
        for attribute in ('"aria-haspopup", "menu"', '"aria-expanded", "false"',
                          '"aria-controls", "account-menu"'):
            assert attribute in body, attribute
        assert 'menu.setAttribute("role", "menu")' in body
        assert 'element.setAttribute("role", "menuitem")' in body
        assert 'setAttribute("role", "separator")' in body
        assert "accountLink" not in hosted and 'link.href = "/account"' not in hosted

    def test_the_items_and_where_they_go(self, hosted):
        body = hosted[hosted.index("function accountItems"):hosted.index("function accountMenu")]
        order = ['"Profile", href: "/account#profile"', '"History", href: "/account#history"',
                 '"Scheduled Statuses", href: "/account#scheduled"',
                 '"Extension", href: "/account#extension"', '"Admin", href: "/admin"',
                 "separator: true", '"Sign out", signOut: true']
        at = [body.index(item) for item in order]
        assert at == sorted(at), "in this order"
        assert "scheduling.enabled ? [{ label: \"Scheduled Statuses\"" in body
        assert "me.admin ? [{ label: \"Admin\"" in body

    def test_the_account_sections_it_names_exist(self):
        page = (WEB.parent / "pages" / "account.html").read_text(encoding="utf-8")
        for name in ("profile", "history", "scheduled", "extension"):
            assert f'id="{name}"' in page, name

    def test_sign_out_is_the_account_pages_own(self, hosted):
        account = (WEB.parent / "pages" / "account.js").read_text(encoding="utf-8")
        call = ('fetch("/api/signout", { method: "POST",\n'
                '      headers: { "Content-Type": "application/json", "X-SnipShare": "1" }, body: "{}",')
        assert call in account
        body = hosted[hosted.index("async function signOut"):]
        assert ('fetch("/api/signout", { method: "POST",\n'
                '        headers: { "Content-Type": "application/json", "X-SnipShare": "1" }, body: "{}",') in body
        assert 'if (done) return location.assign("/");' in body
        assert 'if (done) return location.assign("/");' in account, "the same destination"

    def test_the_keys_the_pattern_asks_for(self, hosted):
        body = hosted[hosted.index("function accountMenu"):]
        for key in ('"ArrowDown"', '"ArrowUp"', '"Home"', '"End"', '"Escape"', '"Tab"', '" "'):
            assert f"event.key === {key}" in body, key
        assert "close(true)" in body, "Escape gives the chip its focus back"
        assert 'document.addEventListener("pointerdown"' in body, "a press elsewhere closes it"
        assert "element.tabIndex = -1" in body, "roving focus: items are not tab stops"

    def test_it_is_built_on_the_page(self, hosted):
        assert "  accountMenu();\n" in hosted

    def test_items_are_thumb_sized_and_the_menu_stays_on_screen(self, css, hosted):
        item = css[css.index(".accountmenu__item {"):]
        item = item[:item.index("}")]
        assert re.search(r"min-height:\s*4[0-9]px", item)
        menu = css[css.index(".accountmenu__list {"):]
        menu = menu[:menu.index("}")]
        assert "right: 0" in menu and "max-width: calc(100vw - 16px)" in menu
        assert ".accountmenu__list[hidden] { display: none !important; }" in css
        assert "function place()" in hosted and "clientWidth - 8" in hosted

    def test_it_uses_the_pages_tokens_so_both_themes_follow(self, css):
        menu = css[css.index(".accountmenu__list {"):css.index(".accountmenu__separator")]
        assert "#" not in re.sub(r"/\*.*?\*/", "", menu, flags=re.S), "no fixed colours"
        for token in ("var(--surface)", "var(--text)", "var(--border)", "var(--surface-sunken)"):
            assert token in menu, token

    def test_the_label_hides_on_a_phone_by_its_own_class(self, css):
        assert ".accountchip__label { display: none; }" in css
        assert "span:last-child" not in css, "the caret is the last child now"


@pytest.fixture(scope="module")
def rule() -> str:
    """The snackbar's own rule in nav.css."""
    nav = (WEB.parent / "pages" / "nav.css").read_text(encoding="utf-8")
    body = nav[nav.index(".snackbar {"):]
    return body[:body.index("}")]


class TestTheToastUsesThePhonesWidth:
    """Owner's review, 2026-10-31: on a 360px phone the confirmation after
    scheduling wrapped a word to a line beside its action. A fixed box placed by
    `left: 50%` and pulled back by a transform shrinks to the half of the screen
    right of that edge, whatever its max-width says (nav.css, shared by every
    page). It is placed between two 16px gutters instead."""

    def test_it_sits_between_the_gutters_not_from_the_middle(self, rule):
        assert "left: 16px; right: 16px;" in rule
        assert "margin: 0 auto" in rule and "width: fit-content" in rule
        assert "left: 50%" not in rule and "translateX(-50%)" not in rule

    def test_the_action_drops_under_the_words_when_they_do_not_share_a_line(self, rule):
        assert "flex-wrap: wrap" in rule and "justify-content: flex-end" in rule
        nav = (WEB.parent / "pages" / "nav.css").read_text(encoding="utf-8")
        assert ".snackbar > span { flex: 1 1 auto; min-width: 0; }" in nav

    def test_its_action_is_a_40px_target_with_a_mouse_too(self):
        nav = (WEB.parent / "pages" / "nav.css").read_text(encoding="utf-8")
        action = nav[nav.index(".snackbar__action {"):]
        assert "min-height: 40px" in action[:action.index("}")]

    def test_the_entrance_no_longer_carries_the_old_centring(self):
        nav = (WEB.parent / "pages" / "nav.css").read_text(encoding="utf-8")
        frames = nav[nav.index("@keyframes snack-in"):]
        frames = frames[:frames.index("\n")]
        assert "-50%" not in frames
