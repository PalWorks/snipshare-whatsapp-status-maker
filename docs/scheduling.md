# Scheduled Statuses: requirement and implementation plan

Written **2026-10-31T00:01:09+05:30** from the owner's request of 2026-10-30.
Revised **2026-10-31T00:15:53+05:30** with the owner's answers to the first
decisions (Table SC-9) and two further asks: a queue the person can rearrange,
retime and post from at once, and a plan for getting video in and clips held
without overwhelming the browser's storage. Revised again
**2026-10-31T00:23:55+05:30**: the queue is a table on an extension page, ordered by
time alone, each post's time edited in its own row (SC-D12). Revised again
**2026-10-31T00:29:11+05:30**: two ways into the queue, **From the editor** (a clip
the person made and looked at) and **From a link** (a link and instructions, the
clip made for them), Section 1b. **Status: plan complete and reviewed (Section 14), every decision taken
(Tables SC-9, SC-10 and SC-17, the last at 2026-10-31T00:31:42+05:30).**
**Status, 2026-10-31T01:51:25+05:30: Release 1 is built (From the editor, Prepare only), and Phase 0 is
pending.** Nothing in it has been tried in a real WhatsApp Web or on the owner's Chrome.
Section 15 says what was built, what differs from this plan and why, and what is
unverified. Releases 2 and 3 and confirmed Send are not built. The next step is Phase 0,
on the owner's word, then a week of the owner's use.

Claims about Chrome's behaviour that this repository has not measured are labelled.
Phase 0 measures them before anything is built, as was done for the extension
([extension-spike.md](extension-spike.md)) and for SnipShare
([hosted-page.md](hosted-page.md), Phase 0).

## 1. What is asked, restated precisely

Today a clip goes from the frame to WhatsApp only when a person presses **Load into
WhatsApp**, and the extension then brings WhatsApp's tab to the front (D-084),
because a background tab was throttled into a timeout. Scheduling separates *when it
is decided* from *when it happens*:

1. The person makes the clip as now, then chooses **Schedule** (a time) or **Add to
   queue** (after the last one) instead of **Load into WhatsApp**.
2. The clip is kept safe for its due time: on this computer if it is due soon, on
   SnipShare, pinned against pruning, if it is due later, and brought down to this
   computer ahead of time. Nothing at the due time depends on a sign-in, and the
   browser never holds more than the person's budget.
3. At the due time, if Chrome is running with the extension loaded, the extension
   puts the clip into WhatsApp's Status composer and, when the person chose it for
   that schedule, sends it and confirms it went, **without moving the person's
   focus**: no window raised, no tab switched, no keyboard stolen.
4. If no quiet way works on this machine at that moment, it falls back in a fixed,
   visible order, ending with today's behaviour.
5. The person sees the whole queue as a table sorted by time, edits any post's time
   in its row (the table re-sorts itself), retimes many at once, pauses it, and posts
   any item at once.

### Table SC-1: terms

| Term | Meaning |
|---|---|
| Schedule | one clip, one caption, one due time, one action, held by the extension in this browser |
| Queue | all of a browser's pending schedules, in due time order |
| Due time | an instant, stored as epoch milliseconds; shown in the browser's own time zone |
| Action | **prepare**: load the composer and stop, the person presses Send (D-020, D-084). **send**: load, press Send once, confirm it went |
| Custody | where the finished clip is kept until its run: **local** (IndexedDB on this computer), **remote** (on SnipShare, pinned, with a schedule ticket), **fetching** (moving from remote to local) |
| Hot horizon | how far ahead clips are kept local; default 48 hours, shrunk automatically when the budget needs it |
| Budget | the most held clips may take on this computer: 1 GB for the owner (Table SC-9, D5) |
| Schedule ticket | a server issued token that can do one thing: read one clip until shortly after its due time. Not a session (Section 7) |
| Pin | the server's promise not to prune a clip while a ticket names it |
| Prewarm | a check five minutes before the due time that WhatsApp's tab is there, signed in and not discarded, and the clip is local |
| Quiet run | a run that completes without changing which window has focus or which tab is active in the window the person is using |
| Placement, ladder | where the WhatsApp page is while the run drives it; the ordered list of placements, quietest first (Table SC-4) |
| Fallback | the last rungs: ask by notification, then today's model (bring WhatsApp forward) |
| Catch-up window | how late a run may still go ahead after a missed due time; 30 minutes |
| Quiet hours | a daily stretch (default 23:00 to 07:00) in which nothing is posted unasked: a catch-up that would land in it waits for its end and asks |

## 1b. Two ways into the queue

The owner's distinction, 2026-10-31T00:28:04+05:30. "Scheduling" means two
different things to the person using it:

### Table SC-16: the two ways in

| | **From the editor** (B) | **From a link** (A) |
|---|---|---|
| What the person does | makes the clip on SnipShare as today, looks at it, adds GIFs, stickers, placed text, edits the caption, then presses **Schedule** or **Add to queue** | gives a link, the part to use, Card or Video, and when; nothing more. Many at once if they like |
| Who makes the clip | the person, in the page, while they watch | SnipShare, driven by the page, one after another, without the person watching |
| What is posted | exactly what they saw | a plain clip with SnipShare's defaults: the frame, the label and the caption the server writes for every clip |
| When the clip exists | before it is scheduled | soon after it is queued (SC-D15), before its due time |
| Who has looked at it | the person, always | nobody, until they choose to (SC-D16) |
| What it suits | the posts that matter, with care | volume: a week of Statuses from a list of links |

**The one idea that makes both simple: they meet at the same place.** Either way,
what the queue holds is a finished clip on SnipShare plus a schedule. **From the
editor** enters the queue already finished: this is what Sections 4 to 9 describe,
and the owner's description of it (store it on the server, bring it down at the
right time, push it to WhatsApp) is exactly custody (Sections 7 and 8; the clip comes
down up to 48 hours early only as a margin against a bad line at the due time).
**From a link** enters one stage earlier, as a **plan** (link, part, mode, caption
choice, time, action), and a making stage turns each plan into a finished clip.
After that the two are the same row in the same table, run by the same runner.
Nothing in custody, the ladder, sending or the table is built twice.

### How **From a link** works

**FR-19 Say what to make.** On the SnipShare page, desktop, **Schedule from links**
opens a form with one row per post: link, start, end or length, Card or Video, when
(or **Add to queue**), and Send or Prepare. Sensible defaults fill what is left out:
the start from the link's own `t=` or 0:00, a length of 30 s, Card, after the last
one in the queue, Prepare. A **Paste many** box takes one post per line in any
reasonable form (`https://youtu.be/abc?t=95 1:35-2:05 Wed 9am video`), parses each
leniently, and shows the interpreted rows before anything is queued; a line it cannot
read is shown with what is missing, never silently dropped (Error Prevention). The
words (title and channel) are fetched through the extension as today, so a private,
removed or live video is caught here, while the person is still there.

**FR-20 Make without watching.** Queued plans are made one at a time in the order
they are due, by the steps the page already takes for a clip: a grant from the
server, the capture in the extension, the render on SnipShare, then a schedule
ticket (Section 7). **The page drives it, so no new credential is needed**: making
uses the person's own session exactly as pressing **Make the clip** does. The
consequence is that making happens while a SnipShare page is open somewhere in that
browser; if every SnipShare tab is closed, making pauses, the table shows **Waiting
for SnipShare to be open** and offers **Open SnipShare to finish making**. Pacing is
today's: 20 captures an hour per browser and the person's clips a day (SC-D9), so the
table shows when each plan is expected to be made.

**FR-21 Capture without taking focus.** Today a capture opens the video in a tab
that is in front until its player is ready (D-090), because Chrome gives no media to
a tab that has never been in front. For one clip the person asked for, a second of
that is fine; for a batch of twenty it is the interruption this feature exists to
avoid. So capture gets a ladder of its own, the same focus guard as Section 6.1:

| Rung | Placement | Quiet? |
|---|---|---|
| C0 | a tab already showing the video, used as it is | yes |
| C1 | the video as the active tab of an unfocused helper window, muted, closed after the read [Inference: an active tab in a visible window is given its media; Phase 0 measures it] | yes if `focused: false` is honoured |
| C2 | today's: in front of the page, muted, until the player is ready, then back | no, about a second per clip |
| C3 | wait until the person is idle, then C2 | not seen |

**From the editor** keeps C2: the person is there and asked for it.

**FR-22 Made, then looked at or not.** A made clip takes its place in the table with
a **Not looked at** mark, a frame, and **Preview**, which plays it in the table. One
notification per batch says "5 of your scheduled clips are made. Look at them
when you can". What happens if nobody looks is SC-D16.

