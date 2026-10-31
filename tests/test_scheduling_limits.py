"""Per person limits and the scheduling pilot switch (docs/scheduling.md, FR-18, Table SC-10).

What these hold in place: the defaults (admins on, 90 pending and 1 GB; everyone
else off, 30 and 400 MB), an admin's override reaching the daily clip and upload
checks, only an admin reading or changing another person's figures (refused before
a body is read), the page being told the figures through `/api/state`, and a
switch that is off hiding nothing on the server.
"""

from __future__ import annotations

import pytest

from wastatus import accounts
from tests.test_portal import ADMIN, Browser, approved, env, site  # noqa: F401


def store(tmp_path, monkeypatch, admins=ADMIN):
    monkeypatch.setenv("WASTATUS_ADMIN_EMAILS", admins)
    return accounts.Accounts(tmp_path / "limits.db")


class TestDefaults:
    def test_everyone_else_starts_off_with_the_small_figures(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        got = db.person_limits("a@example.com")
        assert got["scheduling"] is False
        assert got["pending"] == 30 and got["budget_bytes"] == 400_000_000
        assert got["clips"] == 10 and got["upload_bytes"] == 500_000_000
        assert got["custom"] == {}

    def test_admins_start_on_with_the_large_ones(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        got = db.person_limits(ADMIN)
        assert got["scheduling"] is True
        assert got["pending"] == 90 and got["budget_bytes"] == 1_000_000_000
        assert got["clips"] == 10 and got["upload_bytes"] == 500_000_000

    def test_the_environment_still_sets_the_daily_defaults(self, env, tmp_path, monkeypatch):
        monkeypatch.setenv("WASTATUS_CLIPS_PER_DAY", "25")
        monkeypatch.setenv("WASTATUS_UPLOAD_MB_PER_DAY", "700")
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        got = db.person_limits("a@example.com")
        assert got["clips"] == 25 and got["upload_bytes"] == 700_000_000

    def test_someone_unknown_gets_the_ordinary_figures(self, env, tmp_path, monkeypatch):
        got = store(tmp_path, monkeypatch).person_limits("nobody@example.com")
        assert got["scheduling"] is False and got["pending"] == 30

    def test_an_older_database_gains_the_columns(self, env, tmp_path):
        import sqlite3
        path = tmp_path / "old.db"
        old = sqlite3.connect(path)
        old.execute("create table people (email text primary key, name text not null "
                    "default '', status text not null, role text not null default 'user', "
                    "answers text not null default '{}', google_sub text, created real "
                    "not null, decided real, last_seen real, gif_source text not null "
                    "default '', picture text not null default '')")
        old.execute("insert into people (email, status, created) values "
                    "('a@example.com', 'approved', 1)")
        old.commit()
        old.close()
        db = accounts.Accounts(path)
        assert db.person_limits("a@example.com")["pending"] == 30
        db.set_limits("a@example.com", {"pending": 12})
        assert db.person_limits("a@example.com")["pending"] == 12


class TestOverrides:
    def test_each_figure_can_be_set_and_put_back(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        got = db.set_limits("a@example.com", {
            "clips": 30, "upload_mb": 1500, "pending": 90, "budget_mb": 1000,
            "scheduling": True})
        assert got["clips"] == 30 and got["upload_bytes"] == 1_500_000_000
        assert got["pending"] == 90 and got["budget_bytes"] == 1_000_000_000
        assert got["scheduling"] is True
        assert got["custom"]["upload_mb"] == 1500
        back = db.set_limits("a@example.com", {"clips": None, "scheduling": "",
                                               "pending": None})
        assert back["clips"] == 10 and back["scheduling"] is False and back["pending"] == 30
        assert back["upload_bytes"] == 1_500_000_000   # left out, untouched

    def test_an_admin_can_be_switched_off(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        assert db.set_limits(ADMIN, {"scheduling": False})["scheduling"] is False

    def test_the_daily_clip_limit_follows_the_person(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        db.set_limits("a@example.com", {"clips": 2})
        db._count("a@example.com", "clips", 2)
        assert db.usage("a@example.com")["clips_limit"] == 2
        with pytest.raises(accounts.AccessError, match="today's 2 clips"):
            db.check_clip("a@example.com")
        # Somebody else is still on the default.
        db.add("b@example.com")
        db.check_clip("b@example.com")

    def test_the_daily_upload_limit_follows_the_person(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        db.set_limits("a@example.com", {"upload_mb": 10})
        db.reserve_upload("a@example.com", 9_000_000)
        with pytest.raises(accounts.AccessError, match="10 MB"):
            db.reserve_upload("a@example.com", 2_000_000)
        db.set_limits("a@example.com", {"upload_mb": 1500})
        assert db.reserve_upload("a@example.com", 2_000_000) < 0.01

    @pytest.mark.parametrize("changes", [
        {"clips": 0}, {"clips": 5000}, {"clips": "ten"}, {"clips": 1.5}, {"clips": True},
        {"upload_mb": 0}, {"pending": -1}, {"pending": 501}, {"budget_mb": 20001},
        {"scheduling": "yes"}, {"scheduling": 1}, {"colour": 3},
        {"pending": "²"}, {"pending": "٣"}, {"clips": "１０"}])
    def test_nonsense_is_refused_and_changes_nothing(self, env, tmp_path, monkeypatch, changes):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        with pytest.raises(accounts.AccessError):
            db.set_limits("a@example.com", {"pending": 40, **changes})
        assert db.person_limits("a@example.com")["pending"] == 30

    def test_a_person_who_is_not_here_is_refused(self, env, tmp_path, monkeypatch):
        with pytest.raises(accounts.AccessError, match="nobody"):
            store(tmp_path, monkeypatch).set_limits("nobody@example.com", {"pending": 4})

    def test_deleting_a_person_takes_their_figures(self, env, tmp_path, monkeypatch):
        db = store(tmp_path, monkeypatch)
        db.add("a@example.com")
        db.set_limits("a@example.com", {"pending": 77})
        db.forget("a@example.com")
        db.add("a@example.com")
        assert db.person_limits("a@example.com")["pending"] == 30


class TestOverTheWire:
    def test_a_person_is_told_their_own_figures(self, site):
        person = approved(site, "a@example.com")
        _, state = person.api("GET", "/api/state")
        assert state["scheduling"] == {"enabled": False, "pending": 30,
                                       "budget_bytes": 400_000_000}
        admin = Browser(site)
        admin.sign_in(ADMIN)
        _, state = admin.api("GET", "/api/state")
        assert state["scheduling"] == {"enabled": True, "pending": 90,
                                       "budget_bytes": 1_000_000_000}

    def test_the_admin_turns_it_on_and_the_page_follows(self, site):
        person = approved(site, "a@example.com")
        admin = Browser(site)
        admin.sign_in(ADMIN)
        status, answer = admin.api("POST", "/api/admin/limits", {
            "email": "a@example.com",
            "changes": {"scheduling": True, "pending": 45, "budget_mb": 600, "clips": 20}})
        assert status == 200 and answer["limits"]["scheduling"] is True
        _, state = person.api("GET", "/api/state")
        assert state["scheduling"] == {"enabled": True, "pending": 45,
                                       "budget_bytes": 600_000_000}
        assert state["quota"]["clips_limit"] == 20

    def test_the_overview_carries_each_persons_figures(self, site):
        approved(site, "a@example.com")
        admin = Browser(site)
        admin.sign_in(ADMIN)
        admin.api("POST", "/api/admin/limits", {"email": "a@example.com",
                                                "changes": {"pending": 12}})
        _, overview = admin.api("GET", "/api/admin")
        by = {p["email"]: p["limits"] for p in overview["people"]}
        assert by["a@example.com"]["pending"] == 12
        assert by["a@example.com"]["custom"] == {"pending": 12}
        assert by[ADMIN]["scheduling"] is True

    def test_nobody_but_an_admin_changes_anyones_figures(self, site):
        person = approved(site, "a@example.com")
        approved(site, "b@example.com")
        status, _ = person.api("POST", "/api/admin/limits", {
            "email": "b@example.com", "changes": {"scheduling": True}})
        assert status == 403
        status, _ = person.api("POST", "/api/admin/limits", {
            "email": "a@example.com", "changes": {"scheduling": True}})
        assert status == 403, "not even their own"
        assert site.accounts.person_limits("a@example.com")["scheduling"] is False

    def test_a_refusal_comes_before_the_body_is_read(self, site):
        person = approved(site, "a@example.com")
        # A body far over the cap: a read would be refused with 413 or hang.
        status, _ = person.api("POST", "/api/admin/limits", b"x" * 100_000)
        assert status == 403

    def test_signed_out_is_refused_too(self, site):
        status, _ = Browser(site).open_call("/api/admin/limits", {"email": "a@example.com"})
        assert status in (401, 403)

    def test_the_admin_gets_a_reason_for_nonsense(self, site):
        approved(site, "a@example.com")
        admin = Browser(site)
        admin.sign_in(ADMIN)
        status, answer = admin.api("POST", "/api/admin/limits", {
            "email": "a@example.com", "changes": {"pending": 9000}})
        assert status == 400 and "between 0 and 500" in answer["error"]
        status, answer = admin.api("POST", "/api/admin/limits", {
            "email": "a@example.com", "changes": "lots"})
        assert status == 400

    def test_a_switch_that_is_off_hides_nothing_on_the_server(self, site):
        # The pilot switch is the page's: the quota, the clip list and the grant for
        # a clip all behave as before for someone with scheduling off.
        person = approved(site, "a@example.com")
        _, state = person.api("GET", "/api/state")
        assert state["scheduling"]["enabled"] is False
        assert state["quota"]["clips_limit"] == 10 and "clips" in state
        status, _ = person.api("POST", "/api/grant", {"purpose": "clip", "stem": "x"})
        assert status != 403

    def test_a_schedule_failure_can_be_reported(self, site):
        person = approved(site, "a@example.com")
        status, _ = person.api("POST", "/api/report", {
            "source": "schedule", "phase": "schedule", "code": "invalid", "versions": "ext 2.1.0"})
        assert status == 200
        assert site.accounts.reports(0, "schedule")[0]["code"] == "invalid"

    def test_a_superscript_digit_is_a_400_not_a_500(self, site):
        approved(site, "a@example.com")
        admin = Browser(site)
        admin.sign_in(ADMIN)
        status, answer = admin.api("POST", "/api/admin/limits", {
            "email": "a@example.com", "changes": {"pending": "\u00b2"}})
        assert status == 400 and "whole number" in answer["error"]
