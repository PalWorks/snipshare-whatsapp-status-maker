"""People, sessions and limits for the hosted page: who may use it, and how much.

One SQLite file in the renderer's data directory. Small and boring on purpose: a
handful of people, a few rows a day each, read and written by one process. Every
secret that passes through here (a session, a grant, a person's GIF key) is either
stored as a hash or encrypted, never as itself. See docs/hosted-page.md and
DECISIONS.md D-089.

The admin list comes from the environment, `WASTATUS_ADMIN_EMAILS`, so who runs a
copy of this is never written into the code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("wastatus")

ADMINS_ENV = "WASTATUS_ADMIN_EMAILS"
SECRET_ENV = "WASTATUS_SECRET_KEY"
CLIPS_PER_DAY_ENV = "WASTATUS_CLIPS_PER_DAY"
UPLOAD_MB_PER_DAY_ENV = "WASTATUS_UPLOAD_MB_PER_DAY"

SESSION_DAYS = 30
HISTORY_DAYS = 90
USAGE_DAYS = 400   # daily counts: a year and a little, for the admin's ranges
GRANT_SECONDS = 15 * 60
GRANT_LIFETIME = 2 * 3600   # however busy, a grant ends two hours after it was made
DEFAULT_CLIPS_PER_DAY = 10
DEFAULT_UPLOAD_MB_PER_DAY = 500

PENDING, APPROVED, DECLINED, SUSPENDED = "pending", "approved", "declined", "suspended"
STATUSES = (PENDING, APPROVED, DECLINED, SUSPENDED)
USER, ADMIN = "user", "admin"

# What a person can be asked for. Kept short: every field is something to look
# after, and the owner only needs enough to decide.
ANSWER_LIMITS = {"name": 120, "use": 600, "heard": 200}
GIF_PROVIDERS = ("giphy", "klipy")

SCHEMA = """
create table if not exists people (
  email text primary key,
  name text not null default '',
  status text not null,
  role text not null default 'user',
  answers text not null default '{}',
  google_sub text,
  created real not null,
  decided real,
  last_seen real,
  gif_source text not null default '',
  picture text not null default ''
);
create table if not exists sessions (
  hash text primary key,
  email text not null,
  created real not null,
  expires real not null,
  last_seen real not null,
  agent text not null default ''
);
create table if not exists grants (
  hash text primary key,
  email text not null,
  purpose text not null,
  scope text not null default '',
  expires real not null,
  created real not null default 0
);
create table if not exists usage (
  email text not null,
  day text not null,
  clips integer not null default 0,
  failures integer not null default 0,
  upload_bytes integer not null default 0,
  render_seconds real not null default 0,
  primary key (email, day)
);
create table if not exists gif_keys (
  email text not null,
  provider text not null,
  secret blob not null,
  created real not null,
  primary key (email, provider)
);
create table if not exists history (
  id integer primary key autoincrement,
  email text not null,
  at real not null,
  video_id text not null default '',
  title text not null default '',
  channel text not null default '',
  mode text not null default '',
  start real not null default 0,
  end real not null default 0,
  stem text not null default '',
  ok integer not null default 0,
  seconds real not null default 0,
  error text not null default ''
);
create index if not exists history_by_person on history (email, at);
create table if not exists reports (
  id integer primary key autoincrement,
  at real not null,
  email text not null default '',
  source text not null,
  phase text not null default '',
  code text not null default '',
  detail text not null default '',
  versions text not null default ''
);
create table if not exists alerts (
  key text primary key,
  last real not null,
  count integer not null default 0
);
"""


class AccessError(Exception):
    """A request that is understood and refused. The message is for the person."""


def normal_email(raw: Any) -> str:
    email = str(raw or "").strip().lower()
    if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise AccessError("that is not an email address")
    local, _, domain = email.rpartition("@")
    if not local or "." not in domain or any(c.isspace() for c in email):
        raise AccessError("that is not an email address")
    return email


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def person_id(email: str) -> str:
    """A stable, opaque name for a person, for folders and logs. Not reversible
    without guessing the email, which is enough for a file name in a backup."""
    return hashlib.sha256(("wastatus:" + email).encode()).hexdigest()[:24]


def today(now: float | None = None) -> str:
    return datetime.fromtimestamp(now or time.time(), timezone.utc).strftime("%Y-%m-%d")


def admins() -> set[str]:
    raw = os.environ.get(ADMINS_ENV) or ""
    found = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            try:
                found.add(normal_email(part))
            except AccessError:
                log.warning("%s has an entry that is not an email address", ADMINS_ENV)
    return found


def limits() -> tuple[int, int]:
    """Clips and upload bytes a person may use in a day."""
    def number(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name) or default))
        except ValueError:
            log.warning("%s is not a number; using %d", name, default)
            return default
    return (number(CLIPS_PER_DAY_ENV, DEFAULT_CLIPS_PER_DAY),
            number(UPLOAD_MB_PER_DAY_ENV, DEFAULT_UPLOAD_MB_PER_DAY) * 1_000_000)


@dataclass(frozen=True)
class Person:
    email: str
    name: str
    status: str
    role: str
    answers: dict[str, Any]
    created: float
    decided: float | None
    last_seen: float | None

    @property
    def id(self) -> str:
        return person_id(self.email)

    @property
    def admin(self) -> bool:
        return self.role == ADMIN

    def as_json(self) -> dict[str, Any]:
        return {"email": self.email, "name": self.name, "status": self.status,
                "role": self.role, "answers": self.answers, "created": self.created,
                "decided": self.decided, "last_seen": self.last_seen}


class Accounts:
    """The store. One connection per thread, because SQLite connections are not
    to be shared between threads, and a write lock so two requests never race on
    a counter."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write = threading.Lock()
        with self._write:
            db = self._db()
            self._migrate(db)
            db.executescript(SCHEMA)
            db.commit()
        os.chmod(path, 0o600)
        self.ensure_admins()

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        """Bring a database from an earlier version up to this one, in place.

        2026-10-25: `gif_keys` held one key per person, keyed by email alone; it is
        keyed by person and provider now, so GIPHY and KLIPY can both be kept. And
        `people` gained the person's choice of which to search."""
        tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}
        if "gif_keys" in tables:
            keyed = [row[1] for row in db.execute("pragma table_info(gif_keys)") if row[5]]
            if keyed == ["email"]:
                # One transaction: a process stopped half way leaves the old table as
                # it was, and the next start migrates it again.
                db.executescript("""
                    begin immediate;
                    alter table gif_keys rename to gif_keys_old;
                    create table gif_keys (email text not null, provider text not null,
                      secret blob not null, created real not null,
                      primary key (email, provider));
                    insert into gif_keys select email, provider, secret, created from gif_keys_old;
                    drop table gif_keys_old;
                    commit;
                """)
        if "people" in tables:
            columns = {row[1] for row in db.execute("pragma table_info(people)")}
            if "gif_source" not in columns:
                db.execute("alter table people add column gif_source text not null default ''")
            if "picture" not in columns:
                db.execute("alter table people add column picture text not null default ''")
        if "sessions" in tables:
            columns = {row[1] for row in db.execute("pragma table_info(sessions)")}
            if "agent" not in columns:
                db.execute("alter table sessions add column agent text not null default ''")
        if "grants" in tables:
            columns = {row[1] for row in db.execute("pragma table_info(grants)")}
            if "created" not in columns:
                # Grants live minutes, so the ones made before this column existed
                # count as made now; nothing older than a quarter of an hour survives.
                db.execute("alter table grants add column created real not null default 0")
                db.execute("update grants set created = ?", (time.time(),))

    def _db(self) -> sqlite3.Connection:
        db = getattr(self._local, "db", None)
        if db is None:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("pragma journal_mode=wal")
            db.execute("pragma foreign_keys=on")
            self._local.db = db
        return db

    def _do(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._write:
            db = self._db()
            cur = db.execute(sql, args)
            db.commit()
            return cur

    def _one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self._db().execute(sql, args).fetchone()

    def _all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self._db().execute(sql, args).fetchall()

    # -- people ------------------------------------------------------------

    def ensure_admins(self) -> None:
        """Everyone in the admin list is approved, as an admin, from the start, and
        anyone taken off the list stops being one: the list is the only authority."""
        now = time.time()
        listed = admins()
        if not listed:
            # Run somewhere the list is not set (a shell outside the container):
            # that is not the list saying "nobody", so nobody is demoted.
            return
        for email in listed:
            self._do(
                "insert into people (email, status, role, created, decided) values (?,?,?,?,?) "
                "on conflict(email) do update set status=?, role=?",
                (email, APPROVED, ADMIN, now, now, APPROVED, ADMIN))
        for row in self._all("select email from people where role = ?", (ADMIN,)):
            if row["email"] not in listed:
                self._do("update people set role = ? where email = ?", (USER, row["email"]))

    def person(self, email: str) -> Person | None:
        row = self._one("select * from people where email = ?", (email,))
        if row is None:
            return None
        try:
            answers = json.loads(row["answers"] or "{}")
        except json.JSONDecodeError:
            answers = {}
        return Person(email=row["email"], name=row["name"], status=row["status"],
                      role=row["role"], answers=answers, created=row["created"],
                      decided=row["decided"], last_seen=row["last_seen"])

    def by_id(self, pid: str) -> Person | None:
        """The person behind a `person_id`. A scan, which for a handful of people is
        cheaper than keeping a second index in step."""
        for row in self._all("select email from people"):
            if person_id(row["email"]) == pid:
                return self.person(row["email"])
        return None

    def people(self, status: str | None = None) -> list[Person]:
        rows = self._all("select email from people" + (" where status = ?" if status else "")
                         + " order by created desc", (status,) if status else ())
        return [p for p in (self.person(r["email"]) for r in rows) if p]

    def request_access(self, email: str, answers: dict[str, Any],
                       google_sub: str | None = None) -> tuple[Person, bool]:
        """Record a request. Returns the person and whether this was a new request,
        so a second submit from the same address notifies nobody twice."""
        email = normal_email(email)
        clean = {}
        for key, limit in ANSWER_LIMITS.items():
            value = " ".join(str(answers.get(key) or "").split())
            if len(value) > limit:
                raise AccessError(f"{key} is too long")
            clean[key] = value
        if not clean["name"]:
            raise AccessError("please say your name")
        # One statement decides whether this is new, so two submits arriving at once
        # cannot both insert: the second is simply not new.
        cur = self._do("insert into people (email, name, status, answers, google_sub, created) "
                       "values (?,?,?,?,?,?) on conflict(email) do nothing",
                       (email, clean["name"], PENDING, json.dumps(clean), google_sub,
                        time.time()))
        return self.person(email), cur.rowcount == 1  # type: ignore[return-value]

    def decide(self, email: str, status: str) -> Person:
        if status not in STATUSES or status == PENDING:
            raise AccessError("that is not a decision")
        email = normal_email(email)
        person = self.person(email)
        if person is None:
            raise AccessError("nobody has asked with that address")
        if person.admin and status != APPROVED:
            raise AccessError("an admin cannot be refused here; remove them from "
                              f"{ADMINS_ENV} first")
        self._do("update people set status = ?, decided = ? where email = ?",
                 (status, time.time(), email))
        if status in (DECLINED, SUSPENDED):
            self.end_sessions(email)
        return self.person(email)  # type: ignore[return-value]

    def add(self, email: str, name: str = "") -> Person:
        """Approve someone directly, without a request: the owner's shortcut."""
        email = normal_email(email)
        if self.person(email) is None:
            self._do("insert into people (email, name, status, created, decided) "
                     "values (?,?,?,?,?)", (email, name, APPROVED, time.time(), time.time()))
            return self.person(email)  # type: ignore[return-value]
        return self.decide(email, APPROVED)

    def forget(self, email: str) -> None:
        """Delete everything about a person: what they asked for, their sessions,
        grants, usage, GIF keys and history. Their reports are kept with the email
        blanked, so the failure counts stay honest. Their clips are the caller's to
        delete."""
        email = normal_email(email)
        person = self.person(email)
        if person and person.admin:
            raise AccessError("an admin cannot be deleted here")
        for table in ("sessions", "grants", "usage", "gif_keys", "history"):
            self._do(f"delete from {table} where email = ?", (email,))  # noqa: S608 - fixed names
        self._do("update reports set email = '' where email = ?", (email,))
        self._do("delete from people where email = ?", (email,))

    # -- sessions ----------------------------------------------------------

    def start_session(self, email: str, agent: str = "") -> str:
        """A new session. `agent` is a coarse description of the browser, such as
        "Chrome on Linux", so a person can recognise their sessions."""
        person = self.person(email)
        if person is None or person.status != APPROVED:
            raise AccessError("not approved")
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._do("delete from sessions where expires < ?", (now,))
        self._do("insert into sessions (hash, email, created, expires, last_seen, agent) "
                 "values (?,?,?,?,?,?)",
                 (_hash(token), email, now, now + SESSION_DAYS * 86400, now, agent[:60]))
        self._do("update people set last_seen = ? where email = ?", (now, email))
        return token

    def session(self, token: str | None) -> Person | None:
        """The approved person behind a session cookie, or None."""
        if not token or len(token) > 200:
            return None
        row = self._one("select email, expires, last_seen from sessions where hash = ?",
                        (_hash(token),))
        now = time.time()
        if row is None or row["expires"] < now:
            return None
        person = self.person(row["email"])
        if person is None or person.status != APPROVED:
            return None
        if now - row["last_seen"] > 300:  # write at most every five minutes
            self._do("update sessions set last_seen = ? where hash = ?", (now, _hash(token)))
            self._do("update people set last_seen = ? where email = ?", (now, person.email))
        return person

    def end_session(self, token: str | None) -> None:
        """Sign one browser out. When it was the person's last session, the grants
        it handed the extension end with it, rather than living on for minutes."""
        if not token:
            return
        row = self._one("select email from sessions where hash = ?", (_hash(token),))
        self._do("delete from sessions where hash = ?", (_hash(token),))
        if row is not None and self._one("select 1 from sessions where email = ?",
                                         (row["email"],)) is None:
            self._do("delete from grants where email = ?", (row["email"],))

    def sessions_of(self, email: str, current: str | None = None) -> list[dict[str, Any]]:
        """A person's sessions, newest use first, each named by a short id that is
        not the session's hash. The one `current` names is marked."""
        mine = _hash(current) if current else ""
        rows = self._all("select hash, created, last_seen, agent from sessions "
                         "where email = ? and expires >= ? order by last_seen desc",
                         (email, time.time()))
        return [{"id": _hash("id:" + r["hash"])[:16], "created": r["created"],
                 "last_seen": r["last_seen"], "agent": r["agent"] or "A browser",
                 "current": r["hash"] == mine} for r in rows]

    def end_session_named(self, email: str, ident: str) -> bool:
        for row in self._all("select hash from sessions where email = ?", (email,)):
            if _hash("id:" + row["hash"])[:16] == ident:
                self._do("delete from sessions where hash = ?", (row["hash"],))
                return True
        return False

    def end_other_sessions(self, email: str, keep: str) -> int:
        count = self._do("delete from sessions where email = ? and hash != ?",
                         (email, _hash(keep))).rowcount
        return count

    def set_picture(self, email: str, url: str) -> None:
        # Google's own photo address, or nothing: it is put into pages as an image
        # source, and only an https address on Google's photo host belongs there.
        parts = urllib.parse.urlsplit(url or "")
        if parts.scheme != "https" or not (parts.hostname or "").endswith(".googleusercontent.com"):
            url = ""
        self._do("update people set picture = ? where email = ?", (url[:500], email))

    def google_sub(self, email: str) -> str:
        row = self._one("select google_sub from people where email = ?", (email,))
        return (row["google_sub"] if row else "") or ""

    def bind_google(self, email: str, sub: str) -> None:
        """Remember which Google account an address first signed in with."""
        self._do("update people set google_sub = ? where email = ? and "
                 "(google_sub is null or google_sub = '')", (sub, email))

    def picture(self, email: str) -> str:
        row = self._one("select picture from people where email = ?", (email,))
        return (row["picture"] if row else "") or ""

    # -- the admin's view of a stretch of days ------------------------------

    def range_summary(self, first: str, last: str) -> dict[str, Any]:
        """Usage between two UTC days, inclusive, by person and in all."""
        rows = [dict(r) for r in self._all(
            "select email, sum(clips) as clips, sum(failures) as failures, "
            "sum(upload_bytes) as upload_bytes, sum(render_seconds) as render_seconds "
            "from usage where day >= ? and day <= ? group by email order by clips desc",
            (first, last))]
        start = datetime.strptime(first, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        end = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() + 86400
        new = self._one("select count(*) as n from people where created >= ? and created < ?",
                        (start, end))["n"]
        reports = [dict(r) for r in self._all(
            "select * from reports where at >= ? and at < ? order by at desc limit 500",
            (start, end))]
        return {
            "by_person": rows, "reports": reports, "new_requests": new,
            "totals": {
                "clips": sum(r["clips"] or 0 for r in rows),
                "failures": sum(r["failures"] or 0 for r in rows),
                "upload_bytes": sum(r["upload_bytes"] or 0 for r in rows),
                "render_seconds": round(sum(r["render_seconds"] or 0 for r in rows), 1),
                "people": sum(1 for r in rows if (r["clips"] or 0) + (r["failures"] or 0)),
            },
        }

    def end_sessions(self, email: str) -> None:
        self._do("delete from sessions where email = ?", (email,))
        self._do("delete from grants where email = ?", (email,))

    # -- grants ------------------------------------------------------------

    def grant(self, email: str, purpose: str, scope: str = "",
              seconds: int = GRANT_SECONDS) -> str:
        """A short lived, single purpose bearer token for the extension."""
        if purpose not in ("upload", "clip"):
            raise AccessError("unknown purpose")
        token = secrets.token_urlsafe(32)
        self._do("insert into grants (hash, email, purpose, scope, expires, created) "
                 "values (?,?,?,?,?,?)",
                 (_hash(token), email, purpose, scope, time.time() + seconds, time.time()))
        self._do("delete from grants where expires < ?", (time.time() - 3600,))
        return token

    def check_grant(self, token: str | None, purpose: str,
                    scope: str | None = None, renew: bool = False) -> Person | None:
        """The approved person a grant stands for, or None.

        `renew` slides its expiry forward on use, so an upload that keeps sending, or
        a clip's fetch resuming piece by piece, is never cut off by the clock on a
        slow line, and one that stops expires as usual. Both ask for it."""
        if not token or len(token) > 200:
            return None
        row = self._one("select email, purpose, scope, expires, created from grants "
                        "where hash = ?", (_hash(token),))
        now = time.time()
        if row is None or row["expires"] < now or row["purpose"] != purpose:
            return None
        if scope is not None and row["scope"] != scope:
            return None
        person = self.person(row["email"])
        if person is None or person.status != APPROVED:
            return None
        if renew and row["expires"] - now < GRANT_SECONDS - 60:
            # Slid forward while in use, but never past GRANT_LIFETIME from when it
            # was made: a grant that leaked and is kept busy still ends (D-101).
            limit = (row["created"] or now) + GRANT_LIFETIME
            self._do("update grants set expires = ? where hash = ?",
                     (min(now + GRANT_SECONDS, limit), _hash(token)))
        return person

    # -- limits ------------------------------------------------------------

    def usage(self, email: str, day: str | None = None) -> dict[str, Any]:
        row = self._one("select * from usage where email = ? and day = ?",
                        (email, day or today()))
        clips, upload_bytes = limits()
        used = dict(row) if row else {"clips": 0, "failures": 0, "upload_bytes": 0,
                                       "render_seconds": 0.0}
        return {"clips": used["clips"], "failures": used["failures"],
                "upload_bytes": used["upload_bytes"],
                "render_seconds": round(used["render_seconds"], 1),
                "clips_limit": clips, "upload_limit": upload_bytes}

    def _count(self, email: str, column: str, amount: float) -> None:
        self._do(f"insert into usage (email, day, {column}) values (?,?,?) "  # noqa: S608
                 f"on conflict(email, day) do update set {column} = {column} + ?",
                 (email, today(), amount, amount))

    def refund_upload(self, email: str, size: int, day: str | None = None) -> None:
        """Give back bytes reserved for an upload that never arrived."""
        if size > 0:
            self._do("update usage set upload_bytes = max(0, upload_bytes - ?) "
                     "where email = ? and day = ?", (size, email, day or today()))

    def reserve_upload(self, email: str, size: int) -> float:
        """Count an upload's bytes against today, or refuse it. Returns the share of
        the day's allowance now used, for the caller to warn on.

        The check and the count are one transaction under the write lock: two
        uploads arriving together must not both fit into the same last few MB."""
        _, limit = limits()
        day = today()
        with self._write:
            db = self._db()
            row = db.execute("select upload_bytes from usage where email = ? and day = ?",
                             (email, day)).fetchone()
            used = row["upload_bytes"] if row else 0
            if used + size > limit:
                raise AccessError(
                    f"that would pass today's limit of {limit // 1_000_000} MB of video "
                    "sent. It resets at midnight UTC")
            db.execute("insert into usage (email, day, upload_bytes) values (?,?,?) "
                       "on conflict(email, day) do update set upload_bytes = upload_bytes + ?",
                       (email, day, size, size))
            db.commit()
        return (used + size) / limit

    def check_clip(self, email: str) -> None:
        used = self.usage(email)
        if used["clips"] >= used["clips_limit"]:
            raise AccessError(
                f"you have made today's {used['clips_limit']} clips. "
                "It resets at midnight UTC")

    def count_clip(self, email: str, seconds: float, ok: bool) -> None:
        self._count(email, "clips" if ok else "failures", 1)
        self._count(email, "render_seconds", seconds)

    def usage_table(self, day: str | None = None) -> list[dict[str, Any]]:
        rows = self._all("select * from usage where day = ? order by clips desc",
                         (day or today(),))
        return [dict(r) for r in rows]

    # -- GIF keys ----------------------------------------------------------

    def set_gif_key(self, email: str, provider: str, key: str) -> None:
        if provider not in GIF_PROVIDERS:
            raise AccessError("that is not a GIF service this page knows")
        key = key.strip()
        if not key or len(key) > 200:
            raise AccessError("that is not a key")
        sealed = _seal(key)
        self._do("insert into gif_keys (email, provider, secret, created) values (?,?,?,?) "
                 "on conflict(email, provider) do update set secret=?, created=?",
                 (email, provider, sealed, time.time(), sealed, time.time()))

    def gif_keys(self, email: str) -> dict[str, str]:
        """Every key the person has added, by provider, readable."""
        found = {}
        for row in self._all("select provider, secret from gif_keys where email = ?", (email,)):
            try:
                found[row["provider"]] = _open(row["secret"])
            except Exception:  # noqa: BLE001 - a changed server key makes old ones unreadable
                log.warning("a stored GIF key could not be decrypted; it is ignored")
        return found

    def gif_key_hints(self, email: str) -> dict[str, dict[str, Any]]:
        """What the account page may show of each key: its last four characters and
        when it was added. Never the key."""
        hints = {}
        for provider, key in self.gif_keys(email).items():
            row = self._one("select created from gif_keys where email = ? and provider = ?",
                            (email, provider))
            hints[provider] = {"ends": key[-4:], "added": row["created"] if row else None}
        return hints

    def remove_gif_key(self, email: str, provider: str | None = None) -> None:
        if provider is None:
            self._do("delete from gif_keys where email = ?", (email,))
        else:
            self._do("delete from gif_keys where email = ? and provider = ?", (email, provider))

    def gif_source(self, email: str) -> str:
        row = self._one("select gif_source from people where email = ?", (email,))
        return (row["gif_source"] if row else "") or ""

    def set_gif_source(self, email: str, source: str) -> None:
        if source not in (*GIF_PROVIDERS, "both"):
            raise AccessError("choose GIPHY, KLIPY or both")
        self._do("update people set gif_source = ? where email = ?", (source, email))

    # -- profile and history ----------------------------------------------

    def rename(self, email: str, name: str) -> Person:
        name = " ".join(str(name or "").split())
        if not name:
            raise AccessError("a name cannot be empty")
        if len(name) > ANSWER_LIMITS["name"]:
            raise AccessError("that name is too long")
        self._do("update people set name = ? where email = ?", (name, email))
        return self.person(email)  # type: ignore[return-value]

    def record(self, email: str, *, video_id: str, title: str, channel: str, mode: str,
               start: float, end: float, stem: str, ok: bool, seconds: float,
               error: str = "") -> None:
        """One line of a person's history: a render that finished or failed. Only
        for a person who still exists: a render finishing as its account is deleted
        must not write the account's history back."""
        if self.person(email) is None:
            return
        self._do("insert into history (email, at, video_id, title, channel, mode, start, end, "
                 "stem, ok, seconds, error) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (email, time.time(), video_id[:20], title[:300], channel[:200], mode[:10],
                  start, end, stem[:200], int(ok), round(seconds, 1), error[:200]))
        self._do("delete from history where at < ?", (days_ago(HISTORY_DAYS),))

    def history(self, email: str, limit: int = 200) -> list[dict[str, Any]]:
        # Filtered as well as pruned: pruning happens on a render, and somebody who
        # stops making clips must still see nothing older than the promise.
        rows = self._all("select at, video_id, title, channel, mode, start, end, stem, ok, "
                         "seconds, error from history where email = ? and at >= ? "
                         "order by at desc limit ?", (email, days_ago(HISTORY_DAYS), limit))
        return [dict(r) | {"ok": bool(r["ok"])} for r in rows]

    def forget_old_usage(self) -> int:
        """Daily counts older than USAGE_DAYS, which nothing reads any more and the
        privacy page promises are not kept for ever. Run by the nightly tidy."""
        cur = self._do("delete from usage where day < ?", (today(days_ago(USAGE_DAYS)),))
        return cur.rowcount

    def days(self, email: str, count: int = 14) -> list[dict[str, Any]]:
        """The person's last `count` days, oldest first, each with its counts."""
        rows = {r["day"]: dict(r) for r in self._all(
            "select day, clips, failures, upload_bytes from usage where email = ? and day >= ?",
            (email, today(days_ago(count - 1))))}
        out = []
        for back in range(count - 1, -1, -1):
            day = today(days_ago(back))
            row = rows.get(day, {})
            out.append({"day": day, "clips": row.get("clips", 0),
                        "failures": row.get("failures", 0),
                        "upload_bytes": row.get("upload_bytes", 0)})
        return out

    # -- reports and alerts ------------------------------------------------

    def report(self, source: str, phase: str, code: str, detail: str = "",
               versions: str = "", email: str = "") -> None:
        def short(value: str, limit: int) -> str:
            return " ".join(str(value or "").split())[:limit]
        self._do("insert into reports (at, email, source, phase, code, detail, versions) "
                 "values (?,?,?,?,?,?,?)",
                 (time.time(), email, short(source, 40), short(phase, 40), short(code, 80),
                  short(detail, 400), short(versions, 120)))
        self._do("delete from reports where at < ?", (time.time() - 30 * 86400,))

    def reports(self, since: float, source: str | None = None) -> list[dict[str, Any]]:
        sql = "select * from reports where at >= ?" + (" and source = ?" if source else "")
        rows = self._all(sql + " order by at desc limit 500",
                         (since, source) if source else (since,))
        return [dict(r) for r in rows]

    def should_alert(self, key: str, every: float) -> bool:
        """True at most once per `every` seconds for a key: one message, not a storm."""
        now = time.time()
        with self._write:
            db = self._db()
            row = db.execute("select last from alerts where key = ?", (key,)).fetchone()
            if row is not None and now - row["last"] < every:
                db.execute("update alerts set count = count + 1 where key = ?", (key,))
                db.commit()
                return False
            db.execute("insert into alerts (key, last, count) values (?,?,1) "
                       "on conflict(key) do update set last = ?, count = 1", (key, now, now))
            db.commit()
            return True

    def backup(self, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._write:
            target = sqlite3.connect(dest)
            self._db().backup(target)
            target.close()
        os.chmod(dest, 0o600)
        return dest


# -- encryption for what has to be read back --------------------------------

def _fernet():
    from cryptography.fernet import Fernet

    secret = os.environ.get(SECRET_ENV) or ""
    if len(secret) < 32:
        raise AccessError(f"{SECRET_ENV} is not set, so nothing can be stored encrypted")
    key = base64.urlsafe_b64encode(hashlib.sha256(("gif:" + secret).encode()).digest())
    return Fernet(key)


def _seal(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def _open(value: bytes) -> str:
    return _fernet().decrypt(value).decode()


def days_ago(days: int) -> float:
    return (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
