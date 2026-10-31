# The account page

Asked **2026-10-25T09:03:57+05:30** by the owner, from a screenshot of the Account
panel on the tool page: a separate page that the account icon opens, in two columns,
with Profile, History, API keys and Feedback sections and a sign-out button, so a
person can keep a GIPHY and a KLIPY key at once and switch between them, or search
both together. Also asked the same day: rename the extension's folder to `src/`.

## What was wrong with the panel

The panel unfolded across the top of the tool page, full width, and pushed the work
down the screen. It held one GIF key at a time, so adding KLIPY threw GIPHY away. It
showed a pasted key in plain text. It had no history, no usage, and no way to say
anything to the operator but a problem.

## Table AP-1: the page

`/account`, signed in only. Two columns from 900 pixels up: the sections listed on
the left, the chosen one on the right. On a phone the list becomes a row of tabs
under the heading, one tap away, and the section fills the screen. One section at
a time, named in the address (`/account#keys`), so Back works and a link can point
at one.

| Section | What it holds | What it does |
|---|---|---|
| Profile | name (editable), the Google address (read only), status, member since, last signed in | Save the name; Sign out; Admin, for the admin |
| History | today against the limits, and when they reset in the person's own time; the last 14 days; every clip made in the last 90 days, with its video, window, look, when, and whether it worked | Watch the original at the window's start; Download or Open in SnipShare while the file is still kept (the newest 10) |
| API keys | a card each for GIPHY and KLIPY: added or not, the last four characters, when; where to get one | Add or replace (masked input, checked with one search first), Remove; **Search with**: GIPHY, KLIPY or both mixed together |
| Feedback | a short form: what kind (an idea, a problem, a question, something else), the words, and, for a problem, the last failure the tool page saw | Send: an email to the operator, with the person's address as the reply-to so the operator can answer from their inbox |
| Extension | whether this browser has the extension, its version, whether WhatsApp Web is signed in here | Get or update the extension; what it can reach and its hourly pace |
| Privacy and data | what is kept, for how long, the link to `/privacy` | Delete my account, with the address typed to confirm |

A **Sign out** button sits at the foot of the section list, always visible, and
**Back to SnipShare** at its head.

## Table AP-2: GIF keys, both at once

| Part | Change |
|---|---|
| `gifs.py` | each result carries its provider and is named `provider-id`, so two services' ids cannot collide; `search` reads the person's choice, `giphy`, `klipy` or `both`; **both** asks the two at once, in parallel, and interleaves the answers, keeping what one gave if the other failed |
| The local tool | the same: with both keys in `.env`, `WASTATUS_GIF_PROVIDER=both` works, and the shelf offers **Both** beside the two |
| Credits | each provider's mark stays: GIPHY's "Powered by GIPHY", KLIPY's required "Search KLIPY" in the box; with both, "Search KLIPY and GIPHY" and both marks |
| `accounts.py` | `gif_keys` keyed by person and provider (migrated in place from one key per person); the person's choice kept in `people.gif_source` |
| The tool page | the shelf's service choice (already there for the local tool) appears when a person has two keys, and switching it saves the choice |

## Table AP-3: what else changes

| Part | Change |
|---|---|
| The tool page | the Account chip opens a menu (since 2026-10-31T12:23:37+05:30, D-107): Profile, History, Scheduled Statuses when scheduling is on, Extension, Admin for admins, Sign out; the panel is gone; a clip can be opened from History with `/app?clip=<name>` |
| `accounts.py` | a `history` table, one row per finished or failed render, 90 days, gone with the account; the name can be changed |
| `notify.email` | takes a reply-to, used only for feedback |
| `/api/report` | failures only; words go through Feedback |
| Privacy page | says the history and feedback are kept and how |
| `extension/` | renamed `src/`, everywhere it is named |

**On "Resend CLI behind it":** the server sends through Resend's HTTP API, which is
what the CLI calls; the container has no Node to run the CLI, and the key and the
sending domain are the same ones. Nothing changes for the operator.

## Table AP-4: decisions taken without asking, each reversible

| Question | Taken | Why |
|---|---|---|
| Account page in the same tab or a new one | same tab; the form is remembered | the familiar pattern, and Back returns |
| One section at a time, or all stacked | one at a time | short screens on a phone, and an address per section |
| Default GIF source with two keys | both | the greater range is the point of adding the second |
| How long History is kept | 90 days, like inactive clips | long enough to find last month's clip, short enough to keep little |
| Feedback to Chat as well as mail | mail only | the Chat space is for things that need doing now |

