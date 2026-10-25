# Hosting: OCI and Evolution API

What a hosted wastatus would look like if the posting went through Evolution API
instead of a browser, and what was measured before deciding anything.

**Superseded on 2026-10-24.** Phase 2 was built as a browser extension and a hosted
renderer that never talks to YouTube, [extension.md](extension.md) and
[DECISIONS.md](../DECISIONS.md) D-085. The datacentre risk this document ends on is
the reason. Kept as the record of what was weighed first.

**Nothing here is built.** This is the record of an investigation, so the next
session starts from findings rather than from guesses.

**Deferred by the owner on 2026-08-19 at 09:14 IST.** He chose to use the local tool
as it stands for a while before pursuing hosting, and asked for it rounded off for
daily use instead. Nothing in this document was started, so nothing is half done.
[ROADMAP.md](../ROADMAP.md) phase 2 held the agreed shape; what was built instead is
in [extension.md](extension.md).

The smaller variant at the end of this document, keeping the laptop and reaching the
page from a phone, **was** built. See [DECISIONS.md](../DECISIONS.md) D-026 and D-027.

Written **2026-08-19 01:52 IST**, findings dated where they were taken.

---

## The question

The owner asked, on 2026-08-19 at 01:42 IST: assume the WhatsApp account is linked
to a running Evolution API instance, and assume the service is hosted on an Oracle
OCI cloud server. What does the workflow look like?

## The shape

```
phone or laptop
   |  https://status.<his domain>   (Cloudflare Access decides who gets in)
   v
[cloudflared] --> [wastatus: the same page, the same pipeline.produce]
                       |  yt-dlp + ffmpeg + the PO token provider
                       |  writes out/<stem>.mp4
                       |
                       |  POST http://evolution:8080/message/sendStatus/<instance>
                       |  { type: "video",
                       |    content: "http://wastatus:8765/api/clip?stem=...&t=...",
                       |    caption: "https://youtu.be/...",
                       |    statusJidList: [...] }
                       v
                  [evolution-api] --fetches that URL--> back to wastatus
                       |  Baileys, paired to the account as a device
                       v
                  WhatsApp --> contacts' Status trays
```

Four containers on one Docker network: `wastatus`, `evolution-api`, its `postgres`
and `redis`, plus `cloudflared`. No inbound ports open on the VM at all.

## Table HO-1: what moves and what does not

| Piece | On the laptop today | Hosted with Evolution |
|---|---|---|
| `pipeline.produce` | the engine | **identical**, not a line of it changes |
| Posting | `post.py` drives Chrome over CDP | one HTTP call. `post.py` stays for the laptop |
| The browser | a Chrome profile with a QR scan, kept alive | gone from the server entirely |
| Access control | a per-process token on loopback | Cloudflare Access in front, no open ports |
| Audience | WhatsApp's own privacy setting decides | **an explicit JID list we build** |
| Load, then send | WhatsApp's composer holds the draft | no equivalent exists, see below |
| YouTube egress | a home IP | a datacentre IP, which is the real risk |

## What Evolution API's status endpoint actually does

Read from `EvolutionAPI/evolution-api` on `main` at **2026-08-19 01:45 IST**; the
repository was last pushed 2026-07-14 and has 9.3k stars. The docs pages 404, so
this comes from the source. Every line is **read, not executed**: nothing here has
been run against a live instance. The same findings are in
[MEMORY.md](../MEMORY.md) Table ME-3.

`POST /message/sendStatus/{instance}` takes
`{type, content, caption, statusJidList, allContacts, backgroundColor, font}`.

Three findings change the design:

**1. It wants a URL, not base64.** For `type: video` the handler passes
`{video: {url: content}}` straight to Baileys, with no base64 branch of its own.
The multipart upload path sets `content` to a base64 string and hands *that* to the
same `url` field. So the reliable shape is a URL Evolution can fetch, which is why
both containers belong on one network and the clip can stay private:
`http://wastatus:8765/api/clip?stem=...&t=...` is an internal name, and the token
guard already on that route is what protects it.

