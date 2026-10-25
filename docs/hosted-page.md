# The full page, hosted, with sign-up and Google sign-in

Plan written **2026-10-24T23:33:03+05:30**, revised **2026-10-24T23:43:52+05:30** with
the owner's answers, approved **2026-10-24T23:57:30+05:30** with Table HP-1's
recommendations, 10 clips and 500 MB a day, a self-contained Docker project, the
repository kept fit to publish, and failure tracking and reporting planned.
**Built and live 2026-10-25T02:06:06+05:30**, as SnipShare: see "As built" at the
end, TASKS.md T-068 and DECISIONS.md D-087 to D-093.

## What a person sees

1. **Getting the extension.** The site's `/install` explains the one
   requirement up front: *making a clip needs desktop Chrome with the extension*. It
   offers the extension as a download and shows the four steps to load it.
2. **First visit: Request access.** A short form: name, email, what they will use it
   for, and how they heard of it (optional). **Sign up with Google** fills name and
   email from their Google account and proves the email is theirs; the plain form is
   accepted too, but access is only ever granted to a Google sign-in with that email.
   A Cloudflare Turnstile check stops bots, invisibly for people.
3. **The owner hears at once:** an email to the owner's support address and a message in the
   "Downtime Notifications" Google Chat space, each with the details and a one-press
   **Approve** link (owner sign-in required) and the equivalent command.
4. **Approved:** next visit, **Sign in with Google** and they are in for 30 days. Not
   yet approved: the page says the request is with the owner.
5. **Using it:** the page they would know from the local tool. Paste a link and times,
   **Make the clip**; the extension reads the window in their browser (a YouTube tab
   shows for a second or two), the renderer makes it, it appears in the frame.
   **Load into WhatsApp**; they press Send.

The owner's own Google address is on the list from the start, as the **admin**: the only
account that can approve, see usage, and suspend.

## Where "it needs the extension" is said

| Place | What it says, and what it does |
|---|---|
| `/install` | the requirement first, then the download and steps |
| Request access form | a line above the form, and a tick box "I use desktop Chrome" (not blocking; it sets expectations) |
| Sign-in screen | the same line under the button |
| The page, extension missing | a banner across the top with **Get the extension**; **Make the clip** and **Load into WhatsApp** greyed with the reason beside them, never silently dead |
| The page, extension too old | the banner names the version needed |
| The page on a phone or tablet | "Making a clip needs desktop Chrome. Your recent clips are here to watch and save." Recent strip stays usable |
| Another desktop browser | "Open this in Chrome with the extension" |
| The approval message the owner sends on | the requirement, so the person is not surprised |
| README, LOCAL_SETUP | the same, for people reading the repo |

## Answers to the owner's two questions

- **This repository was private** on GitHub at the time (`PalWorks/whatsapp-status-maker`,
  which stays private with the full history). Since 2026-10-25 it is published as a
  fresh copy, `PalWorks/snipshare-whatsapp-status-maker` (D-099). The page's code is readable by anyone, as
  any website's is; nothing secret is in it.
- **A Google Cloud project already exists for this repository**, created 2026-08-31
  for the Google Sheet record and owned by the owner's Google account. The plan uses it
  for the sign-in client unless the owner prefers a separate one (Table HP-1). Its id
  and owner are in the private operations notes.

## The public page at the site's root

Asked 2026-10-25: the root of the site becomes public, so it should explain the
project and be on good terms with YouTube, Google and Meta without cowering.

**The stance: plain, accurate, respectful, not apologetic.** The design already does
the things platforms care about; the page says so as facts, not as pleas.

- **What it is:** a way to share the part of a song or talk you love, as a vertical
  Status clip, **with the link back to the original in every clip**. It exists to send
  people to the creator, not to replace them.