## As built, 2026-10-25T09:21:14+05:30

As planned, with these settled in the building:

| Planned | Built | Why |
|---|---|---|
| KLIPY key from "docs.klipy.com" | the steps link to KLIPY's partner dashboard, whose API keys page makes the key | checked: the docs site has no key, the dashboard does |
| Sign out at the foot of the list | at the foot of the list on a computer; at the very end of the page on a phone | on a phone the list is a row of tabs, and a button between the tabs and the section they open was in the way |
| The shelf's service switch | on a wide screen beside GIF search, as the local tool always had; on a phone, asked by the owner the same morning, a compact segmented row of its own under Drawings and GIFs, the three choices splitting the width | a phone's shelf row has no room beside the two chips, so it takes its own line |
| The picture's fade in | removed in both modes, D-094 | WhatsApp shows the first frame before play |

## Second pass: designed as one system, 2026-10-25T12:55:26+05:30

The owner marked up four screens (Profile, API keys, Feedback, Admin) and asked for
them, and every other page, to be designed the way an experienced Google designer
would. The first pass built the right sections; this one makes them behave like a
settings product people already know.

### Table AP-5: the principles, and where each lands

| Principle | What it means here |
|---|---|
| Read first, edit in place | A setting is a row: what it is, its value, and a pencil. Pressing the pencil turns the row into its field with Save and Cancel; Enter saves, Escape cancels. No form sits open waiting to be filled |
| One primary action per screen | Feedback's Send, Admin's Approve; everything else is a quieter button or a text action |
| Confirm by result, not by dialog | A saved change says so in a short message at the foot of the screen (a snackbar); a destructive one asks in place, in the row it affects |
| The same controls everywhere | Segmented buttons for a choice of three or fewer, chips for filters, rows for settings, cards for groups, a menu behind ⋯ for rare actions |
| Status in words and colour | Connected, Not added, Pending, Approved, Suspended: a pill, never colour alone |
| Theme anywhere | System, Light or Dark, in the header of every page and in Profile, one choice shared with the tool page |
| Mobile first | Every row works at 360 pixels: value under label, actions as a row of their own, tap targets 40 pixels or more |

### Table AP-6: the screens

| Screen | Becomes |
|---|---|
| Profile | A header with the Google photo (or initial), name, email and role. **Basic info**: Name (pencil), Email (managed by Google). **Preferences**: Theme (System, Light, Dark). |
| Sign-in and security (new section) | Signs in with Google; member since; last seen; **where you are signed in**: each browser with its kind and when last used, this one marked, and **Sign out everywhere else** |
| API keys | A row per service: Connected with the key's last four and the date, or Not added. **Replace** (pencil) opens the field in place; **Remove** asks in place. **Add key** opens the field with the three steps beside it. **Search with** is one segmented control |
| Feedback | Name (filled, editable), Email (from Google, locked), Type as chips, **Subject**, Message, **Screenshots** (drop or choose, up to 3 images, previewed, each removable), the last failure for a problem. Sent: the form gives way to a confirmation with "Send another" |
| Admin | A **date range** at the top (Today, 7 days, 30 days, or two dates) that every number below follows: people active, clips, failed, uploaded, new requests. **Requests** as cards with Approve and Decline side by side. **People** as a searchable list with status filters, each row with its pill, last seen, clips in range and a ⋯ menu (Suspend, Let back in, Delete). **Add person** is a button that opens one compact row: email, name, Add. Usage and Failures follow the range |
| Every page | The header carries the theme chooser, and, signed in, the person's photo as the way to the account |

### Table AP-7: what the server keeps that it did not

| New | Why | Said where |
|---|---|---|
| The Google photo's address | the profile and the header show the person's own face | privacy page |
| A session's browser kind and system, coarse ("Chrome on Linux") | so a person can recognise and end a session they do not know | privacy page |
| Screenshots attached to feedback | the operator sees the problem; they are re-encoded (no metadata), mailed, and not kept on the server | privacy page |

### As built, 2026-10-25T13:12:05+05:30