**2. `allContacts: true` is not "everyone".** It builds the list from Evolution's
own contact table, keeping rows that have a `pushName`. On a fresh instance that
throws `Contacts not found`. There is a second, different implementation of the
same flag further down the file, excluding groups instead of filtering on
`pushName`, behind an option the first one never sets.

More important: **WhatsApp's status privacy setting is enforced by the sending
client.** Evolution sends to the list it is given, so "my contacts except…" is
silently ignored. The audience stops being WhatsApp's business and becomes ours.

**3. Partial failure is silent.** The send fans out in batches of ten JIDs: the
first uploads the media, the rest relay the same `messageId`, and those later
batches run under `Promise.allSettled`. A failed batch is swallowed. Those ten
contacts never see the Status and nothing says so.

The route also carries the maintainers' own comment,
`// TODO: Revisar funcionamento do envio de Status`. The open issues agree. It
works for people; it is not the settled part of that project.

**Design consequence:** keep a named audience list in the tool, show it in the page
before sending, and always pass an explicit `statusJidList`. Never use
`allContacts` for a real post. That turns an invisible risk into something readable.

## The step that has no equivalent

The page's primary action is **Load into WhatsApp**: fill the composer, stop, let a
human press Send ([DECISIONS.md](../DECISIONS.md) D-020). An API call either sends
or does not. Three substitutes, in preference order:

| Option | What it feels like | Cost |
|---|---|---|
| The page is the review step, and Send goes out at once | today's flow minus the WhatsApp window. The preview is already an honest frame | no "I saw it in WhatsApp" moment |
| Queue it, approve from the phone | hosting puts the page on the phone, so approving from the sofa is natural | none, it is a state on the clip |
| Post to yourself first, `statusJidList: [own JID]`, then a second button sends to everyone | the closest analogue: it appears in the real tray, seen by nobody else | two uploads, and a duplicate to delete |

Recommended: the first two together, with the third as an option for a post that
matters.

## The risk that decides it

**A datacentre IP against YouTube.** OCI ranges are heavily flagged and the failure
looks like a bot check on every ladder entry. Both hooks already exist
(`WASTATUS_PROXY`, `WASTATUS_COOKIES_FROM_BROWSER`) and the PO token provider helps.
In order: try the plain VM, since the provider plus the JS solver may be enough;
then proxy egress through a residential IP; and **do not** put a real Google
session's cookies on an internet-facing box.

**Account risk.** Evolution is Baileys, the unofficial protocol client
[DECISIONS.md](../DECISIONS.md) D-002 rejected precisely to protect this account.
The owner has accepted that. The mitigations are: keep the browser path working as a
fallback, keep the fan-out small and human-paced, and treat a ban as losing the
account the whole tool serves.

## What hosting buys

- **Scheduling**, which is impossible today: post at 07:30, or queue a week
- No laptop, no Chrome to babysit, no QR profile, no window-throttling workarounds
- Posting becomes an HTTP call with a status code instead of CSS selectors that a
  WhatsApp redesign can break without notice, which is the single most fragile thing
  in the current design

## What it costs

- ffmpeg on four Ampere cores is about as fast as the laptop, not faster: a 60
  second clip stays near 80 seconds
- Evolution needs Postgres and Redis, roughly 1 GB of RAM, comfortable in 24 GB
- The PO token provider has to become a long lived service rather than a per run
  child, and concurrent renders need a queue
- One more moving part, whose status endpoint its own maintainers flag as unsettled

## The two tests that come before any building

Both can kill the plan, so neither is worth deferring.

1. **On the VM, run `wastatus.sh` once.** If a datacentre IP cannot fetch a section,
   the answer becomes "render at home, host only the posting and the scheduling".
2. **Send one status through Evolution to your own JID only**, with a video URL and
   a caption. Confirm it plays, and confirm the caption is still tappable. That is
   the same load bearing check the whole caption design rests on, and it has to be
   re-proven on a different transport.

Recorded as open verification debt in [MEMORY.md](../MEMORY.md) Table ME-1.

## A smaller variant: keep the laptop, publish from the phone