- **What it is not, stated as facts:** not a downloader (it never saves a whole video,
  only up to 90 seconds you choose, rendered into a new frame with the source named);
  it does not skip or block ads (the capture waits for them to play); it refuses
  protected (DRM) video outright; it never posts for you (you press Send in WhatsApp);
  no bulk, scheduled or unattended use, and limits that keep it at a person's pace.
- **Experimental and invite-only:** a personal project, offered as is, with daily
  limits, that may change or stop. Access by request.
- **Not affiliated** with YouTube, Google, WhatsApp or Meta; their names are used only
  to say what it works with, and belong to them.
- **Rights and takedowns:** you are responsible for what you share; a clear contact
  for any creator or rights holder, and clips removed on request.

### Layout, mobile first

1. **Top:** the name, one line on what it does, **Request access** (primary) and
   **Sign in**, and "Experimental, by invitation".
2. **How it works, in three steps** with small frames: pick the moment on YouTube; make
   the clip; post it to your Status yourself, the link travels with it.
3. **Made to send people to the source:** the facts list above, as short cards.
4. **What you need:** desktop Chrome with the extension (link to `/install`), WhatsApp
   Web to post. Said here, before anyone signs up.
5. **Questions:** Is this a downloader? Does it post for me? Is it affiliated with
   YouTube or WhatsApp? What do you keep about me? I made the video and want a clip
   removed.
6. **Footer:** Privacy, Terms, Contact (the support address), the status page, and the
   non-affiliation line.

Plus `/install`, `/privacy` and `/terms`, written plainly (the owner reviews them;
they are not legal advice), which Google's sign-in needs before it is published.

### Two additions to the build that the page's promises depend on

- **The extension refuses protected video.** It detects an encrypted stream (EME, or an
  encrypted header) and says "This video is protected and cannot be clipped",
  instead of producing a broken clip.
- **The product's name.** "WhatsApp Status clip" puts Meta's trademark in the
  product's name, which its brand guidelines do not allow. A neutral name, with
  "for WhatsApp Status" as a description, avoids the one thing most likely to draw a
  complaint (Table HP-1).

## The shape

```
extension icon --> https://<the site>/app            the page, served by the renderer
                     |  Turnstile + Request access form --> Resend --> the owner's address
                     |                                  --> Google Chat webhook
                     |  Sign in with Google --> session cookie (HttpOnly, 30 days)
                     |  /api/...  the page's own API, per person, on the renderer
                     |  "capture this window" --> extension (externally_connectable)
                     v
                   extension: walks the YouTube tab, uploads with a 15 minute grant
                     |
                   POST /api/render (upload ids) --> pipeline.produce(captured)
                     v
                   clip in the frame; Load into WhatsApp --> extension
```

The page is served by the renderer rather than packed into the extension, so images
and video need no token in their URLs (D-081), one copy of the page serves the local
tool and the hosted one, and a page fix ships with a deploy.

## Contained: one Docker project, nothing shared

Decided 2026-10-24: everything this project runs on the server lives in its own
Compose project, so it can be edited, rebuilt, restarted or removed without touching
anything else on the host.

- **Its own Compose project and network** (`wastatus`), its own named volumes, its own
  resource limits (3 CPUs, 3 GB), no host ports.
- **Its own front door: a Cloudflare Tunnel container** in the same project. Today the
  renderer is reached through the host's shared Caddy, which meant editing a file
  every other site depends on and reloading it; the tunnel ends that. The Caddy block
  and the DNS `A` record are removed once the tunnel answers, and nothing of this
  project remains in shared configuration.
- **Its own state:** the people, requests, sessions and usage in SQLite inside its
  volume; a nightly backup into a second volume of its own, seven kept.
- **Its own scheduled work** (janitor, digest, backups) inside its container, not in
  the host's crontab.
- **The one outside dependency kept:** Uptime Kuma checks the public address, which
  touches nothing of ours. Its monitor row is the only thing outside the project, and
  it is recorded in the private operations notes (below).
- **Removal is one command**, `docker compose down -v`, plus deleting the tunnel.

