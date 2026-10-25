# Incidents

Last updated **2026-10-25T15:21:02+05:30**

Postmortems: what went wrong, what it cost, why, and what changed so it does not
happen again. Every entry is drawn from the project's own record, and each names the
document it came from. Nothing here is reconstructed from memory. The decisions they
led to are in [DECISIONS.md](DECISIONS.md), the work in [TASKS.md](TASKS.md), and what
is still open in [LIMITATIONS.md](LIMITATIONS.md).

A near miss is recorded the same way as an outage. Several of the entries below cost
nothing because they were found first, and the lesson is the same.

**Table IN-1: index**

| Id | Date | What | Impact | Links |
|---|---|---|---|---|
| IN-01 | 2026-08-18 | One command posted two Statuses | a duplicate on a real account | D-020 |
| IN-02 | 2026-08-18 | A design built on an untested claim about caption links | a wrong product design, reversed the same day; a second detour the day after | D-003, D-013, T-012 |
| IN-03 | 2026-08-18 | A fixed bitrate would have made every 60 second clip unpostable | near miss | D-017, T-014 |
| IN-04 | 2026-08-20 | WhatsApp renamed two controls and every post stopped | no posting for an evening | D-041, T-026 |
| IN-05 | 2026-08-20 | A refused POST poisoned the keep-alive connection behind it | an evening spent on a misleading log | D-042 |
| IN-06 | 2026-08-20 | Two renders could claim one output name | latent; never happened | T-017 |
| IN-07 | 2026-08-22 | The test suite was writing into the real logs | thirteen fake run records in `runs.jsonl` | none |
| IN-08 | 2026-08-31 | A refused Status was reported as sent | a Status the owner believed was live was not | D-071, D-072, D-073, D-074 |
| IN-09 | 2026-09-01 | A green test was measuring a layout that no longer existed | near miss | D-078, T-064 |
| IN-10 | 2026-10-24 | WhatsApp dropped the Send icon the tool waited for | every load timed out | D-079, T-065 |
| IN-11 | 2026-10-25 | Two faults found only in production: mail refused, Turnstile never drawn | owner notifications and the request form broken at launch | none |
| IN-12 | 2026-10-25 | Every clip opened on a black frame | black thumbnails in WhatsApp | D-094 |
| IN-13 | 2026-10-25 | The pre-publication audit | latent faults, one of them a breach of D-071 | D-071, D-093 |

---

## IN-01: one command posted two Statuses

- **Date:** 2026-08-18
- **What happened:** two Statuses went out a second apart from one posting command.
- **Impact:** a duplicate Status on the owner's real account.
- **Root cause:** WhatsApp's Status composer holds every file it is given and Send
  posts all of them. An earlier run had left a composer loaded, and the next run
  attached into it.
- **Fix:** `load_video` backs out of an open composer before attaching. Later, two
  overlapping post requests are refused with a 409, and the page loads the composer
  and stops, so sending is a second, deliberate press.
- **Lesson:** sending is the one irreversible step. Make it the one a person does, and
  never assume the composer is empty.
- **Source:** [CHANGELOG.md](CHANGELOG.md), "Fixed: a composer left open sent two
  Statuses"; [MEMORY.md](MEMORY.md); [DECISIONS.md](DECISIONS.md) D-020.

## IN-02: a design built on an untested claim about caption links

- **Date:** 2026-08-18, and a second detour on 2026-08-19.
- **What happened:** the first design posted every Status twice, because a URL in a
  media caption was believed not to be tappable (D-003). A real post showed the
  caption renders as an anchor on the web client and opens the YouTube app from a
  phone. The next day a caption check made from the posting phone alone concluded
  that Android captions were not linkified, which was also wrong.
- **Impact:** a two post design, reversed the same day (D-013); a second design detour
  the day after.
- **Root cause:** the claim came from secondary sources, not a device test. The second
  time, WhatsApp does not linkify your own Status caption **on the device you posted
  it from**; the link is live on any other device.
- **Fix:** one post by default, `--follow-up` as an option. The finding is recorded
  as settled in MEMORY.md, and LOCAL_SETUP and the FAQ warn about it.
- **Lesson:** a load bearing claim from a secondary source is worth a five minute
  test before anything is designed around it. Any caption check needs a second
  device. Whether the link works on other people's clients is still open, T-012.
- **Source:** [DECISIONS.md](DECISIONS.md) D-003 and D-013; [MEMORY.md](MEMORY.md),
  **Settled**; [TASKS.md](TASKS.md) T-012.

## IN-03: a fixed bitrate would have made every 60 second clip unpostable