As Tables AP-5 to AP-7, checked at 360 and 1280 pixels in light and dark, and driven
in a headless browser: the name edited in place and confirmed, the theme switched,
a key row opened for Replace and for Remove and closed again, the feedback form
refusing a missing subject, and two sessions listed. One thing found by looking:
the shared script must load at the top of each page, before the page's own, or the
photo, the theme and the messages are missing.

**Password, asked 2026-10-25, then withdrawn:** SnipShare keeps no password; sign-in
is Google's. Rows linking to Google's password and recovery pages were added and then
removed at the owner's word the same hour: advice about a Google password from a
third-party site confuses more than it helps. Signing in with Google is the whole
story, and the page says only that.

## Scheduled Statuses in the account, 2026-10-31T11:21:01+05:30

Asked by the owner as "Scheduled Videos": the queue, seen and managed from the
account page's menu. Named **Scheduled Statuses**, the product's word for what is
posted and the queue page's own title; the menu's other labels are short nouns
("History", "Extension"), so the product's term reads as one of them. The queue lives
only in the extension (docs/scheduling.md, SC-D2) and its page already exists, so the
lead's decision was to frame that page here rather than draw the table a second time.

### Table AP-8: the section

| Part | What it does |
|---|---|
| Menu and section | `#scheduled`, after History, offered only when the person's pilot switch is on (`scheduling.enabled` in `/api/account`). Off, the link stays hidden and `/account#scheduled` opens Profile |
| Loading | skeleton rows until the extension answers and the frame has said its height |
| Extension missing | "Your queue is kept by the SnipShare extension...", **Get the extension** (`/install`) |
| Too old, or no `schedule` feature | the version, and **Update the extension** (`/install`) |
| Not answering in 5 s | reload, or **Update the extension** |
| Phone | one line, "Scheduling works in Chrome on a computer with the extension.", nothing to press |
| Ready | `chrome-extension://<id>/queue.html?embed=1&theme=<system, light or dark>` in a frame titled "Your Scheduled Statuses", as tall as its content; **Open in its own tab** beside the heading |
| Frame silent for 6 s | the frame is removed; **Open the queue in its own tab** asks the extension (`open-queue`) |
| Up next on the tool page | **Scheduled** goes to `/account#scheduled` in the same tab, as the Account menu's items do; the toast after scheduling still opens the queue's own tab |

### Table AP-9: what crosses between the page and the frame

| Direction | Message | Checked |
|---|---|---|
| frame to page | `{snipshareQueueHeight}` after every change of layout | sent to `CONFIG.site`'s origin only; taken only from `chrome-extension://<id>` and from this frame's window; clamped to 120 to 20000 pixels |
| page to frame | `{snipshareTheme}` when the theme changes, no reload | sent to the extension's origin only; taken only from the site's origin and from the frame's parent |
| page to frame | `{snipshareShown: {top, bottom}}` on scroll and resize | the same; the frame puts its toast in the part on screen, since a frame as tall as its content would otherwise show it at its foot, out of sight |

The frame also refuses to draw or connect when any ancestor is not the site
(`location.ancestorOrigins`). The manifest exposes `queue.html`, `queue.css`,
`queue.js` and `queue-page.js` as web accessible to the local addresses, which
`scripts/build_extension.py` replaces with the site alone, as for
`externally_connectable`. The account page's policy adds `chrome-extension://<id>` to
`frame-src` when the configured id has Chrome's shape (32 letters a to p), and changes
nothing else.

### As built, 2026-10-31T11:21:01+05:30

Driven in headless Chromium with the unpacked extension in a scratch profile against a
local hosted server: one scheduled row shown at 360 and 1280 pixels in light and dark,
no sideways scroll, the theme followed without a reload, the time moved an hour by
keyboard alone (Tab into the frame, F2, arrows, Enter) with the toast on screen, a
message from the wrong origin ignored, the fallback after 6 s opening the queue's tab,
the missing extension and phone states, and the standalone queue page unchanged.

Found in the building:

- The frame's first height is sent on a timer, not `requestAnimationFrame`: Chrome
  runs no frames for a cross-origin frame that is hidden or has no height, which is
  how the page holds it until that first height arrives.
- With `chrome-extension://<id>` taken back out of `frame-src`, the frame still loaded:
  Chromium lets extension resources past a page's policy. The `frame-src` entry is
  kept as the explicit statement of what the page frames. [Inference] other Chromium
  builds behave the same; only the bundled Chromium was tried.
- The queue's row buttons sat high in their outline at table width, in the standalone
  page too; centred.