**FR-23 When making fails.** The row says why in plain words (private video, removed,
live, protected, the day's limit reached, SnipShare unreachable) with **Try again**,
**Edit** and **Cancel**. A plan still unmade 2 hours before its due time notifies;
at its due time it becomes **missed** with the reason. A plan never takes another's
place or time.

**FR-24 Edit in SnipShare.** Every row, made or not, offers **Edit in SnipShare**:
the editor opens with the row's link, part, mode and caption filled in; the person
adds what they like and presses **Make the clip**; the new clip replaces the row's,
keeping its time and action, and the old clip's ticket is deleted. This is how a plan
from a link becomes a post from the editor. The video is read again, because the
server keeps an upload only until it is made into a clip or abandoned (30 minutes
idle, `hosted.UPLOAD_IDLE`). For a row that came from the editor, its stickers, framing
and words are put back: the engine writes them beside every clip (`pipeline.py`,
`<stem>.json`), `serve.py` returns them as the clip's `job`, and the page's `recall`
(`app.js`) restores them (verified in code at the 2026-10-31 review). What still needs
defining is how long an uploaded sticker or GIF the composition names is kept.

### What the table shows for each

The table gains one column, **Made**: **Plan** (not yet made, with when it is
expected), **Making 40 %**, **Made, not looked at**, **Made** (looked at, or from the
editor), **Could not make** (with the reason). A plan's row cannot be posted until it
is made; **Post now** on a plan makes it first, then posts. Filtering by **Not
looked at** shows what still awaits the person's eyes.

## 2. Scope

### Table SC-2: in and out of scope for this version

| In | Out, and why |
|---|---|
| Scheduling a clip already made (From the editor), and a plan made into a clip soon after it is queued (From a link, Section 1b) | Making the clip at its due time: a capture can fail (ad, private video, slow line) and should fail while there is time to fix it (D6) |
| One-off schedules up to 30 days ahead (D5), arranged as a queue | Recurring schedules ("every day at 9"): the data model reserves a field (Table SC-15) |
| Retime in place, shift, spread, pause, post now, one or many at once | Saved looks (a set of stickers, GIFs and text reused across clips from a link): SC-D17 |
| Runs while Chrome is open, the profile loaded and the computer awake | Running with Chrome closed or the computer asleep: an extension cannot. Missed runs are caught up or reported (FR-9) |
| Prepare, and confirmed send as a per schedule choice (D1) | Choosing the Status audience: WhatsApp's own privacy setting applies, as for a manual send |
| The SnipShare page and the extension's options page | The local tool (`wastatus serve`), which has CDP and its own `--post` |
| One WhatsApp account per browser profile | Several accounts |

## 3. Who it is for, and what they do

- **The owner, batching.** On Sunday makes eight clips and presses **Add to queue**
  after each; they land three hours apart from Monday 9 AM. Moves Wednesday's ahead of
  Tuesday's by editing their times in their rows; the table re-sorts. Works all week in other windows; at
  each due time nothing on screen moves, and a quiet notification says **Sent**.
- **The owner, changing plans.** News breaks: selects the next clip, **Post now**.
  It goes in a minute; the rest keep their times. Travelling for two days: **Pause
  queue**; on return, three are overdue and the page offers **Post them in order,
  90 s apart**, **Move everything later by 2 days** or **Mark them missed**.
- **An invited person, away.** Schedules a clip for 8 PM and leaves the laptop open.
  If WhatsApp had signed out, the notification and the page say so, with what to do.
- **Anyone, laptop shut.** Within the catch-up window the run happens on waking;
  beyond it, the schedule is marked missed and offers **Post now** and **Change
  time**.

## 4. Functional requirements

### Creating

**FR-1 Create.** On a finished clip: **Load into WhatsApp** stays the one primary
action; beside it, secondary, **Schedule** and **Add to queue**. The picker offers
presets (in one hour, this evening 6 PM, tomorrow 9 AM, after the last one), a date
and time field, and shows the interpreted time in words before saving ("Sat 1 Nov,
6:00 PM, in 17 hours"). It refuses a time under 2 minutes or over 30 days away, and
warns (does not refuse) inside quiet hours, inline with the reason. Action: **Send
it for me** or **Put it in WhatsApp for me to send**, default the latter (D1), the
consequence written beside the choice. Caption editable. A due time within 90 s of
another is moved to 90 s after it, and the picker says so.

**FR-2 Custody at creation.** The page asks the server for a schedule ticket for the
clip (Section 7), which also pins it, and hands the ticket to the extension with the
`schedule` command. If the due time is inside the hot horizon and the budget allows,
the extension fetches the clip at once and answers saved when it is local and its
SHA-256 recorded; otherwise it answers saved as **remote**, after a ranged read of
the first byte proves the ticket works. Raw captures are never part of custody: once
the server has the upload, the browser holds nothing of the capture (Section 8.1).

### The queue

**FR-3 The schedule table.** The queue lives on an extension page of its own,
`queue.html`, as a table, one row per schedule, always sorted by due time, with day
separator rows (Today, Tomorrow, then dates). Columns: tick box, **When** (date and
time, editable in place, FR-5), a frame of the clip, the caption's first line
(editable in place), **Action** (Send or Prepare, a toggle), **State**, **Clip**
(**On this computer**, **On SnipShare, comes down Tue 6 PM**, **Coming down 40 %**),
and the row's actions. It opens from the SnipShare page's **Scheduled** link (the
page asks the extension over the port; a web page cannot open an extension page
itself), from the toolbar button's right-click menu, and from every notification.
A footer shows the budget in use ("412 MB of 1 GB on this computer") and **Pause
queue**. Empty: "Nothing scheduled. Make a clip on SnipShare, then choose Add to
queue". A running row shows its progress and is locked. Below 720 px wide the table
becomes one card per row with the same fields and order, so nothing scrolls
sideways. The SnipShare page shows only a compact **Up next** (the next three) and
the link; the options page keeps settings only.

**FR-4 Per row.** **Post now**, **Edit caption**, **Send or Prepare**, **Cancel**,
and the time in place. Every change that can be undone shows a toast with **Undo**
for 10 seconds; nothing is deleted until the toast ends.

**FR-5 Time is the order (D12, the owner's design).** There is no dragging and no
separate reorder: a schedule's due time is the only thing that decides its place,
and the table re-sorts itself after every change. To move a post, edit its time in
its row:

- The **When** cell becomes a date and time field on a click, Enter or F2, with the
  row's current value and a line under it in words ("Wed 5 Nov, 9:00 AM, in 4
  days"). Enter or leaving the field saves; Escape restores.
- Checked inline before saving, the error beside the field with how to fix it: not
  in the past, not over 30 days ahead, not past the ticket's end for a remote clip
  ("Open SnipShare to move this past Tue 4 Nov"). Quiet hours warn, they do not
  refuse.
- Within 90 s of another post, it is saved 90 s after that one and the line says so
  ("Moved to 9:01:30, 90 s after the clip at 9:00").
- On save the row moves to its new place with a short slide, keeps keyboard focus,
  is scrolled into view and highlighted for two seconds, and the toast says where it
  went ("Moved to Thu 6 Nov, 9:00 AM. Undo"). Undo puts it back, time and place.
- A row whose time is being edited does not jump while it is being edited, even if
  another change arrives from elsewhere; the change is applied when the edit ends,
  and a conflict on the same row is shown, not overwritten (FR-17).
- Custody follows the new time at once: a clip moved inside the hot horizon starts
  coming down; one moved out of it is let go if its ticket is valid.

**FR-6 Many at once.** Rows have a tick box; with any ticked, a bar offers:
**Post now** (in queue order, 90 s apart, with progress), **Shift** (by plus or
minus minutes, hours or days), **Spread** (from a start time, a fixed gap),
**Send or Prepare**, **Cancel**. Each is previewed (the new times on the rows) and
undoable.

**FR-7 Post now.** Runs that schedule immediately; the rest keep their times. With
action send, it takes the quiet ladder like a scheduled run. With action prepare,
it behaves as **Load into WhatsApp** does today and brings WhatsApp forward, because
the person asked to see it. A remote clip is brought down first, with progress.
**Post next now** sits at the top of the queue for the commonest case. Also offered
on every notification.

**FR-8 Pause and resume.** **Pause queue** stops all runs; prewarm and custody carry
on. On resume, anything that fell due while paused is listed with three choices:
**Post them in order, 90 s apart**, **Move them all later by the time paused**, or
**Mark them missed**. Nothing is posted on resume without that choice.

### Running

**FR-9 Arm, catch up, miss.** Each schedule has alarms `prewarm:<id>` at due minus 5
minutes and `due:<id>` at due, and one `sched-sweep` every 15 minutes while any is
pending, which also drives custody (Section 8.3). Schedules live in
`chrome.storage.local`; alarms are rebuilt from them on install, startup, every wake
and every sweep, because Chrome may drop alarms across a restart (noted in `sw.js`).
A due time that passed while Chrome was closed or the machine slept runs on the next
wake if less than the catch-up window late and not in quiet hours; otherwise it
becomes **missed**, is notified, and offers **Post now** and **Change time**.
Several missed at once are never run back to back unasked.

**FR-10 Prewarm.** At due minus 5 minutes: the clip is local and its hash checks;
WhatsApp's tab is found, reloaded in the background if discarded, marked not
discardable until the run ends, and checked signed in. A failure notifies at once
("WhatsApp Web is signed out. Scan the code before 6:00 PM") with a button that
brings the tab forward, which is the person's choice.

**FR-11 Run quietly.** Walk the ladder (Table SC-4) from the quietest placement this
machine is known to support. Focus is checked before and after every placement
change; a change the run caused is undone at once and recorded against that rung.

**FR-12 Respect the person.** Never run while the person is using WhatsApp (its tab
active in the focused window and `chrome.idle` active) or a Status composer is open:
wait in 1 minute steps for up to 10 minutes, then ask (FR-13). A manual load or
capture in flight takes priority, under the existing one-at-a-time rule for
WhatsApp.

**FR-13 Fallback.** If every quiet rung fails: when `chrome.idle` reports idle (60 s
without input), bring WhatsApp forward, run, and put focus back; otherwise notify
**Your 6:00 PM Status is ready. Post it now**, whose press runs today's model (D3).
The setting **Bring WhatsApp forward when needed** skips the asking.

**FR-14 Confirmed send (D1).** Only for schedules whose action is send. After the
composer is loaded and the caption read back equals what was scheduled, a
notification **Sending your 6:00 PM Status in 60 s. Cancel** gives a last chance;
then Send is pressed **at most once**, and confirmed: the composer closed and **My
status** gained an entry. A run interrupted after Send may have been pressed is
**unconfirmed**, never retried, and the person is asked to look. This is the rule
that stopped two Statuses going out in 2026-08 (D-020).

**FR-15 Outcomes.** Every run ends in one recorded state (Table SC-6), with the
placement used, the time it took and the error if any, notified once. **History**
below the queue shows the last 30 days with **Schedule again**.

**FR-16 Learn the machine.** The extension keeps which placements have worked
quietly and how long they took, and starts the ladder at the best one. A placement
that failed three times running is skipped for a week, then tried again.

**FR-17 One editor at a time, many viewers.** The extension is the only owner of the
queue. Every schedule carries a revision; a change names the revision it was made
against and is refused if another page changed it first, and the page then shows the
current queue. Open pages subscribe and are told of every change, so the page and
the options page never disagree.

### Limits

**FR-18 Limits (D5 and Table SC-10).** Due at most 30 days ahead. Per browser, at
most 90 pending schedules for the owner (three a day for 30 days) and 30 for others;
held clips within the person's budget, 1 GB for the owner. The server tells the page
each person's figures; the extension enforces the smaller of those and its own.
Refusals say which limit and what frees room.

## 5. Non-functional requirements

### Table SC-3: qualities and how each is checked

| Quality | Requirement | Checked by |
|---|---|---|
| Focus | a run in placements S0 to S2 never changes the focused window or the active tab of the window the person is in | the focus guard's log; Phase 0 and Phase 9 matrices |
| Timeliness | a run starts within 60 s of its due time when the machine is awake | alarm lateness recorded per run [Unverified: Chrome's alarm granularity is 30 s from Chrome 120, a minute before; the extension's minimum is 116] |
| Reliability | 95 percent of runs on an awake machine with WhatsApp signed in end prepared or sent | outcome codes |
| Safety | never a double send; never a send the person did not choose for that schedule | FR-14; state machine tests |
| Storage | held clips never exceed the budget; a full disk or quota error is reported and handled, never a silent loss | Section 8; tests with a fake store and an injected `QuotaExceededError` |
| Memory | a capture holds at most what it holds today (200 MB per YouTube tab); scheduling adds no capture memory; a clip moved to WhatsApp is held once, not three times | Phase 0 and Phase 8 measurements |
| Privacy | no caption, video id or due time leaves the browser beyond what the server already has for the clip; the server learns that a clip is pinned and until when | review against D-089's reporting rule |
| Security | queue commands only from the built site's origin; tickets read one clip and nothing else, end shortly after the due time, die with a suspension | `allowedOrigin`, `accounts.check_grant`; pytest per rule |
| Resilience | a worker stopped at any point resumes or ends cleanly from stored state | every transition persisted, as `sw.js` does for jobs |
| Accessibility | the picker and the table work fully by keyboard; editing a time keeps focus on its row when it moves, and the move is announced; visible focus; both themes | the page's existing checks |
| Layout | the page's parts render at 360 px without horizontal scroll, though scheduling itself needs desktop Chrome | the page's existing checks |

## 6. The placement ladder

What this repository knows: a background WhatsApp tab was throttled hard enough to
time the composer out (D-084), and Chrome gives no media to a tab that has never been
in front (`sw.js`, `pageCapture`). What is not known is which placements survive
those two facts once the composer steps are rewritten for a hidden page (6.2).

### Table SC-4: the ladder, quietest first

| Rung | Placement | When it applies | Quiet? | Main risk |
|---|---|---|---|---|
| S0 | WhatsApp's existing tab, left where it is, never activated | a WhatsApp tab exists, signed in, has been shown at least once | yes | intensive timer throttling in a page hidden over 5 minutes; the composer's video preview may need rendering a hidden page does not do [Inference] |
| S1 | a new background tab (`active: false`) in the window the person last used | no WhatsApp tab exists | yes, a tab appears in the strip | never shown, so Chrome withholds its media [Inference] |
| S2 | an unfocused helper window (`chrome.windows.create({focused: false})`), small, at a screen edge; an existing WhatsApp tab is moved into it and back, never duplicated | S0 or S1 failed or is known not to work here | only if the window manager honours `focused: false` [Unverified on the owner's Linux desktop] | a second WhatsApp tab triggers WhatsApp's "Use here" conflict, which is why the tab is moved |
| S3 | the front, while the person is idle, focus put back afterwards | `chrome.idle` idle for 60 s | not quiet, nobody is looking | the person comes back mid-run; the run finishes rather than abandon a half loaded composer |
| S4 | ask: a notification, whose press runs today's model | the person is active and S0 to S2 failed | yes until pressed | the person is away; it waits |
| S5 | today's model without asking (D-084) | only with **Bring WhatsApp forward when needed** | no | the interruption the feature avoids |

### 6.1 The focus guard

Before any rung: record the focused window and its active tab, and listen to
`chrome.windows.onFocusChanged` and `chrome.tabs.onActivated` for the run's length.
After each placement change and at the end, compare. A change within 1.5 s of the
run's own call is the run's, is undone at once and recorded against that rung
(FR-16). On S3 and S5 the original focus is restored at the end unless the person
moved it meanwhile.

### 6.2 Composer steps that work in a hidden page

`whatsapp.js` waits with `await sleep(300)` loops. In a hidden page those run at
most once a second, and after 5 minutes hidden a chain of them can be held to once a
minute [Inference from Chrome's documented intensive throttling; consistent with
D-084, not measured here]. The rewrite:

- Wait on the page, not on timers: `waitFor(selector, limit)` on `MutationObserver`.
- The service worker keeps time: it holds the port open and sends `tick` every
  500 ms, on which the page re-checks; a message is a task, not a timer
  [Inference, measured in Phase 0].
- The 75 s and 150 s limits are measured in the worker.
- Selectors stay in step with `post.py`; `tests/test_extension.py` already fails on
  drift. The Send selector used by FR-14 is the one `post.py` uses.

### 6.3 Keeping the tab alive

From prewarm to the end of the run, WhatsApp's tab is `autoDiscardable: false`, set
back afterwards. A discarded tab is reloaded in the background and waited on.

## 7. Custody across the server: schedule tickets and pins

Holding every clip for 30 days on the computer would need the whole budget for a
week of video clips, and fetching a clip at its due time would need a sign-in the
extension does not have (D-090). So far-off clips stay on SnipShare, and the
extension holds a ticket that can fetch that one clip.

**What the server has today, and what blocks this:**

### Table SC-5: server facts that scheduling meets

| Fact (file) | Effect on scheduling | Change |
|---|---|---|
| A grant lasts 15 minutes, slides while used, and never outlives 2 hours (`accounts.GRANT_SECONDS`, `GRANT_LIFETIME`, D-101) | a clip grant cannot reach a due time days away | a new purpose `schedule`, scope the clip's stem, lasting until due plus catch-up plus 24 hours, at most 31 days; never slid; an amendment to D-101 for this purpose alone |
| `check_grant` refuses anyone not approved (`accounts.py`) | a suspended person's tickets stop working at once | none; this is what is wanted |
| Only the 10 newest clips per person are kept; the 11th prunes the oldest (`portal.KEEP_CLIPS`, `retention.prune`) | a queue of 30 would lose its far end on the server | a persistent pin table; `prune` skips pinned stems, and pinned clips do not count towards the 10 |
| `retention.hold` is in memory only | lost on a restart | the pin table is in the accounts database, read by `prune` |
| 10 clips and 500 MB of upload a day per person (`accounts.limits`) | a Sunday batch of eight video clips is close to both | per person limits set by the admin (Table SC-10, SC-D9) |
| Clips of anybody away 90 days are removed (D-089) | a 30 day queue is well inside | a pinned clip is not removed while pinned |

**The ticket.** Minted by `POST /api/schedule-ticket {stem, due}` from the page (the
person's session), stored hashed like every grant, returned once. It authorises
`GET /api/v1/clip?stem=` for that stem, with Range, and `DELETE
/api/schedule-ticket` with itself, nothing else. It is used only against the page's
own origin, whatever a message says (D-090). Pins: one row per ticket (`email,
stem, until, bytes`); a pin ends when its ticket is deleted or expires; the daily
sweep removes expired pins. Pinned bytes per person are capped (owner 3 GB, others
1 GB) so the server's disk stays bounded.

**Why this is not a session.** It reads one clip the person already made, ends by
itself, dies with suspension, and is revoked when the schedule is cancelled or
done. Leaked, it shows one clip to whoever holds it before it ends. That is the
trade put to the owner in SC-D8.

**Changing time past the ticket.** Editing a time, shift and spread may
move a remote clip's due time up to its ticket's end minus the catch-up window. A
move beyond that is offered only on the SnipShare page, which mints a fresh ticket;
the options page says "Open SnipShare to move this past Tue 4 Nov". Local clips
need no ticket and move freely within 30 days.

## 8. Getting video in and clips held, without overwhelming the browser

Four places hold bytes. Each has a rule.

### Table SC-6: where bytes live, and the rule for each

| Stage | Where | Today | Rule from this plan |
|---|---|---|---|
| 1. Capture | the YouTube tab's memory (`recorder.js`) | up to 200 MB per tab, the player's own buffer copied | unchanged cap; **released as soon as the extension has the window** (8.1); one capture at a time (already) |
| 2. Transit | the service worker's memory | the window arrives as base64 messages, decoded to parts, joined to a Blob, uploaded, then dropped (page path); kept in IndexedDB until uploaded (popup path) | parts dropped as soon as the Blob is made; the Blob dropped when the server acknowledges the last chunk; popup path deletes its capture keys on that acknowledgement |
| 3. Render | SnipShare's disk | the clip kept among the person's 10 newest | pinned while scheduled (Section 7) |
| 4. Custody | IndexedDB, `sched:<id>:clip` | nothing | hot horizon and budget (8.2, 8.3) |

### 8.1 Capture and transit: nothing kept that the server already has

- After `done`, the extension tells the page to drop the stored fragments of that
  video's MediaSource. Whether `recorder.js` already lets go when the player removes
  its own buffer is to be measured, not assumed; Phase 0 measures the tab's memory
  before, during and after a capture.
- Blobs Chrome holds for a worker may be paged to disk when large [Inference]; the
  rule is about references, not about where Chrome puts them: no array, closure or
  stored job keeps a captured part after the upload is acknowledged.
- Batch making stays one clip at a time with the existing pacing (20 captures an
  hour), so a batch never stacks captures in memory.
- Card clips upload only sound and a picture (D-080 to D-085), a tenth of a video's
  bytes; the picker shows each clip's size so the budget is never a surprise.

### 8.2 Custody: hot and cold

- **Hot** clips are local: due within the hot horizon (48 hours), or within the
  catch-up window, or currently running.
- **Cold** clips are remote: pinned on SnipShare with a ticket.
- **Admission.** A new schedule is accepted only if the clips due in any 48 hour
  stretch fit the budget, counting its own size (the server tells the page the size
  before the ticket is minted). If not, the hot horizon for that stretch shrinks to
  the latest point that fits, and the clip stays cold until then. **Correction,
  2026-10-31 review:** the example that stood here (six clips in six hours exceeding
  1 GB) was wrong. The encoder targets about 10 MB per clip whatever its length
  (`render.py`, D-071's 10 MiB composer ceiling); 90 clips take about 944 MB and
  30 about 315 MB. See Section 14, UC1.
- **Write path.** The fetch reuses `fetchClip` (Range, stall timeout, resume) but
  keeps what arrived in IndexedDB every 2 MB, as `download()` does, so a fetch
  interrupted by a worker stop resumes rather than restarts, and the worker never
  holds more than a few MB of a clip in flight. SHA-256 is computed once at the end
  and kept.
- **Before writing:** `navigator.storage.estimate()` must show room for twice the
  clip; otherwise the furthest-due hot clip that has a valid ticket is demoted (its
  local copy deleted, kept remote) and the estimate asked again. A
  `QuotaExceededError` does the same, once, then fails the fetch with a plain message.
- **Persistence.** The extension asks for `unlimitedStorage`, so its data is not
  evicted under disk pressure and the 1 GB budget is not cut by Chrome's per origin
  quota [Unverified for an extension loaded from a folder; Phase 0 checks with
  `navigator.storage.persisted()` and a 1 GB write]. The budget is ours, not
  Chrome's: it is enforced whatever Chrome would allow.
- **Integrity.** The hash is checked at prewarm and before a run. A mismatch with a
  valid ticket is refetched; without one, the schedule fails with "The scheduled clip
  is damaged. Schedule it again from the page".
- **Handing over to WhatsApp.** `whatsappLoadOnce` today reads the whole clip into
  an array and sends it in 512 KB base64 messages. Unchanged in size, but the array
  is released as each slice is sent, so the clip is held once, not three times.
- **Clean up.** Local copies go when a run ends (`sent`, `prepared` once the composer
  closes) or when Undo's 10 seconds pass after a cancel; the ticket is deleted at the
  same moment, which unpins the server copy. `sweepBlobs` learns to leave `sched:`
  keys to `schedule.js`, and the sweep deletes `sched:` keys no schedule names.

### 8.3 The custody loop

Every 15 minute sweep and after every queue change:

1. Compute the hot set from due times, the horizon and the budget.
2. Demote local clips no longer hot whose tickets are valid (furthest first).
3. Promote cold clips now hot: fetch, nearest due first, one at a time, with backoff
   (1, 5, 15, 60 minutes).
4. A clip still cold 2 hours before due is a problem now: notify ("Your 6:00 PM
   Status could not come down from SnipShare. Check your connection") and keep
   trying until prewarm, which fails the run if it is still not local.

## 9. Architecture

```
SnipShare page (hosted.js)                 extension service worker (sw.js)
--------------------------                 --------------------------------
picker, Up next (3 rows)  -- port -->     queue.js: pure queue operations
queue.html: the table,       (commands       (retime, shift, spread,
                              + a watch       pause/resume, spacing, limits)
options page: settings         subscription)  schedule.js: store, revisions, alarms,
                                              state machine, catch-up, quiet hours
                                           custody.js: hot/cold, budget, fetch,
                                              demote, hash, tickets
                                           place.js: ladder S0..S5, focus guard,
                                              activity guard, discard guard
                                           whatsapp.js (page world): event driven,
                                              confirmed send
chrome.alarms: prewarm:<id>, due:<id>, sched-sweep
chrome.notifications: outcomes, asks, the 60 s send warning
server (portal.py, accounts.py, retention.py): tickets, pins, per person limits
```

### Table SC-7: what changes where

| File | Change |
|---|---|
| `src/queue.js` (new) | pure functions over a list of schedules: insert and retime with 90 s spacing, sorted by due time, shift, spread, pause and resume with the overdue choices, quiet hours, limits. No Chrome APIs, so Node tests cover it completely |
| `src/schedule.js` (new) | store with revisions in `chrome.storage.local`, alarm reconcile, the state machine (Table SC-8), catch-up, the subscription broadcast |
| `src/custody.js` (new) | hot set, admission, fetch with resume into IndexedDB, demotion, hash, ticket deletion, storage estimate and quota handling |
| `src/place.js` (new) | the ladder, focus guard, activity guard (`chrome.idle`), discard guard, the per machine record |
| `src/sw.js` | `importScripts` the four; port commands `schedule`, `queue` (read), `queue-change` (one operation and its revision), `post-now`, `watch`; WhatsApp one-at-a-time rule shared; `whatsappLoadOnce` takes a placement and releases slices as sent; `hello` adds `features: ["schedule"]`; `sweepBlobs` leaves `sched:` keys |
| `src/sw.js`, capture | the capture ladder C0 to C3 (FR-21) beside today's `pageCapture`, chosen by a `placement` the page passes; **From the editor** keeps C2 |
| `src/recorder.js` | drops a video's stored fragments when told the capture is done (if Phase 0 shows it does not already) |
| `src/whatsapp.js` | `waitFor` on `MutationObserver`, `tick`, caption read back, the send step and its confirmation |
| `src/wa-bridge.js` | carries `tick` |
| `src/manifest.json` | `notifications`, `idle`, `unlimitedStorage`; version 2.1.0 |
| `src/popup.*` | the settings (**Bring WhatsApp forward when needed**, quiet hours, default gap for Add to queue), **Test quiet mode** |
| `src/test/queue.test.js`, `schedule.test.js`, `custody.test.js` (new) | Section 11 |
| `wastatus/accounts.py` | purpose `schedule` with its own lifetime and no sliding; the pins table; per person limits (clips a day, upload a day, pending schedules, budget, pinned bytes) with defaults and admin overrides |
| `wastatus/retention.py` | `prune` skips pinned stems and does not count them towards `keep` |
| `wastatus/portal.py` | `POST` and `DELETE /api/schedule-ticket`; `/api/v1/clip` accepts a schedule ticket; the page's config carries the person's scheduling limits and the minimum extension version; the admin page edits per person limits; outcome codes accepted by the failure report |
| `src/queue.html`, `src/queue.css`, `src/queue-page.js` (new) | the schedule table (FR-3 to FR-8): time and caption edited in place, re-sorting with focus kept, the bulk bar, pause and resume, history, the budget meter, the watch subscription; cards below 720 px |
| `wastatus/pages/making.js` (new) | From a link: the **Schedule from links** form, the **Paste many** parser and its preview, and the making loop that takes plans from the extension and drives grant, capture, render and ticket one at a time, resuming whenever a SnipShare page is open |
| `wastatus/pages/hosted.js`, its HTML and CSS | Schedule and Add to queue, the picker, a compact Up next and the **Scheduled** link that asks the extension to open `queue.html`; gated on `features` and the person's switch (D7) |
| `tests/test_accounts.py`, `tests/test_portal.py`, `tests/test_retention.py`, `tests/test_extension.py` | Section 11 |

### Table SC-8: a schedule's states

| State | Entered when | Next |
|---|---|---|
| `planned` | From a link: queued, not yet made | `making`, `missed` (unmade at due time), `cancelled` |
| `making` | the page is capturing and rendering it | `holding`, `unmade` |
| `unmade` | making failed; the reason is stored | `making` (Try again), `planned` (Edit), `cancelled`, `missed` |
| `holding` | saved; first fetch or ticket check under way | `scheduled`, or removed with the error on the page |
| `scheduled` | ready; custody local or remote | `prewarmed`, `running` (Post now), `paused`, `cancelled`, `missed` |
| `paused` | the queue was paused | `scheduled`, `running`, `missed` by the resume choice |
| `prewarmed` | prewarm passed or reported a problem | `running`, `cancelled` |
| `waiting` | the person is using WhatsApp, or another load is in flight | `running`, `asked` after 10 minutes |
| `running` | a rung is being tried; the rung is stored; locked against edits | `prepared`, `sending`, `asked`, `failed` |
| `sending` | the 60 s warning shown, then Send pressed once | `sent`, `unconfirmed`, `cancelled` (warning's Cancel) |
| `asked` | fallback notification shown | `running` (pressed), `cancelled`, `missed` after 24 hours |
| `prepared` | composer loaded, action prepare | `done` when the composer closes |
| `sent` | Send pressed and confirmed | `done` |
| `unconfirmed` | Send may have been pressed, not confirmed | `done` once the person says; never retried |
| `failed` | every rung and the fallback failed, or the clip was lost | `scheduled` (Change time), `cancelled` |
| `missed` | past the catch-up window, or into quiet hours | `running` (Post now), `scheduled` (Change time), `cancelled` |
| `cancelled`, `done` | | removed with its clip and ticket after the undo or 24 hours |

On a worker start, a `running` prepare is run again from the top (the open composer
check refuses a second load); a `sending` whose Send may have been pressed becomes
`unconfirmed`.

### Table SC-15: the stored schedule

| Field | Example | Note |
|---|---|---|
| `id`, `rev` | `s_7f3a`, 4 | random id; revision for FR-17 |
| `created`, `due` | epoch ms | due is an instant; zones and daylight saving cannot move it |
| `zone` | `Asia/Kolkata` | for showing it only |
| `stem`, `name`, `caption`, `mode` | | the clip's, frozen at save; caption editable until `running` |
| `size`, `sha256` | | size from the server at save; hash once local |
| `custody` | `local`, `remote`, `fetching` | with `fetched` bytes for resume |
| `ticket`, `ticketEnds` | | the schedule ticket, kept in `chrome.storage.local` only |
| `action` | `prepare` or `send` | |
| `catchUp` | 1800000 | ms |
| `state`, `rung`, `attempts`, `error`, `outcome` | | per Table SC-8 |
| `origin` | `editor` or `link` | Section 1b |
| `plan` | `{url, videoId, start, end, mode}` | From a link only; kept after making, for **Edit in SnipShare** |
| `looked` | `false` | From a link: set when the person previews it |
| `repeat` | `null` | reserved |

## 10. Decisions

### Table SC-9: taken by the owner, 2026-10-31T00:14:05+05:30

| # | Question | Answer |
|---|---|---|
| D1 | May a scheduled run press Send? | yes, as a per schedule choice, default prepare, confirm-once; built after the prepare-only runs have proved out |
| D2 | Where do schedules live? | in the browser only; the server holds tickets and pins, not the queue |
| D3 | Default when quiet rungs fail and the person is active | ask by notification; bring forward is a setting |
| D4 | Catch-up window | 30 minutes, editable per schedule |
| D5 | Limits | up to 30 days ahead, pending raised to match; 1 GB of held clips for the owner |
| D6 | Capture now or at the due time | now |
| D7 | Who gets it first | the owner and a per person pilot switch |

### Table SC-10: taken by the owner, 2026-10-31T00:23:09+05:30

| # | Question | Answer |
|---|---|---|
| SC-D8 | How far-off clips are kept | ~~schedule tickets and pins~~ **superseded 2026-10-31T00:45:04+05:30 by UC1: every scheduled clip is kept on the computer; Section 7 and the cold half of Section 8 are dropped; D-090 and D-101 stand unamended** |
| SC-D9 | The server's per person limits under batching | per person limits the admin sets; defaults unchanged; the owner at 30 clips and 1.5 GB of upload a day |
| SC-D10 | Held clip budget | the owner 1 GB, others 400 MB, both editable per person |
| SC-D11 | Pending limit | the owner 90, others 30 |
| SC-D12 | How the order changes | **the owner's design, replacing both options offered:** the queue is a table on an extension page; a post's time is edited in its own row and the table re-sorts by time. Time is the only order; no dragging, no slots (FR-3, FR-5) |
| SC-D13 | Quiet hours | on, 23:00 to 07:00; stops catch-ups and warns at scheduling |
| SC-D14 | The 60 s warning before a send | on |
| S3 | A **Swap times** action | none; two time edits do it (owner, 2026-10-31T00:28:04+05:30) |

### Table SC-17: taken by the owner, 2026-10-31T00:31:32+05:30

| # | Question | Answer |
|---|---|---|
| SC-D15 | When is a clip from a link made? | soon after it is queued, driven by the page with the person's own session; no new credential |
| SC-D16 | May a clip nobody has looked at be sent? | ~~only if the person ticked **Send without my review**~~ **superseded 2026-10-31T00:45:04+05:30 by UC2: not in this version; a clip from a link is sent only after it has been previewed, consent bound to that clip and account** |
| SC-D17 | What a clip from a link looks like | plain, SnipShare's defaults; saved looks may come later as their own phase |
| SC-D18 | How links are entered | a form row per post plus **Paste many**, previewed before queueing |
| SC-D19 | Capturing a batch without taking focus | the capture ladder, C1 first, subject to Phase 0 |

## 11. Tests

### Table SC-11: what proves it

| Layer | Tests |
|---|---|
| `queue.js` (Node) | retiming re-sorts and keeps the row's identity; shift and spread preview equals result; 90 s spacing on insert and after every operation; pause and each resume choice; quiet hours; limits; every operation is undone exactly by its Undo |
| `schedule.js` (Node, fake clock and store) | a worker killed at every transition resumes correctly; a plan unmade at its due time becomes missed; an unseen clip is never sent unless its row says so; `sending` at start becomes `unconfirmed`, never sent again; alarms rebuilt after loss; daylight saving and zone change leave `due` fixed; revision conflicts refused |
| making (Node, `making.js` parser) | Paste many: every reasonable form of link, time and window; the preview equals what is queued; bad lines kept with what is missing |
| `custody.js` (Node, fake fetch and store) | hot set under a full budget; admission refusal and its message; demotion order; resume of a fetch at every 2 MB; hash mismatch; injected `QuotaExceededError`; orphaned `sched:` keys swept |
| `media.test.js` | unchanged; still passes |
| pytest | a schedule ticket reads its clip and nothing else, ends on time, is not slid, dies on suspension, is deleted by itself; pinned clips survive `prune` and do not count towards 10; pinned bytes capped; per person limits read and edited by the admin only; `/api/v1/clip` still refuses a wrong scope |
| `tests/test_extension.py` | the new permissions; Send and caption selectors still match `post.py` |
| By hand, Phase 0 and Phase 9 | Table SC-12 |

## 12. Implementation plan

Each phase ends with a strict audit of that phase before the next starts, as for the
extension and SnipShare. Days are [Inference], one maintainer with an agent.

### Phase 0: the spike that could change the plan (1.5 days)

In the owner's Chrome on Linux, against the owner's WhatsApp Web, never pressing
Send:

1. A scratch `whatsapp.js` with `waitFor` and `tick`; for S0, S1 and S2: does the
   composer load and the caption go in, how long, did focus or the active tab move.
   S0 with WhatsApp hidden for 1, 10 and 60 minutes.
2. S2 on the owner's window manager: is `focused: false` honoured; does moving the
   WhatsApp tab into the helper window and back reload it or trigger "Use here".
3. `chrome.alarms` lateness: awake, after a 10 minute suspend, after a Chrome restart.
4. Whether `background` keeps Chrome alive with no windows open.
5. Storage: `unlimitedStorage` loaded from a folder; `navigator.storage.persisted()`
   and `estimate()`; a 1 GB write and read back in IndexedDB; time to hash 60 MB in
   the worker.
6. Memory: the YouTube tab and the worker before, during and after a 90 s 1080p
   capture and its upload; whether `recorder.js` lets go of the fragments.
7. Whether a press on a notification's button may bring a window forward.
8. Capture in an unfocused helper window (C1): is the player given its media, does
   the read finish, did focus move; ten captures in a row.
9. (Answered at the 2026-10-31 review: the composition is kept with each clip;
   see FR-24.)

**Exit:** Table SC-12 written here with every result; the ladder's order fixed; if no
quiet rung works, the plan is put back to the owner before Phase 1.

### Phase 1: the queue and schedules that keep (3 days)

`queue.js` and `schedule.js` with their Node tests; alarms and reconcile; catch-up,
missed, quiet hours, pause and resume; revisions and the watch broadcast. A run ends
in a stub.

### Phase 2: the server side (2 days)

Schedule tickets, pins, `prune` honouring pins, per person limits and their admin
edit, the page config carrying the person's figures, `/api/v1/clip` accepting a
ticket. Pytest for every rule in Table SC-11. DECISIONS.md entries amending D-090
and D-101 for the ticket.

### Phase 3: custody (2.5 days)

`custody.js`: admission, hot set, fetch with resume, demotion, hash, quota handling,
ticket deletion, sweeping. The `schedule` command end to end against a local
SnipShare. Node tests.

### Phase 4: capture and transit hygiene (1 day)

From Phase 0's memory findings: release in `recorder.js`, references dropped in the
page and popup capture paths, the popup path's capture keys deleted on the upload's
acknowledgement, `whatsappLoadOnce` releasing slices. Measured again.

### Phase 5: the quiet runner (3 days)

`place.js` in Phase 0's order with the focus, activity and discard guards and the
per machine record; `whatsapp.js` event driven, worker keeping time; prewarm;
outcomes. The manual **Load into WhatsApp** keeps bringing the tab forward.

### Phase 6: fallback and notifications (1 day)

S3, S4, S5; a notification per outcome with **Post now** where it applies; the badge
counting schedules that need the person; the settings.

### Phase 7: the queue on the page and the options page (4 days)

**Schedule** and **Add to queue** beside the primary; the picker; the schedule table in `queue.html` grouped by
day with custody and budget; time and caption edited in place with re-sorting;
the bulk bar with previews; **Post next now**; pause and the resume choices; history;
Undo everywhere it applies; empty states; the delete warning for a scheduled clip;
the admin page's per person limits. Gated on `features` and the pilot switch.
Checked at 360 px and desktop, by keyboard alone, in both themes, then walked end to
end as a first time person.

### Phase 7b: From a link (3.5 days)

The **Schedule from links** form and **Paste many** with its preview; plans stored
in the extension (`planned`, `making`, `unmade`); `making.js` driving grant, capture,
render and ticket one at a time, pausing with no SnipShare page and resuming; the
capture ladder C0 to C3; the **Made** column, **Not looked at**, **Preview** and the
batch notification; failures and their reasons; **Edit in SnipShare** for both kinds
of row; SC-D16's rule enforced in the runner, not only in the page. Tested with a
batch of ten links of every kind (card, video, ads, a private one, a live one, a
removed one) while the owner works in other windows.

### Phase 8: confirmed send (1.5 days)

The send step, the 60 s warning, the confirmation, `unconfirmed`, the per schedule
choice with its consequence written beside it. First on a WhatsApp account with a
tiny audience, as D-002 asked of any send automation, then on the owner's, only after
a week of prepare-only runs without a missed or misplaced one.

### Phase 9: end to end and the bad cases (2.5 days)

The Phase 0 matrix on the built extension, plus: suspend through a due time, Chrome
restarted, WhatsApp signed out, tab discarded, typing in WhatsApp at the due time, a
manual load in flight, two due together, the extension reloaded mid-run and
mid-fetch, a server restart mid-fetch, a ticket expired, the person suspended, the
budget full, a 30 day queue of mixed clips, retiming and shift across the hot horizon,
pause through three due times and each resume choice, a batch from links made with every SnipShare tab closed half way. Results as Table SC-13.

### Phase 10: audit, documents, release (1.5 days)

Master audit against Table SC-3. Documents in the same session, each timestamped:
DECISIONS.md, this file's "As built", docs/extension.md Table EX-3, API.md,
DATA_MODEL.md (pins, limits, the stored schedule), SECURITY.md (the ticket),
LIMITATIONS.md, TESTING.md, OBSERVABILITY.md (outcome codes, pinned bytes),
CHANGELOG.md, ROADMAP.md, TASKS.md. Then the build, the key scan required before any
publish, and `scripts/deploy.sh`, which is the owner's to run.

**Total:** about 27 to 29 working days [Inference], Phase 7b included.

## 13. Risks

### Table SC-14: risks, options and recommendation

| Risk | Options | Recommended |
|---|---|---|
| No quiet rung works on Linux | a. ship S3 and S4 only; b. S2 with a window appearing unfocused; c. drop the feature | from Phase 0; b if `focused: false` holds, else a |
| WhatsApp changes its composer or Send | a. selectors shared with `post.py`, tested for drift; b. plus a daily prewarm-only self check that notifies early | a, then b if breakages recur |
| An unwanted or duplicate post | a. per schedule choice, send once, confirm; b. plus the 60 s warning | a and b |
| A ticket leaks | a. scope one clip, end at due plus a day, die with suspension, hashed at rest; b. bind it to the extension's id as well, through `Origin` | a, and b if Phase 2 shows the header is reliable |
| The server's disk fills with pins | a. pinned bytes per person capped; b. plus an alert at 80 percent, beside the existing disk alert | a and b |
| The browser's storage is evicted or full | a. `unlimitedStorage`, our own budget, demotion; b. hold everything remote and fetch at prewarm only | a; b is the automatic fallback when the budget is exceeded |
| People expect it to run with the laptop shut | a. say so in the picker ("Keep Chrome open and the computer awake"); b. a server side sender, which would need an unofficial WhatsApp client | a; b is refused by D-002 |

## 14. Review, 2026-10-31T00:42:08+05:30

A full plan review (strategy, design, engineering) run with the gstack `/autoplan`
pipeline. Each phase had two independent outside reviewers, a Claude subagent with
no prior context and OpenAI Codex, plus the primary review; their findings were
checked against the code before being accepted. Developer experience review was
skipped: the feature is for people posting Statuses, not for developers. Nothing in
Sections 1 to 13 is changed by this section except the three factual corrections
marked in place (FR-24, 8.2, Phase 0 item 9). Where an amendment below conflicts with
earlier text, the amendment wins. **Approved by the owner at the gate, 2026-10-31T00:45:04+05:30:** UC1,
UC2 and UC3 as recommended, and T1 to T4 as recommended. Every table in this
section is therefore part of the plan.

### Table SC-R1: what the four voices agreed on

| Question | Claude subagents | Codex | Consensus |
|---|---|---|---|
| Premises valid | no: storage, account risk, reliability metric | no: storage, demand, account risk | **confirmed: three premises wrong or unproven** |
| Right problem, right scope | scope bundles three products | scope bundles three products | **confirmed: release in stages** |
| Remote custody needed | no, clips are about 10 MB | no, 90 clips fit in about 944 MB | **confirmed: local custody** |
| Unseen auto-send safe to ship now | no | no, consent not bound to content or account | **confirmed** |
| Send confirmation correct | (not raised) | no, breaks D-071's `ack` rule | **flagged; verified in AGENTS.md and `post.py`** |
| Architecture sound | two critical, eight high | three critical, five high | **confirmed: fixable, listed below** |
| Information hierarchy | inverted: nothing says what needs me | serves the developer | **confirmed** |
| States specified | many missing | experience between states missing | **confirmed** |
| Phone push alternative | worth a Phase 0 probe | (not raised) | single voice: taste |
| The idle rung S3 | (not raised) | idle is not absence | single voice: taste |

### User challenges (both models say a direction you set should change)

**UC1. Keep every scheduled clip on the computer; drop schedule tickets and pins
(reverses SC-D8).** You chose tickets and pins on my figure that 1 GB holds "roughly
25 to 50 video clips". That figure was wrong: the encoder aims for about 10 MB per
clip, under WhatsApp's 10 MiB composer ceiling, so your 90 clips take about 944 MB
and anyone else's 30 about 315 MB, both inside the budgets you set. Tickets and pins
need a long-lived credential (amending D-090 and D-101), a pin table, changes to
three deletion paths, orphan cleanup and a race-free cap: about 4 to 5 days and the
largest new attack surface in the plan. What we might be missing: a clip larger than
10 MB (the budget is a target, not a hard cap, so admission must check the real
size), and recovery if the browser profile is lost, which local custody does not
offer. If we are wrong: a lost profile loses its queue, which is true of schedules
already (SC-D2).

**UC2. No sending of a clip nobody has looked at, in this version (narrows
SC-D16).** Both strategy voices see unseen batches sent on a timer as the point
where driving the real WhatsApp client stops looking like a person (D-002 calls the
account the one asset), and the engineering voice found the consent is not bound to
the clip or the account: a replaced clip or a different signed-in account would
inherit an old "Send without my review". Recommended: a clip from a link is sent
only after it has been previewed; consent is tied to that clip's revision and the
WhatsApp account seen at scheduling; replacing the clip resets the row to Prepare.
What we might be missing: you may want true hands-off volume, which this delays. If
we are wrong: From a link runs as Prepare until you look, which costs a press per
post.

**UC3. Ship in three releases with gates, not one 27 to 29 day build.** Both strategy
voices and the Codex design voice independently say the plan bundles three products
(batch making, the queue, unattended sending) and postpones the test of the central
promise. Recommended order:
- **Release 1, about 15 days:** Phase 0; From the editor; local custody; the queue
  table with time editing, Post now, Cancel and Pause; the quiet runner and
  fallback; Prepare. Then confirmed Send, behind D-071's `ack`, for schedules from
  the editor, after a week of Prepare runs.
- **Release 2, about 5 days:** From a link, with leases and the worker driving the
  making (Table SC-R2, E2 and E3).
- **Release 3, about 2 days:** the bulk bar (shift, spread, many at once).

What we might be missing: you asked for all of it, and the bulk controls were your
explicit request. If we are wrong: batch making arrives about three weeks later than
in the single build. [Inference: the day counts.]

### Taste decisions (recommended answer applied unless you say otherwise)

| # | Decision | Recommended | The other choice |
|---|---|---|---|
| T1 | The idle rung S3 takes focus when nobody has typed for 60 s | make S3 an opt-in setting beside S5; "idle" is not "away" (someone watching a film) | keep S3 on by default: more runs complete unattended |
| T2 | Notifications | only what needs the person, plus one daily summary of what went out; per-post notices as a setting | one notification per outcome, as written: more reassurance, many more interruptions |
| T3 | A phone route | add a Phase 0 probe: at the due time a notification on the phone, one tap shares the clip to My status [Unverified that the share reaches My status] | leave the phone out of this plan |
| T4 | What "due time" means | the time it goes out: prewarm loads the composer two minutes early and the 60 s warning runs before the due time | processing starts at the due time, as written: posts land a minute or two late |

### Table SC-R2: amendments decided by the review (mechanical, apply with the plan)

| # | Amendment | Found by |
|---|---|---|
| E1 | `chrome.alarms.onAlarm` dispatches by name; `wastatus` keeps `run()`. One `next` alarm for the nearest event instead of two per schedule; rebuilt on every wake. A test proves a schedule alarm never calls `drive()` (`sw.js:1285`) | eng, Claude |
| E2 | Batch making is driven by the worker, which keeps time; the SnipShare page only answers session calls (grant, render, ticket) over the open port, because a hidden page's timer chain (`app.js:1112`) is throttled. Phase 0 measures a hidden SnipShare tab at 10 and 60 minutes | eng, Claude; primary |
| E3 | A plan is claimed with an expiring lease (plan, tab, until), renewed while making, freed on disconnect; a 409 from `/api/grant` (`portal.py:1088`) means wait | eng, both |
| E4 | Scheduled runs have their own pacing key, so the page's 10 loads an hour (`sw.js:1163`) cannot refuse them | eng, Claude |
| E5 | Clips are fetched into numbered parts (`sched:<id>:part:<n>`), joined only when handed to WhatsApp; `download()`'s rewrite of the whole growing file is not copied (`sw.js:585`) | eng, Claude |
| E6 | Size checked against the server's figure; the hash is checked once at prewarm, not three times | eng, Claude |
| E7 | `whatsappLoadOnce` reads one slice at a time and waits for `wa-bridge.js` to acknowledge it before the next (`sw.js:687`) | eng, Claude |
| E8 | Every queue mutation runs through one promise chain, as `paced()` does; IndexedDB writes wait for the transaction to complete, not the request (`sw.js:70`) | eng, both |
| E9 | `pressAt` is stored and awaited just before Send; only a run with `pressAt` set can become `unconfirmed`. Countdown and send intent are separate states. No replay after an uncertain side effect | eng, both |
| E10 | **Sent means WhatsApp's own `ack`, read as `post.py` does (D-071, AGENTS.md).** A closed composer or a new local entry is never proof. The extension gains the `post.py` ack reader | eng, Codex; verified |
| E11 | Waits and the Undo window are stored deadlines (`waitUntil`, `deleteAfter`) carried out on alarms and on wake, never only by a page timer | eng, Claude |
| E12 | `sweepBlobs` learns to leave `sched:` keys in the first phase, before any is written (`sw.js:92`) | eng, Claude |
| E13 | `contextMenus` added to the manifest list; `background` only if Phase 0 shows it helps | eng, Claude |
| E14 | A send kill switch: the extension reads a small public flag from the site at prewarm, and when sending is off every run prepares instead | primary |
| E15 | A local run log (last 200 runs, codes and timings, no video or caption) viewable from the queue, so a fault reported weeks later can be reconstructed | primary |
| E16 | The account a run will post as is recorded at scheduling and checked at the run; a different account turns the run into Prepare and asks | eng, Codex |
| E17 | Reliability is measured two ways: of runs on an awake machine, and of every schedule made, sleeping machines included; Prepare and Send separately; the Release 1 gate is a real week of the owner's use | strategy, both |
| E18 | Release 2 pilot users are named before it is switched on for anyone but the owner, and From a link volume is capped per day with attribution kept on every post (D-103's copyright reasoning) | strategy, Claude |
| E19 | A Windows or Mac machine joins the Phase 0 matrix before any pilot user is switched on | strategy, Claude |
| E20 | The daily prewarm-only self check (Table SC-14, row 2, option b) ships with the runner, not after a breakage | strategy, Claude |

### Table SC-R3: design amendments (structural, apply with the plan)

| # | Amendment |
|---|---|
| U1 | `queue.html` opens on **Needs you** (missed, unconfirmed, asked, failed, could not make, not looked at, signed out), one line and one action each, its count also on the toolbar badge; then **Next up** with a countdown; then the table |
| U2 | One **Status** column with plain words, its colour and its one action, mapped from every state in Table SC-8; where the clip is kept is a muted second line; storage detail behind a disclosure; **Pause queue** beside **Post next now** |
| U3 | Labels say what will happen: **Send now**, **Prepare now**; Undo never offered once a send has been pressed |
| U4 | Bulk Post now sends Send rows 90 s apart and lines Prepare rows up one at a time, each after the previous composer closes; the bar says "3 will send, 2 will wait for you" |
| U5 | The 60 s warning's button is **Hold** (back to the queue, Undo offered); **Cancel post** exists only in the table |
| U6 | A states table per surface (picker, Up next, queue, bulk bar, From a link form): loading, empty, error, partial, success, extension missing or too old, pilot switch off, offline while editing; partial bulk results apply what they can and keep the rest with the reason |
| U7 | The first schedule offers **Try quiet mode now (nothing is sent)**; the queue footer says whether quiet posting works on this computer; the picker says "Keep Chrome open and the computer awake" |
| U8 | Each row shows one action chosen by its state; the rest in a labelled **More** menu; cards below 720 px show status, time, caption, action, details folded |
| U9 | Presets that have passed are hidden; a preset in quiet hours carries the warning; "Open SnipShare to move this" is a button |
| U10 | On a phone: no Schedule buttons, one line "Scheduling works in Chrome on a computer with the extension"; Up next readable |
| U11 | Measurable accessibility: every target at least 40 px (the owner's rule), text contrast at least 4.5:1, focus returned after every dialog, re-sorts announced politely, reduced motion respected |
| U12 | One toast at a time holding the latest change; Undo scrolls to the restored row |

### Error and rescue registry (new code paths)

| Code path | What can go wrong | Rescued how | The person sees |
|---|---|---|---|
| alarm dispatch | unknown or stale alarm name | ignored, logged, next alarm rebuilt | nothing |
| clip fetch into parts | stall, 404, 5xx, quota full, size mismatch | resume from last part; quota: refuse with room needed; 404: row fails | "Could not bring the clip down" with Try again |
| prewarm | WhatsApp signed out, tab discarded, wrong account | reload in background; notify; Prepare on wrong account | Needs you: "WhatsApp is signed out" |
| quiet ladder | every rung fails, focus moved | focus restored, rung recorded, fall back (S4) | Needs you: "Ready. Post it now" |
| composer load | selector moved, composer open, timeout | stop, record WhatsApp's menu | Needs you with today's Load |
| send | countdown held, worker stops before or after press, no `ack` | before `pressAt`: back to queue; after: `unconfirmed`, never retried | "Check WhatsApp: we cannot tell whether it went" |
| making (Release 2) | lease lost, 409 busy, capture or render failed, daily limit | wait on 409; lease expiry frees; failure stored with reason | "Could not make: private video" with Try again |
| queue mutation | revision conflict, two writers | serialised chain; stale edit refused | the current queue, the edit kept for retry |

### Failure modes with a critical gap before this review

| Failure | Gap | Closed by |
|---|---|---|
| A schedule alarm wakes the old job loop and the scheduler never runs | silent, untested | E1 |
| A refused Status reported as sent | silent, against D-071 | E10 |
| Two tabs make the same plan; daily clips spent twice | silent | E3 |
| A hidden SnipShare tab stalls a batch | silent | E2 |
| Prepare runs replayed after a crash | duplicate composer, no test | E9 |

### Not in scope (deferred)

- Remote custody (tickets and pins), unless UC1 is rejected.
- Sending unseen clips, until UC2's consent rules and a month of Release 1 data exist.
- Recurring schedules and saved looks (Table SC-2, SC-D17).
- Queue export and recovery after a lost profile (Codex strategy finding 8); revisit if Release 1 users lose a queue.

### What already exists and is reused

| Need | Existing code |
|---|---|
| Fetch a clip with Range and stall timeout | `fetchClip` in `sw.js` |
| Restore a clip's composition into the editor | `<stem>.json` from `pipeline.py`, `job` in `serve.py`, `recall` in `app.js` |
| Read WhatsApp's `ack` for a Status | `post.py` (around line 1025 to 1170) |
| Composer steps and their selectors | `whatsapp.js`, kept in step with `post.py` by `tests/test_extension.py` |
| Serialised work with persisted state | `paced()` and the job loop in `sw.js` |
| Grants, capture, render from the page | `hosted.js`, `/api/grant`, `/api/render` |

### Dream state delta

Today a clip goes out when the person presses Load. After Release 1, clips made with
care go out at their time, quietly, confirmed by WhatsApp. After Release 2, a list of
links becomes a week of clips the person looks over. The twelve month ideal the
reviewers point to is a phone route too (T3), so a Status can go out with the laptop
shut; nothing in this plan blocks it.

### Decision audit trail

| # | Phase | Decision | Class | Principle |
|---|---|---|---|---|
| 1 | intake | Developer experience review skipped: no developer-facing product | mechanical | P3 |
| 2 | intake | Review written into this file in the repository's own style; restore point kept outside the repository, not as a comment naming a home folder | mechanical | P5 |
| 3 | CEO | Mode: selective expansion | mechanical | default |
| 4 | CEO | Storage premise wrong: UC1 | user challenge | P1 |
| 5 | CEO | Unseen auto-send: UC2 | user challenge | P1 |
| 6 | CEO | Staged releases: UC3 | user challenge | P6 |
| 7 | CEO | Phone probe: T3 | taste | P1 |
| 8 | CEO | E17 to E20 | mechanical | P1 |
| 9 | design | U1 to U12 | mechanical (structural) | P5, P1 |
| 10 | design | S3 opt-in: T1; notifications: T2; due time: T4 | taste | P5 |
| 11 | eng | E1 to E13, E16 | mechanical | P5 |
| 12 | eng | E10 send confirmation by `ack` | mechanical (standing rule) | P4 |
| 13 | eng | E14 kill switch, E15 run log | mechanical | P1 |
| 14 | all | Corrections to FR-24, 8.2 and Phase 0 item 9 applied in place | mechanical | honesty |

Test plan written outside the repository, in the gstack project folder, dated
2026-10-31.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---|---|---|
| CEO Review | `/plan-ceo-review` via `/autoplan` | Scope and strategy | 1 | clean | 3 user challenges, 1 taste decision, 4 amendments |
| Codex Review | `codex exec`, three phases | Independent second opinion | 3 | done | strategy 8, design 7, eng 9 findings |
| Eng Review | `/plan-eng-review` via `/autoplan` | Architecture and tests (required) | 1 | clean | 22 issues, 5 critical gaps, all with amendments |
| Design Review | `/plan-design-review` via `/autoplan` | UI and UX gaps | 1 | clean | 14 issues, 12 structural amendments, 3 taste decisions |
| DX Review | `/plan-devex-review` | Developer experience | 0 | skipped | no developer-facing scope |

- **CROSS-MODEL:** Claude and Codex agreed on the storage premise, staged releases,
  unseen auto-send, the inverted hierarchy and missing states; Codex alone caught the
  `ack` rule, the account binding and replay after a crash.
- **VERDICT:** CEO + ENG + DESIGN CLEARED, 2026-10-31T00:45:04+05:30: the owner approved UC1 to UC3 and
  T1 to T4 as recommended. Ready for Phase 0 of Release 1 when the owner asks.

NO UNRESOLVED DECISIONS


## 15. As built, Release 1, 2026-10-31T01:51:25+05:30

Section 14 overrides Sections 1 to 13 where they conflict, and this section overrides
both where the build differs. Branch `feat/scheduling-r1`, uncommitted when this was
written. The build contract named the modules and the commands; this describes the
behaviour, not the lines. Decisions taken while building are D-105.

**Table SC-18: what was built**

| Piece | What it does |
|---|---|
| `src/queue.js` | pure rules, no Chrome: order by time, 90 second spacing, 2 minute minimum lead and 30 days ahead, quiet hours (a warning, never a refusal), the limits check, catch up (run if no more than 30 minutes late and outside quiet hours, else missed), resume's three choices, the next wake, Undo snapshots and the plain words and tone for each state. Also `shift` and `spread`, unused until Release 3 |
| `src/custody.js` | fetches a scheduled clip into IndexedDB in numbered parts of at most 2 MiB (`sched:<id>:part:<n>`), one ranged request per part, resumable after the worker stops, size checked against the server's figure before anything is kept, SHA-256 kept, room for twice the clip checked, a full disk reported plainly, orphan parts swept. No tickets, no pins, no change to what the server holds |
| `src/place.js` | the placement ladder. S0 an existing WhatsApp tab untouched, S1 a new background tab, S2 an unfocused helper window, S3 only when the person allows taking focus while idle, S4 asks by notification, S5 only when the person allows bringing WhatsApp forward. A focus guard around every rung, a discard guard, an activity guard (the person using WhatsApp, or a composer already open, means wait). `placeStats` records per machine which rung worked. `testQuiet` is the queue page's test |
| `src/schedule.js` | the stored queue and its states, one promise chain for every change, revisions so a stale edit is refused (`conflict`), the `sched-next` alarm and a 15 minute `sched-sweep` alarm rebuilt on every wake, prewarm, waiting and retry, notifications and the badge, history, the run log, settings and limits, the commands of both ports |
| `src/sw.js` | loads the four modules, answers the external port (`schedule`, `queue-peek`, `open-queue`, `hello` with `features`), the internal port `snipshare-queue`, the toolbar menu item, alarm dispatch by name, and the scheduled pacing key. `sweepBlobs` leaves every `sched:` key alone |
| `src/whatsapp.js`, `src/wa-bridge.js` | the composer steps now wait on page changes rather than sleeping, return the caption read back, never press Send, and the bridge acknowledges every chunk before the next is sent |
| `src/queue.html`, `queue.css`, `queue-page.js` | the queue page (Section 4's table): Needs you, Next up, the table with in row time and caption edits, Cancel with Undo, Pause and Resume, history, the budget, the quiet test, the run log. Mobile first |
| `src/popup.*` | the scheduling settings, saved as each control changes, and **Open the queue** |
| `wastatus/web/*`, `wastatus/pages/hosted.*` | **Schedule** and **Add to queue** beside **Load into WhatsApp** (which stays primary), the picker with presets and the time in words, **Up next**, the Scheduled link, and one line on a phone. Hidden in the local tool |
| `wastatus/accounts.py`, `portal.py`, `pages/admin.js` | per person limits and the pilot switch, `scheduling` in `/api/state`, `POST /api/admin/limits`, the admin page's editor, the report source `schedule` |

Every run is **Prepare**: the clip is put in WhatsApp's composer and the person presses
Send. The `action` field exists and is always `"prepare"`; any other value is refused.

**Table SC-19: where the build differs from the plan, and why**

| Plan | Built | Why |
|---|---|---|
| T2: only what needs the person is notified, success is silent bar a daily summary | every prepared clip is notified, "in WhatsApp, press Send", with **Show WhatsApp**, and counts as Needs you on the badge | every prepared clip needs a press in this release, and an open composer blocks the next run |
| WhatsApp's tab kept from discarding while prewarmed | and while a clip is prepared and unsent, up to 6 hours | a discarded tab destroys the unsent composer |
| Schedule saved on one press | the same two press stale preview check as Load and Download | a preview out of step with the settings must not be scheduled unseen |
| **Post next now** (U3) | **Prepare next now**, and the row buttons are secondary | it posts nothing; one primary button per screen |
| Scheduled runs share the page's pacing | their own key, 40 an hour (E4) | ten loads an hour must not starve a queue |
| Limits carried "in the page config or the account answer" | `/api/state` carries `scheduling: {enabled, pending, budget_bytes}`; the page tells the extension, which enforces them | the state answer is the one the page already reads |
| Quiet mode Phase 0 first | built before Phase 0; the ladder's order is learned per machine from `placeStats` | the order cannot be known until it is tried on the owner's machine |
| Sending in the plan's Phase 8 | not built | AGENTS.md Never, D-084, and the plan's own gate of a week of Prepare runs |
| From a link and the bulk bar | not built | Releases 2 and 3 |

**Table SC-20: what is unverified**

| Claim | Status |
|---|---|
| Phase 0 on the owner's Chrome | [Unverified] not run. Every Chrome behaviour this plan labelled unverified still is: a composer in a hidden tab, a tab that has never been shown (S1), `focused: false` on Linux (S2), moving a tab between windows without WhatsApp's "Use here", and typing a caption in an unfocused tab. **Try quiet mode now (nothing is sent)** on the queue page is the owner's test |
| Anything in real WhatsApp Web | [Unverified] nothing was run against it |
| Resume's three choices, end to end | [Unverified] covered by unit tests only |
| The alarm rebuild on every wake, end to end | [Unverified] covered by unit tests only |
| The queue as a whole | verified in a headless Chromium with the real unpacked extension and a local hosted server in a scratch profile: real clips scheduled, retimed, captions edited, cancelled and undone, paused and resumed across two open queue pages, and a due schedule run with WhatsApp blocked, which failed cleanly to "signed out" with a notification and no change of focus |
| Unit tests | 152 Node tests pass; the full pytest suite passes with 1569 passed and 7 skipped (2026-10-31T09:55:06+05:30, after the independent review's fixes) |

### Added 2026-10-31T11:35:09+05:30: the account section and the capture fix

Built on the same branch after the table above. **Scheduled Statuses in the account
page** frames the extension's queue page (`queue.html?embed=1`), gated on
`scheduling.enabled` in `/api/account`: one queue UI rather than a second, decided in
D-106; states and messages in docs/account-page.md, Tables AP-8 and AP-9; the
manifest's `web_accessible_resources` and the `frame-src` entry in SECURITY.md; Up
next's **Scheduled** now goes to `/account#scheduled`. **A capture** no longer waits on
a YouTube tab that cannot answer (IN-14, docs/extension.md). Extension version stays
2.1.0.

**Table SC-21: what is unverified, added**

| Claim | Status |
|---|---|
| The account section | driven in headless Chromium with the unpacked extension at 360 and 1280 pixels, light and dark; the "extension too old" state is [Unverified], not driven in a browser |
| The capture's tab rule | covered by `src/test/capture.test.js` with fake tabs; [Unverified] against the owner's own open tabs |
| Unit tests | 156 Node tests pass; pytest 1593 passed, 7 skipped (counted 2026-10-31 after commit d917694) |

Next: Phase 0 by the owner, then a week of the owner's use of Prepare, then confirmed
Send (Phase 8), Release 2 and Release 3, in that order unless the owner says otherwise.