Asked on **2026-08-19 08:14 IST**: with the home laptop kept, can the drafting and
uploading happen on the laptop while the publishing happens on the phone, without
losing the existing WhatsApp Web route?

**Not literally.** A Status composer is local to the client that opened it. There is
no synced draft, so a composer loaded on the laptop cannot be sent from the phone.

**But two shapes give the substance of it, and both keep every existing path.** Both
were built on 2026-08-19; what follows is what they turned out to be.

1. **The page on the phone, driving the laptop.** `wastatus serve` binds loopback
   today. On a Tailscale interface instead, the phone opens the same page and
   presses the same buttons; the posting still happens through the laptop's Chrome.
   Nothing about the posting path changes. Tailscale rather than `0.0.0.0`, because
   the page hands its token to whoever loads it, so "anyone on the WiFi" is not an
   acceptable trust boundary. See [SECURITY.md](../SECURITY.md).
2. **Deliver the clip to the phone and post it natively.** The page offers the mp4
   as a download and the caption as one tap of Copy. Posting then happens in the
   real WhatsApp app, with WhatsApp's own audience and privacy settings and no
   automation at all. It is the safest route in the whole tool.

**Both are on the page at once, and only the emphasis changes.** The owner asked for
this on 2026-08-19 at 09:46 IST: keep Load and Send when the page is open beside
WhatsApp Web, and offer Download and Copy when it is open on a phone. The page decides
which is the primary button from the address the request arrived on, and hides
neither. See [DECISIONS.md](../DECISIONS.md) D-026.

**Rendering never moves.** In both shapes the laptop fetches and encodes, because
yt-dlp, ffmpeg, the token provider and the output folder all live there. The phone is
the screen and the buttons, which is what makes shape 1 a remote control rather than a
second copy of the tool. The reason posting also stays on the laptop in shape 1 is
that the WhatsApp session is a device pairing inside that Chrome profile: the phone's
browser has no access to it, and WhatsApp Web does not run in a mobile browser anyway.

**The caption question that shape 2 rested on is settled.** Asked and answered on
2026-08-19 between 09:46 and 09:56 IST. A URL typed into the Status caption from the
Android composer **is** tappable, but not when you look at your own Status on the
device you posted it from. The first test was done on one device only and produced the
opposite conclusion, which briefly looked like a reason to redesign the route. It was
not. No follow-up text status is needed, and Copy ships the caption exactly as
written. Recorded in [MEMORY.md](../MEMORY.md) under Settled, because the next person
to test a caption will be misled the same way.

**One defect blocked the first shape, and is now fixed.**
`serve.Handler._authorised` compared the `Origin` header against a hardcoded
`127.0.0.1` and `localhost`. Chrome sends `Origin` on every same-origin POST, so
every write from any other address was refused: the page would load and read, and
nothing could be made or posted.

Reproduced on **2026-08-19 08:41 IST** by binding the server to `127.0.0.2`, which
is still loopback and so exposes nothing, and driving the real page in Chrome:
`GET /api/state` returned 200 and `POST /api/render` returned 403. After the fix,
the same probe returns 200 for both.

The check now derives the expected origin from the request's own `Host` header, and
trusts that header only when it names an address rather than a name. That is what
keeps DNS rebinding out: an attacker can point `evil.com` at 127.0.0.1, and the
browser will then send `Host: evil.com` with a matching `Origin`, and both are
refused. A hostname front door behind a tunnel will need this widened deliberately,
which is phase 2's business.

**Binding beyond loopback is now available and still off by default.** `--also-on`
adds a second address; loopback stays bound, and the value has to be an IP literal so
it cannot drift from what a browser sends as `Host`. See
[DECISIONS.md](../DECISIONS.md) D-027 and [SECURITY.md](../SECURITY.md).

**Tailscale is installed and working, confirmed again on 2026-08-20 after a reboot.** `--also-on tailscale` was
run against the real tailnet: the page answered on both addresses, reporting
`local: true` on loopback and `local: false` on the tailnet one, which is the fact
D-026 leans on. So the phone shape above is available today, and phase 2 is about
reaching the page without both devices being on the tailnet, not about reaching it
from a phone at all.