## Fit to publish: what goes in the repository and what never does

The repository was prepared on 2026-08-20 to be made public (T-022), and was
published on 2026-10-25 as a fresh single-commit copy rather than with its history
(D-099, T-070). So the public and the private are kept apart by design, not by a
clean-up later.

### Table HP-3: the demarcation

| In the repository, safe to publish | Kept out, in a private operations repository and the server's `.env` |
|---|---|
| all code, the extension, tests, generic docs | the real domain, the server's name and address, what else runs on it |
| `deploy/compose.yml`, `Dockerfile`, a tunnel template, all reading settings from the environment | the tunnel token, Resend and Turnstile keys, the Google client secret, the Chat webhook, the encryption key |
| `.env.example` naming every setting, with no values | the real `.env`, mode 600 on the server |
| `src/config.example.js` with `https://renderer.example.com` | `src/config.js` (git-ignored), generated at build with the real address, and the built extension offered at `/install` |
| `example.com` addresses and placeholder names in every example | the owner's emails, the admin list, the Uptime Kuma notes, DEPLOYMENT's real values |

- **A private operations repository** (`whatsapp-status-ops`, private, under PalWorks)
  holds the real DEPLOYMENT notes and values, and no keys: those live only in the
  server's `.env`. The public repository's [DEPLOYMENT.md](../DEPLOYMENT.md) is the
  generic recipe.
