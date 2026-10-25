"""GIF search: the seam, the switch, and what is never trusted.

Nothing here reaches a provider. Two things are worth pinning: that the feature is
off unless it is deliberately and completely on, and that two providers with
completely different JSON come out as one shape.
"""

from __future__ import annotations

import json

import pytest

from wastatus import gifs


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("WASTATUS_GIF_PROVIDER", "WASTATUS_GIF_RATING",
                 "WASTATUS_GIPHY_KEY", "WASTATUS_KLIPY_KEY"):
        monkeypatch.delenv(name, raising=False)


class TestTheSwitch:
    """Off is the default, and a half finished setup is also off.

    The point of failing closed is that the page asks `state` whether to draw the
    toggle at all. A provider with no key behind it would draw a search box that
    answers nothing but errors.
    """

    def test_off_by_default(self):
        assert gifs.provider() == ""
        assert gifs.enabled() is False
        assert gifs.credit() == {}

    def test_a_provider_with_no_key_is_still_off(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        assert gifs.enabled() is False, "a keyless provider must not look configured"

    def test_a_key_with_no_provider_is_still_off(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        assert gifs.enabled() is False

    def test_both_together_turn_it_on(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        assert gifs.provider() == "giphy"
        assert gifs.credit()["placeholder"] == "Search GIPHY"

    @pytest.mark.parametrize("value", ["", "off", "none", "  ", "tenor", "nonsense"])
    def test_anything_unusable_is_off_rather_than_an_error(self, value, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", value)
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        assert gifs.enabled() is False

    def test_klipy_carries_its_own_required_placeholder(self, monkeypatch):
        """KLIPY's one mandatory term is the words in the search box."""
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "klipy")
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        assert gifs.credit()["placeholder"] == "Search KLIPY"

    def test_searching_while_off_says_so_rather_than_crashing(self):
        with pytest.raises(gifs.GifError, match="switched off"):
            gifs.search("flower")


class TestTheRating:
    def test_the_default_is_pg_not_g(self):
        """`g` strips out ordinary celebration and reaction GIFs."""
        assert gifs.rating() == "pg"

    @pytest.mark.parametrize("value", ["g", "pg", "pg-13", "r", "PG", " pg-13 "])
    def test_every_real_value_is_taken(self, value, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_RATING", value)
        assert gifs.rating() == value.strip().lower()

    def test_a_typo_falls_back_rather_than_becoming_off(self, monkeypatch):
        """A setting that quietly means the opposite of its name is the worst kind."""
        monkeypatch.setenv("WASTATUS_GIF_RATING", "off")
        assert gifs.rating() == "pg"


class TestTwoProvidersOneShape:
    """The page and the server only ever see `Gif`, whoever answered."""

    GIPHY = {"data": [{
        "id": "abc123", "title": "Thanks GIF",
        "images": {
            "fixed_width_small": {"url": "https://media.giphy.com/s.gif",
                                  "width": "100", "height": "56", "size": "9000"},
            "downsized": {"url": "https://media.giphy.com/d.gif",
                          "width": "480", "height": "270", "size": "410000"},
        },
    }]}

    KLIPY = {"result": True, "data": {"data": [{
        "slug": "cute-cat", "title": "Cute Cat", "type": "gif",
        "file": {
            "xs": {"gif": {"url": "https://cdn.klipy.co/xs.gif",
                           "width": 90, "height": 90, "size": 12000}},
            "md": {"gif": {"url": "https://cdn.klipy.co/md.gif",
                           "width": 640, "height": 640, "size": 197000}},
        },
    }]}}

    def _search(self, monkeypatch, name, key_env, payload):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", name)
        monkeypatch.setenv(key_env, "k")
        monkeypatch.setattr(gifs, "_get", lambda url, timeout=0: payload)
        return gifs.search("thanks")

    def test_giphy_comes_out_in_the_common_shape(self, monkeypatch):
        found = self._search(monkeypatch, "giphy", "WASTATUS_GIPHY_KEY", self.GIPHY)
        assert len(found) == 1
        one = found[0]
        assert one.id == "abc123" and one.title == "Thanks GIF"
        assert one.preview.endswith("s.gif"), "the shelf must get the small one"
        assert one.full.endswith("d.gif"), "and placing must get the large one"
        assert (one.width, one.height, one.bytes) == (480, 270, 410000)

    def test_klipy_comes_out_in_the_same_shape(self, monkeypatch):
        found = self._search(monkeypatch, "klipy", "WASTATUS_KLIPY_KEY", self.KLIPY)
        assert len(found) == 1
        one = found[0]
        assert one.id == "cute-cat" and one.title == "Cute Cat"
        assert one.preview.endswith("xs.gif") and one.full.endswith("md.gif")
        assert (one.width, one.height, one.bytes) == (640, 640, 197000)

    def test_a_result_missing_its_pictures_is_dropped_not_half_shown(self, monkeypatch):
        found = self._search(monkeypatch, "giphy", "WASTATUS_GIPHY_KEY",
                             {"data": [{"id": "x", "images": {}}]})
        assert found == []

    def test_an_empty_query_asks_nobody_anything(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")

        def refuse(*_a, **_k):
            pytest.fail("an empty search box must not reach the provider")

        monkeypatch.setattr(gifs, "_get", refuse)
        assert gifs.search("   ") == []


class TestFetchingIsGuarded:
    """`fetch` is the only place this tool downloads from a stranger."""

    def test_only_https_is_ever_fetched(self):
        for url in ("http://example.com/a.gif", "file:///etc/passwd",
                    "ftp://example.com/a.gif", ""):
            with pytest.raises(gifs.GifError, match="not an address"):
                gifs.fetch(url, ceiling=1000)

    def test_a_declared_size_over_the_ceiling_is_refused_before_reading(
            self, monkeypatch):
        class Response:
            headers = {"Content-Length": "9000000"}

            def read(self, _n=None):
                pytest.fail("the body was read despite the header saying it was huge")

            def __enter__(self): return self
            def __exit__(self, *_e): return None

        monkeypatch.setattr(gifs._media_opener, "open", lambda *_a, **_k: Response())
        with pytest.raises(gifs.GifError, match="over the"):
            gifs.fetch("https://media1.giphy.com/a.gif", ceiling=8_000_000)

    def test_a_lying_header_does_not_get_past_the_ceiling(self, monkeypatch):
        """The provider's byte count is usually right and is not a promise."""
        class Response:
            headers = {}

            def read(self, n=None):
                return b"x" * n

            def __enter__(self): return self
            def __exit__(self, *_e): return None

        monkeypatch.setattr(gifs._media_opener, "open", lambda *_a, **_k: Response())
        with pytest.raises(gifs.GifError, match="over the"):
            gifs.fetch("https://static.klipy.com/a.gif", ceiling=100)

    @pytest.mark.parametrize("url", [
        "https://example.com/a.gif", "http://media1.giphy.com/a.gif",
        "https://giphy.com.example.net/a.gif", "https://127.0.0.1/a.gif",
    ])
    def test_only_the_providers_media_hosts_are_fetched(self, url):
        """D-101: an address in a provider's answer cannot point the server anywhere."""
        with pytest.raises(gifs.GifError, match="not an address"):
            gifs.fetch(url, ceiling=100)

    def test_a_redirect_off_the_media_hosts_is_not_followed(self):
        handler = gifs._MediaRedirects()
        with pytest.raises(gifs.GifError, match="led somewhere"):
            handler.redirect_request(None, None, 302, "Found", {}, "http://169.254.169.254/")


class TestErrorsAreSafeToShow:
    @pytest.mark.parametrize("code,expect", [
        (401, "refused"), (403, "refused"), (429, "rate limiting"), (500, "answered 500"),
    ])
    def test_an_http_failure_becomes_a_sentence(self, code, expect, monkeypatch):
        import urllib.error

        def raise_it(*_a, **_k):
            raise urllib.error.HTTPError("u", code, "no", {}, None)

        monkeypatch.setattr(gifs.urllib.request, "urlopen", raise_it)
        with pytest.raises(gifs.GifError, match=expect):
            gifs._get("https://api.example/x")

    def test_rubbish_json_is_not_a_traceback(self, monkeypatch):
        class Response:
            def read(self): return b"<html>down for maintenance</html>"
            def __enter__(self): return self
            def __exit__(self, *_e): return None

        monkeypatch.setattr(gifs.urllib.request, "urlopen",
                            lambda *_a, **_k: Response())
        with pytest.raises(gifs.GifError, match="not JSON"):
            gifs._get("https://api.example/x")


class TestChoosingAProvider:
    """The chooser in the page, T-034. A key is what makes a provider an option."""

    def test_only_providers_with_a_key_are_offered(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        assert [one["name"] for one in gifs.available()] == ["giphy"]
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        # Two keys, and searching both at once becomes a choice too.
        assert [one["name"] for one in gifs.available()] == ["giphy", "klipy", "both"]

    def test_nothing_configured_offers_nothing(self):
        assert gifs.available() == []

    def test_choosing_switches_the_provider_for_this_process(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        assert gifs.provider() == "giphy"
        assert gifs.choose("klipy") == "klipy"
        assert gifs.provider() == "klipy"
        assert gifs.credit()["placeholder"] == "Search KLIPY"

    def test_a_provider_without_a_key_is_refused(self, monkeypatch):
        """Choosing it would switch the feature off and say nothing about why."""
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        with pytest.raises(gifs.GifError):
            gifs.choose("klipy")
        assert gifs.provider() == "giphy"

    @pytest.mark.parametrize("name", ["", "tenor", "GIPHY; rm -rf", "../giphy"])
    def test_anything_else_is_refused(self, name, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        with pytest.raises(gifs.GifError):
            gifs.choose(name)

    def test_a_name_is_matched_case_insensitively_and_trimmed(self, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        assert gifs.choose("  KLIPY ") == "klipy"

    def test_the_credit_carries_what_else_could_be_chosen(self, monkeypatch):
        """The page draws no chooser for one option, so it has to be told."""
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        assert len(gifs.credit()["choices"]) == 1
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        # Two keys are three choices: either one, or both mixed together.
        assert [one["name"] for one in gifs.credit()["choices"]] == ["giphy", "klipy", "both"]

    def test_choosing_never_writes_the_env_file(self, monkeypatch, tmp_path):
        """`.env` holds the API keys. Nothing reachable from a request rewrites it."""
        env_file = tmp_path / ".env"
        env_file.write_text("WASTATUS_GIF_PROVIDER=giphy\n", encoding="utf-8")
        monkeypatch.setenv("WASTATUS_ENV", str(env_file))
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")
        before = env_file.read_text(encoding="utf-8")
        gifs.choose("klipy")
        assert env_file.read_text(encoding="utf-8") == before