- **Date:** 2026-08-18; the ceiling bisected on 2026-08-20.
- **What happened:** a fixed 2800 kbit/s encoder ceiling produced about 21 MB at 60
  seconds. WhatsApp refuses media over its real limit by never opening its editor,
  with no message at all.
- **Impact:** none in the end: found by measuring against the real composer before
  long clips were in use. Unfixed, it would have looked like a bug in the posting
  driver rather than in the encoder.
- **Root cause:** the limit was taken from the platform's documentation (16 MB). The
  real line is **10 MiB**, 10,485,760 bytes, bisected between 10,452,278 accepted and
  10,519,352 refused.
- **Fix:** `render.video_maxrate` derives the ceiling from the duration, so a clip
  lands near 10 MB whatever its length, and a clip that goes over is called out
  rather than refused in silence.
- **Lesson:** measure a platform's limit against the platform. A silent refusal
  surfaces in the wrong component.
- **Source:** [DECISIONS.md](DECISIONS.md) D-017; [TASKS.md](TASKS.md) T-014;
  [DOMAIN.md](DOMAIN.md), Table DO-1.

## IN-04: WhatsApp renamed two controls and every post stopped

- **Date:** 2026-08-20. Last good post 2026-08-19 22:53, first failure 2026-08-20
  19:42.
- **What happened:** `Photo and video` became `Photos & videos`, `Text status` became
  `Text`, and both moved behind an **Add Status** button. The tool said `could not
  find a control labelled 'Photo and video'`.
- **Impact:** no posting from the tool for an evening.
- **Root cause:** labels were matched by exact string equality, unchanged since the
  first commit that could post. It surfaced after a reboot because Chrome restarted
  and fetched a newer WhatsApp Web build; the tab had been running the old one from
  memory.
- **Fix:** labels are matched on **words** (`photo video`), each control has a list
  of spellings, the menu is opened only if the choice is not already visible, and the
  error names the file and the list to widen. T-026 then added a probe that checks
  the controls once per server run, before a post rather than during one.
- **Lesson:** a third party's interface changes without notice. Match loosely, fail
  with the fix in the message, and look before you need it.
- **Source:** [CHANGELOG.md](CHANGELOG.md), "WhatsApp renamed two controls and every
  post stopped"; [MEMORY.md](MEMORY.md), Table ME-10; [DECISIONS.md](DECISIONS.md)
  D-041; [TASKS.md](TASKS.md) T-026.

## IN-05: a refused POST poisoned the keep-alive connection behind it

- **Date:** 2026-08-20
- **What happened:** the local page's log filled with `501 Unsupported method
  ('{"url":...}POST')` at the same time as every request from an old tab was answered
  `403 bad or missing token`.
- **Impact:** a log line that named nothing actually wrong, and an evening spent
  looking at the wrong thing.
- **Root cause:** `do_POST` answered 403 without reading the request body. The
  connection is keep-alive (`HTTP/1.1`), so the body stayed in the socket and the
  next request line was parsed out of the middle of it. The 403 itself was correct:
  the tab predated a restart, and the token is minted per process.
- **Fix:** the body is read, bounded by `MAX_BODY_BYTES`, before anything is decided.
  Closing the connection instead was rejected, because a tab left open across a
  restart would reconnect four times a minute. `TestKeepAlive` fails without the fix.
  The page now says "this page is older than the server. Reload it".
- **Lesson:** on a persistent connection, a refusal still has to consume the request.
  The 2026-10-25 audit found the same class again on the hosted site (IN-13).
- **Source:** [DECISIONS.md](DECISIONS.md) D-042; [CHANGELOG.md](CHANGELOG.md), "A
  refused POST was corrupting the connection behind it"; [MEMORY.md](MEMORY.md),
  Table ME-10.

## IN-06: two renders could claim one output name

- **Date:** found and fixed 2026-08-20.
- **What happened:** nothing visible. Two identical renders started in the same
  second could pick the same output stem, and one clip would overwrite the other.
- **Impact:** none: it needs the same song and window submitted twice at once, and it
  never happened.
- **Root cause:** `naming.unique_stem` checked the folder and the render wrote to it
  half a minute later: check then act, with the whole render as the window.
- **Fix:** `naming.reserve_stem` **claims** the name by creating the `.part` file with
  `O_CREAT|O_EXCL`, which only one caller can win, across processes. A claim left by a
  killed render is logged as a warning rather than silently stepping to `-2`. Eight
  threads asking at once get eight names; the test loses a file against the old code.
- **Lesson:** a lock would only have covered the page. Make the allocation atomic
  where it happens.
- **Source:** [TASKS.md](TASKS.md) T-017; [LIMITATIONS.md](LIMITATIONS.md), Table LI-1;
  [CHANGELOG.md](CHANGELOG.md).

## IN-07: the test suite was writing into the real logs

- **Date:** 2026-08-22
- **What happened:** running the suite appended thirteen fake run records to
  `logs/runs.jsonl`, against `https://youtu.be/abc`, failing with
  `ZeroDivisionError`, and four launch headers to `logs/chrome.log`.