- **A test that fails the build** when a tracked file contains a public IPv4 address,
  a home directory path, an email outside `example.com`, or anything on a private deny
  list (a git-ignored file of the owner's own strings, read when present).
- **Before the switch was flipped**, a secrets and personal-data scan (gitleaks) of
  the exact tree published. The history was not rewritten but left behind: the
  public copy starts from one commit (D-099).
- **Already in the repository and to be moved out in this work:** the production
  domain in the extension's defaults and manifest, `deploy/Caddyfile.wastatus`, and the
  host description in DEPLOYMENT.md (the server's alias and address were already kept
  out on 2026-10-24).

## Phase 0: tests that could change the plan

| Test | If it fails |
|---|---|
| A YouTube tab opened in front, then sent behind, still loads and can be walked | keep it in front for the few seconds of the capture |
| The page can message the extension and get a few MB back | relay through a content script the extension puts in the page |
| A Google ID token from the page verifies with `google-auth` | none expected |
| Resend sends from the verified sending subdomain, and the Chat webhook posts | use the other verified domain |

### Phase 0 results, 2026-10-25T00:00:30+05:30

| Test | Result |
|---|---|
| YouTube tab in front, then behind | in front for **0.5 s** until the player was ready, then sent behind (`hidden`); a 30 second video window captured behind in **8.1 s**. The flash is half a second |
| Page to extension messaging | `externally_connectable` from an allowed origin: **8 MB back in 0.09 s**, the sender's origin reported to the extension |
| Resend and Chat | a test email from the sending subdomain **delivered** to the owner's support address; the Downtime Notifications webhook answered **200** |
| Google ID token | **verified**, 2026-10-25T00:23:03+05:30: a sign-in from a throwaway page on `localhost:8790` checked by `google.oauth2.id_token` against the new client: signature, issuer `accounts.google.com`, audience matching, email verified |

## Phase 1: access

- **Google sign-in client** in the project above: type *Web application*, origin
  the site's own, scopes `openid email profile` only. Those are not
  sensitive scopes, so the consent screen can be published without Google's review;
  it needs a privacy policy and terms, served at `/privacy` and `/terms`.
- **Requests:** stored per email with the form's answers and status `pending`,
  `approved`, `declined` or `suspended`. Approve and decline from the link (admin
  session) or `wastatus hosted user approve|decline|suspend|list EMAIL`.
- **Sessions:** random, stored hashed, `HttpOnly`, `Secure`, `SameSite=Lax`, 30
  days. Suspending someone ends theirs at once.
- **CSRF:** cookie **and** an `Origin` of the site **and** a custom header on every
  change.
- **Grants:** short-lived, single-purpose bearer tokens the page hands the extension
  (upload one capture; fetch one clip). The extension never holds a session.
- **Notifications:** Resend, with a new sending-only API key limited to the verified
  sending subdomain, in the server's environment;
  the Chat webhook from the same space Uptime Kuma uses. Both keys in the server's
  `.env`, mode 600, outside the image and outside git.
- **Nothing is emailed to the person who signed up.** Mail goes only to the owner's
  own address, so the domain's reputation cannot be hurt by a typo or a bot's address.

## Phase 2: the page's API on the renderer, per person

`serve.py` already answers every call the page makes; it is made reusable, not
copied. `serve.App` becomes a per-person **workspace** under `/data/users/<id>/` (clips,
tasks, uploaded stickers, GIF key); the routes are shared; a hosted subclass supplies
authorisation (session, not the per-process token) and which workspace a request
reaches.

| Call | Local | Hosted |
|---|---|---|
| `/api/render` | yt-dlp | the capture's upload ids, `pipeline.Captured` |
| `/api/words` | `fetch.probe` | the title the extension read, cleaned by the same `title_and_channel` |
| `/api/post` | CDP | the extension, in the person's own WhatsApp Web |
| `/api/state` | ffmpeg, provider, WhatsApp, debug port | renderer, extension present and its version, WhatsApp tab signed in, quota left today |
| `/api/browser`, `/api/controls` | Chrome, WhatsApp's menu | not offered |
| Stickers | library and uploads | library in the volume; uploads per person, capped |
| GIFs | `.env` key | the person's own key, or none (below) |
| media and previews | token in the URL | the session cookie |

## Phase 3: abuse protection, monitoring and analytics

What could overload the server, or get something blacklisted, and what stops it.

### Table HP-2: risks

| Risk | Stopped by |
|---|---|
| Bots filling the sign-up form | Cloudflare Turnstile; a per-address limit of 5 requests an hour; one request per email, ever, and a typed email's standing never told back (D-100) |
| One person hogging the renderer | per person: one render at a time, **10 clips a day**, **500 MB of uploads a day**; across everybody: the queue of 8, and a cap of 60 renders an hour |
| A file built to attack ffmpeg | only approved people can upload; the container's limits (D-081) |
| YouTube flagging a person's account or address | the server never talks to YouTube, so it cannot be blacklisted there. The extension paces captures to a person's: at most **20 an hour per browser**, never in parallel, never unattended |
| WhatsApp (Meta) flagging an account | the extension only ever fills the composer when a person presses the button, never sends, and is limited to **10 loads an hour** |
| The mail domain's reputation | mail only to the owner's own address; Resend's own limits |
| Google sign-in being restricted | basic scopes only, a published privacy policy and terms, no other Google APIs |
| The disk filling | the janitor (an hour), per person retention of 10 clips, a free-space floor that refuses new work |
| Cloudflare treating a burst as an attack | the rate limits above keep traffic human; one free Cloudflare rate limiting rule on `/api/session` and `/api/signup` as a second line |

### What is watched, and who hears

- **Usage, on the server**, nothing sent anywhere: per person per day, clips made,
  failures, upload bytes, render seconds. An **Admin** panel on the page for the admin
  account: people, requests, usage, suspend.
- **Alerts to the Downtime Notifications space:** a new access request; anyone
  reaching 80 percent of a daily limit; the hourly render cap reached; failures
  above 20 percent in an hour; disk under 5 GB; plus Uptime Kuma's existing monitor.
- **A daily digest** to the same space at 08:30 IST: yesterday's people, clips,
  failures and the busiest hour.
- **Product analytics, optional (Table HP-1):** PostHog, which the owner already uses,
  for the funnel (visited, requested access, approved, first clip, clips per week)
  and where captures fail. Events carry a hashed person id and the phase, never the
  video, the email or the words.

## Phase 3b: failures and the downside, tracked and reported

What usually goes wrong in a project like this, how it is noticed, and who is told.

### Table HP-4: what is watched

| What goes wrong | How it is noticed | Who hears |
|---|---|---|
| YouTube changes its player and captures start failing | the extension reports every failed capture (phase, reason, extension and Chrome versions, never the video), and the server alerts when capture failures pass 20 percent in an hour or three people fail in a row | Chat, at once |
| WhatsApp renames a control and loading fails | the load failure reports the step and the labels WhatsApp offered, which is exactly what a fix needs | Chat, at once, with those labels |
| The renderer errors | every exception logged with the job, and alerted once per kind per hour so a storm is one message | Chat |
| The renderer is down or slow | Uptime Kuma, and a queue wait over five minutes | Chat |
| Someone abuses it | quota hits, Turnstile failures, a burst of failed sign-ins, suspensions | Chat, and the daily digest |
| The disk or memory runs out | free disk under 5 GB; the container's memory near its limit | Chat |
| A certificate or a domain lapses | Cloudflare manages the certificate; Uptime Kuma already warns on expiry | Chat |
| A dependency has a known hole | a monthly rebuild on fresh base images and `pip-audit`, reported in the digest | digest |
| Data is lost | the nightly backup, and a monthly restore test reported in the digest | digest |
| A copyright or abuse complaint | a published contact (support@ on `/terms`), a takedown that deletes a clip and can suspend the person, recorded | the owner, by mail |
| Someone wants their data gone | **Delete my account** on the page: sessions, clips, keys and usage, at once; inactive accounts' clips removed after 90 days | recorded |

- **Every report is sanitized before it leaves the browser:** a phase, a reason code,
  versions. No video id, no title, no email, no words. Said in the privacy policy.
- **An Incidents list** in the Admin panel, and in the daily digest: what failed, how
  often, since when, which version.
- **A "Report a problem" link** on the page, which sends the person's words and the
  last failure's code to support@ by Resend, rate limited.

## Phase 4: people's own GIF keys

- Settings on the page: **Your GIPHY or KLIPY key**, with a link to where to get one
  free. Checked once against the provider before it is kept.
- Kept on the server encrypted (Fernet, from `cryptography`, already installed), with a
  key from the server's `.env`; used only for that person's searches; never logged;
  **Remove my key** deletes it.
- Without a key, the GIF tab says how to add one instead of not being there.
- **The owner's own keys** stay in the local `.env` (git-ignored already, checked) and,
  if wanted for the admin account only, the server's `.env`. Never in the image, never
  in git, never sent to the page.

## Phase 5: the page

One page for both, told by `/api/state` whether it is hosted and whether the extension
is there. Hosted it adds: Request access and Sign in screens; the extension banner and
greyed buttons from the table above; capture before render with its progress line;
Load into WhatsApp and Fetch the words through the extension; GIF key settings; the
Admin panel; and quota left today, shown quietly beside **Make the clip**.

## Phase 6: the extension

The icon opens the page, or brings an open one forward; the popup is kept, switched
off. `externally_connectable` for the site only: version; capture this window (reuse
an open tab of that video, or open one in front, let it load, step it back, walk it,
close it); load this clip into WhatsApp; read the video's words. The pacing limits in
Table HP-2 live here, where they can be enforced per browser.

## Phase 7: production, end to end, audits, documents

Sign-in client, keys, allowlist, OpenMoji in the volume, Caddy's body limit raised for
the sticker upload route only, Turnstile site, the Cloudflare rule, the extension
download at `/install`, deploy. Then in the owner's Chrome: request access with a
second Google account, the notification arriving by mail and in Chat, approve, sign in,
a card and a video from a link, stickers, a GIF with that person's own key, placed text,
Load into WhatsApp and close, the second person unable to see the first's clips, a
limit reached, suspend, sign out. Bad network and Stop again. Independent audit, all
findings fixed, every document swept.

## Table HP-1: decisions for the owner

| Question | Options | Recommendation |
|---|---|---|
| Google Cloud project | reuse the project's existing Google Cloud project, already under the owner's account; or a new one | reuse it: same owner, same product, one place for its keys |
| Approval | the owner approves each request; or anyone who signs up with Google is in at once | the owner approves: it is the abuse protection that costs nothing |
| Daily limits per person | 30 clips, 2 GB of uploads | **decided: 10 clips and 500 MB a day** |
| PostHog product analytics | yes, with the privacy rules above; or server usage only | server usage only at first; add PostHog once there are ten people |
| The admin's own GIF key on the server | yes; or the admin adds a key like everyone else | like everyone else: one path, nothing special to keep secret on the server |
| The YouTube tab that shows for a second | accept; or ask people to open the video first | accept, if Phase 0 shows it steps back |
| The product's name (asked 2026-10-25) | keep "WhatsApp Status clip"; or a neutral name with "for WhatsApp Status" as its description | **decided: SnipShare**, subtitled "Status Maker for WhatsApp, from YouTube videos". The marks appear only in the subtitle and descriptions, saying what it works with, never as the name |
| The protected video claim (2026-10-25) | build the check now; or keep the claim and build the check later | **decided: later**, once there are a few people. The page says "Protected (DRM) video cannot be clipped", which is true today because encrypted media cannot be decoded; it does not claim the extension refuses it |
| The public page's tone (asked 2026-10-25) | cautious and apologetic; or plain and factual | plain and factual: the design already does what platforms care about, and saying it as fact reads as confident, not defensive |

## Size

Five to six working days, in seven audited phases plus the containment and
publishing work, roughly 3,500 lines across the server, the page and the extension,
plus tests.

## As built, 2026-10-25T02:06:06+05:30

Every phase above was built, audited twice and verified, locally and in production.
Where the build differs from the plan, the build is right and this says why.

| Planned | Built | Why |
|---|---|---|
| The page's API under `/api/...` on the renderer | `portal.SiteHandler`: the renderer's handler and the local page's in one, the person's `Workspace` (`serve.App` in `users/<id>/`) bound per request | every route the page uses is the one the local tool already tests |
| CSRF: cookie, `Origin` and a custom header | the custom header carries a value derived from the session, so the page's own `X-Wastatus-Token` is the CSRF value and `app.js` did not change | one mechanism for both pages |
| Grants: upload one capture; fetch one clip | the upload grant also resolves the window exactly as the render will, and slides forward while an upload keeps sending | a slow line must not be cut off by the clock; the extension must read the window the server will cut |
| Extension: reuse an open tab, or open one in front, step back | as planned, and the opened tab is muted | Phase 0's half second of sound |
| Popup kept, switched off | it is the extension's options page | a token holder can still reach it |
| `src/config.example.js` and a git-ignored `config.js` | `src/config.js` is committed, naming a local copy; the build replaces it | an unpacked load of the repository works as it is |
| A private operations repository | the owner's notes hold the real values; see the closing report | |
| Product analytics | server usage only | Table HP-1 |

### Table HP-5: measured, 2026-10-25

| Case | Result |
|---|---|
| Card, 15 s, throwaway Chrome, local server | 18 to 26 s from the press to the clip on screen |
| Video, 10 s, the same | 14 to 15 s; 67 s when a 52 s ad played first |
| Card and video against production, the built extension | 34.5 s and 30.2 s |
| Load into WhatsApp in a throwaway profile | reaches WhatsApp Web, reports it not signed in after 2 minutes, as it should |
| Uptime monitor across the switch to the tunnel | no failed check |
| Google's button and Turnstile on the live site | both render; Cloudflare's own analytics beacon is refused by the page's policy, which the privacy page's "no analytics" promise wants |