- **Impact:** the file read to judge which extraction strategy is working was being
  seeded with fake failures. Nobody noticed, because neither file is in git.
- **Root cause:** tests used the real log directory.
- **Fix:** an autouse guard in `tests/conftest.py` points every test's logging at a
  temporary directory, and a test asserts it is not the project's. The existing
  records were left alone: they are identifiable by that URL.
- **Lesson:** found by copying both files, running the suite and diffing. Check what a
  test run leaves behind.
- **Source:** [CHANGELOG.md](CHANGELOG.md), "Found while auditing: the tests were
  writing into the real logs".

## IN-08: a refused Status was reported as sent

- **Date:** 2026-08-31, the refused send at 19:21.
- **What happened:** reported as WhatsApp Web showing the video as published, while
  the Status could not be seen on the phone and had zero views. The same clip had
  been posted twice: at 18:14 with `ack 3` (read), and at 19:21 with `ack -1`
  (refused). The tool called both a success in four seconds.
- **Impact:** a Status believed live was not, and every posting result the tool had
  ever logged was unverified.
- **Root cause:** `wait_until_sent` only asked whether the composer was gone and
  nothing said "Sending", both facts about this browser and none about WhatsApp.
  Every posting run in `runs.jsonl` took exactly 4.0 seconds, the arithmetic floor of
  that function: it was measuring its own sleep. Why WhatsApp refused that send is
  unknown; it records no reason client side.
- **Fix:** `confirm_sent` reads the `ack` WhatsApp keeps against the message in its
  own store, and tells this Status from the last one by id and by time (D-071). A
  refusal (`StatusRefused`) is retried at 20, 40 and 80 seconds; no answer
  (`StatusUnconfirmed`) is never retried, because that Status may still be on its way
  (D-073). The sheet records only what was accepted (D-074). Reading the page for
  this also found the caption box selector could match a chat's message box, which
  could have typed the link into an open group chat and sent it (D-072, a near miss).
  The same evening, a deleted Status's protocol row was caught masquerading as the
  newest Status.
- **Lesson:** "done" has to be a fact about the other system, not about your own
  screen. A duration that never varies is a measurement of your own code.
- **Source:** [DECISIONS.md](DECISIONS.md) D-071, D-072, D-073, D-074;
  [LIMITATIONS.md](LIMITATIONS.md), Table LI-2; [CHANGELOG.md](CHANGELOG.md), 2026-08-31
  forty sixth pass.

## IN-09: a green test was measuring a layout that no longer existed

- **Date:** 2026-09-01
- **What happened:** `tests/test_safe_zone.py`, which guarantees no text is drawn
  under WhatsApp's header or into its caption band, worked the card layout out a
  second time beside the copy in `build_card`. D-075 changed the drawing; the test
  kept passing, describing the old layout.
- **Impact:** none. The guarantee was silently void until an audit found it.
- **Root cause:** duplicated layout logic. Its failure mode is a green test, not a red
  one.
- **Fix:** `compose.card_words` is the one function the drawing and the test both
  ask; the test only measures what it is given.
- **Lesson:** a test must ask the code under test, not reimplement it.
- **Source:** [CHANGELOG.md](CHANGELOG.md), "The audit: a green test measuring a frame
  that no longer existed"; [DECISIONS.md](DECISIONS.md) D-078; [TASKS.md](TASKS.md)
  T-064.

## IN-10: WhatsApp dropped the Send icon the tool waited for

- **Date:** 2026-10-24
- **What happened:** WhatsApp Web stopped putting `data-icon` on the composer's Send
  button. `--load` and `--post` waited 75 seconds for a Send button already on
  screen, then said the editor never opened.
- **Impact:** every load and post from the local tool failed. Found while testing the
  extension, not reported by a failed post.
- **Root cause:** the Send button was recognised by its icon alone.
- **Fix:** Send is matched by its label too (`Send 1 selected`, `Send`). The check for
  an already open composer recognises the text composer by its `Close status posting
  view` control, so a chat with a typed reply is never taken for one.
- **Lesson:** the same as IN-04, two months later: every selector against a third
  party's page needs a second way to be found.
- **Source:** [DECISIONS.md](DECISIONS.md) D-079; [TASKS.md](TASKS.md) T-065;
  [CHANGELOG.md](CHANGELOG.md), "Send has no icon any more".

## IN-11: two faults found only in production

- **Date:** 2026-10-25, at SnipShare's launch.
- **What happened:** the first mail from the server was refused with a 403, error
  1010. Separately, the request form's Turnstile box stayed empty.
- **Impact:** owner notifications by mail did not arrive; the human check on the
  access form never rendered.
- **Root cause:** Cloudflare in front of Resend's API refuses Python's default
  User-Agent. An element with `id="turnstile"` answers to `window.turnstile` and hid
  Turnstile's own global object.
- **Fix:** `notify.py` sends its own `User-Agent`; the box was renamed.
- **Lesson:** a third party's edge is part of its API. Both passed every local test.
- **Source:** [CHANGELOG.md](CHANGELOG.md), "Audited three times"; [MEMORY.md](MEMORY.md);
  `wastatus/notify.py`.

## IN-12: every clip opened on a black frame

- **Date:** 2026-10-25
- **What happened:** reported with two screenshots: WhatsApp's composer showed a
  loaded clip as a black rectangle until it was played, and its thumbnail was black.
- **Impact:** every clip looked empty in the composer and in the Status list.
- **Root cause:** the picture faded in from black over its first 0.3 seconds, and
  WhatsApp shows the first frame before anybody presses play.
- **Fix:** the picture no longer fades in, in either mode. The sound still rises over
  0.2 seconds so it does not click. A test makes a clip and measures its first frame.
- **Lesson:** the first frame is the thumbnail. Check output where it is shown, not
  only where it is played.
- **Source:** [DECISIONS.md](DECISIONS.md) D-094; [CHANGELOG.md](CHANGELOG.md), "A clip
  opens on its picture".

## IN-13: the pre-publication audit

- **Date:** 2026-10-25, before the repository was made public.
- **What happened:** an audit of the whole system ahead of publication found a set of
  latent faults. None had been reported by a user. The most serious:
  - an unreadable WhatsApp store was reported as **sent** once the composer closed,
    a breach of D-071 (IN-08). It now raises `StatusUnconfirmed`, and a busy browser
    is told apart from an unreadable store;
  - a body left unread on a refused account call, and a GET or HEAD carrying a body,
    could desynchronise a connection the tunnel shares between people: the IN-05
    class again, now with other people's requests behind it. Refused bodies close the
    connection; a GET with a body is a 400;
  - a 300,000 character title could hold the only render slot for hours. Text fields
    are capped at 1024 characters and the URL at 2048;
  - a "URL" beginning `--` could be read by yt-dlp as an option. yt-dlp now gets `--`
    before the URL;
  - the sign-up answer could reveal whether an address had an account;
  - the local server answered any `Host`, so DNS rebinding could read its token;
  - ffmpeg and ffprobe accepted any protocol and format in an uploaded capture.
- **Impact:** none known. The production deployment had not been redeployed with the
  fixes when they were written.
- **Root cause:** several, each local. The pattern is that the hosted site made
  failure modes that were harmless on a single user's loopback reachable by
  strangers.
- **Fix:** each with a test, including `tests/test_hardening.py`. What was left is in
  [LIMITATIONS.md](LIMITATIONS.md): the base image is not pinned by digest, the Python
  requirements use `>=`, and a long hidden YouTube tab may be throttled by Chrome.
- **Lesson:** rules already decided (D-071, D-042) regress when the code around them
  grows. Re-read the decisions against the code before a wider audience arrives.
- **Source:** the audit notes of 2026-10-25; [CHANGELOG.md](CHANGELOG.md);
  [LIMITATIONS.md](LIMITATIONS.md).

---

## Patterns across these

**Table IN-2: recurring causes**

| Cause | Incidents | The rule it produced |
|---|---|---|
| A third party's interface changed without notice | IN-04, IN-10, IN-11 | match WhatsApp's controls by words and by more than one attribute; say in the error what to widen (D-041, D-079) |
| A claim or limit taken on trust | IN-02, IN-03 | test a load bearing claim on the real platform, from a second device |
| Success inferred from our own side | IN-08, IN-13 | a Status is posted when WhatsApp's `ack` says so (D-071) |
| A request not read to the end | IN-05, IN-13 | read or close; never leave a body in the socket (D-042) |
| A test that cannot fail | IN-07, IN-09 | tests ask the code under test, and write nowhere real |

A new incident gets the next IN number, a row in Table IN-1, and the same seven
headings. Link the decision or task it led to; if it led to none, say why.
