# FAQ

Last updated **2026-10-25T15:21:02+05:30**

Short answers to the questions people actually ask, with a pointer to the document
that has the whole answer. The first part is for people using SnipShare or the local
tool; the second is for people running or changing the code. Symptom to fix, in
full, is in [RUNBOOK.md](RUNBOOK.md); known gaps are in
[LIMITATIONS.md](LIMITATIONS.md).

## Using it

### Is this a downloader?

No. It reads only the window you choose, at most 90 seconds, and turns it into a new
vertical clip with the title and channel drawn on it and the link to the original in
the caption. On SnipShare the extension reads that window from what YouTube's own
player has already loaded in your browser while the video plays; it never saves the
whole video, never skips or blocks ads (it waits for them), and cannot read protected
(DRM) video. The point of a clip is to send people to the source.

### Why does it never post by itself?

Because sending is the one step that cannot be undone, and the one that needs no
help: a single press in a window that is already open. **Load into WhatsApp** opens
your Status composer with the clip and caption in place and stops there, so you see
exactly what will go out (D-020). On the local tool, `--post` can press Send for you,
but it is off by default and only sends when asked for explicitly; the hosted site
never does (D-090).

### Why is the link in my caption not tappable?

WhatsApp does not turn your **own** Status caption into a link on the device you
posted it from. It is a real, tappable link for everybody else, and on your other
devices. Check it from a second device. This misled the project once, see
[INCIDENTS.md](INCIDENTS.md) IN-02.

### Why does making a clip need Chrome on a computer?

The extension is what reads the video, by listening to the Media Source Extensions
that YouTube's player feeds, and Chrome on a phone runs no extensions. Other browsers
would need their own build and testing. On a phone, SnipShare shows the clips you
have made, to watch and save. See [LIMITATIONS.md](LIMITATIONS.md), Tables LI-11 and
LI-12.

### Why is the extension loaded unpacked, with Developer mode on?

The Chrome Web Store's policy does not allow extensions that download streaming
media. Install it from the site's `/install` page, as in
[LOCAL_SETUP.md](LOCAL_SETUP.md), **Use SnipShare instead**.

### Why is SnipShare by invitation, and limited?

It is an experiment on a small server, with one render at a time. Letting people in
by hand, a daily allowance of clips each, and a cap across everybody an hour keep it
working for the people using it, at a person's pace. The admin can raise the daily
limit (`WASTATUS_CLIPS_PER_DAY`); the hourly cap is 60 renders by default.

### The page says the extension is not answering, or is an old version

Load the current zip from `/install`, replace the folder's contents, and press reload
on the extension's card in `chrome://extensions`. If a YouTube tab was open before
the extension was installed or updated, reload it once. [RUNBOOK.md](RUNBOOK.md),
Tables RB-3 and RB-4.

### The capture says YouTube stopped sending the video

Reload the YouTube page and make the clip again. If several people see it at once,
YouTube has probably changed its player; the owner is alerted automatically.

### WhatsApp shows my Status, but nobody can see it and it has no views

WhatsApp refused it. The tool now reads WhatsApp's own acknowledgement and reports a
refusal as a failure rather than a success (D-071). Delete it in the browser and post
again; if the same file is refused twice, make the clip afresh. If the tool says the
Status is **unconfirmed**, it may still go out: check its views before posting again,
so you do not post it twice.

### The composer never opens for my clip

WhatsApp refuses media over 10 MiB without a word. The tool keeps every clip near
10 MB and says on screen when one goes over, so suspect a file made by hand.

### What does SnipShare keep about me?

Your Google name and email, your request, your last few clips, and the daily counts
that keep the limits. Never your WhatsApp messages. Failure reports carry a step, a
code and versions, never the video, title or words. **Delete my account** on the
account page removes it all at once. The privacy page on the site has the detail.

### I made a video and want a clip of it removed

Write to the contact address on the site's terms page with the link. The clip is
removed, and the account that made it can be suspended.

### Is it affiliated with YouTube, Google, WhatsApp or Meta?

No. Those names are used only to say what it works with, and they belong to their
owners. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Running the local tool

**Table FQ-1: the local page's common problems**

| You see | Answer |
|---|---|
| Every button says `bad or missing token`, or the page says it is older than the server | the tab was opened before the server last restarted; the token belongs to one run of the server. Reload the page |
| The **WhatsApp Web** health row is amber | the posting Chrome is not running. Press **start it** on that row |
| The **ffmpeg** row is amber | install ffmpeg, then press **recheck** |
| The **token provider** row is amber, or `PO token provider missing` | `bash scripts/setup_provider.sh`, then restart the page |
| The sticker card says the library is not installed | `bash scripts/setup_stickers.sh`, then reload |
| `error: cannot listen on 127.0.0.1:8765` | a page is already serving there. Open it, or start another with `--port` |
| The phone cannot open the page | it was started without `--also-on tailscale`, so it is on loopback only. No `Also on` line at start up means no phone. Set `WASTATUS_ALSO_ON=tailscale` in `.env` to make it stick |
| Posting cannot find a WhatsApp control | WhatsApp renamed it. RUNBOOK's **Posting failed** prints what the controls are called today; the lists are at the top of `wastatus/post.py` and in `src/whatsapp.js` |
| `no Chrome answering on 127.0.0.1:9222` | no debug browser on that port. Your everyday Chrome profile cannot be used for this; RUNBOOK, **Chrome will not open its debug port** |
| A download keeps failing | run it again first; YouTube's anti bot behaviour often lets the second try through. Then `tail -1 logs/runs.jsonl` and `tail -40 logs/wastatus.log` |
| `--video` output looks soft | that video had no HLS rendition, so it fell back to 360p. Use card mode for that song |
| An older clip has gone from `out/` | the newest 20 are kept. Raise `--keep-last` |
| The first ever run takes minutes | yt-dlp is fetching its JavaScript solver once |

Sources: [LOCAL_SETUP.md](LOCAL_SETUP.md), **If something looks wrong** and **If it
fails**; [RUNBOOK.md](RUNBOOK.md), Table RB-1.

### Why is there no Tamil script on the card?

A product decision, not a technical limit: every title is romanised the way Tamil
speakers spell it, so no Tamil font is needed. `--title` overrides the result. See
[DOMAIN.md](DOMAIN.md), **Transliteration rules**.

### Can I use my everyday Chrome for posting?

No. Chrome 136 and later refuse remote debugging on the default profile, by design.
The posting browser is a separate profile (D-022).

### Should the local page be put on my network address?

No. It hands its token to whoever loads it. Keep it on loopback, or add your own
tailnet with `--also-on tailscale`. See [SECURITY.md](SECURITY.md).

## Contributing and licensing

### What is the licence?

**Dual.** The code is AGPL-3.0-only ([LICENSE](LICENSE)), or a commercial licence by
written agreement ([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). You do not need
the commercial one to run the tool yourself, study it, change it for yourself, or run
an unmodified copy that links to this repository. You do need it to run a modified
hosted site for others without publishing your changes, or to ship the code inside a
product you do not release under the AGPL. Ask by opening an issue titled
**Commercial licence enquiry**.

### Why AGPL, and why does every page link to the source?

The hosted site runs aksharamukha, which is AGPL-3.0, for people over a network, so
every public page links to the source (`WASTATUS_SOURCE_URL`, by default
`https://github.com/PalWorks/snipshare`). A changed copy must point that link at its
own changed source. Third-party packages keep their own licences whatever is agreed;
see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### How do I contribute?

Read [CONTRIBUTING.md](CONTRIBUTING.md): because the code is offered under two
licences, contributions are accepted only under its licence terms. Then
[AGENTS.md](AGENTS.md) for the rules of the codebase and [TESTING.md](TESTING.md) for
the suite. `.venv/bin/python -m pytest` must pass before anything else.

### Why does a test fail on my documentation change?

`tests/test_publishable.py` fails on any real email address outside `example.com`,
any IP address other than loopback or the `100.64.0.x` placeholders, any home
directory path, and anything on the private deny list. Use placeholders.

### How do I report a security issue?

Privately, through GitHub: on this repository, **Security**, then **Report a
vulnerability**. Please do not open a public issue. If private reporting is
unavailable, open an issue saying only "security report, please contact me" and the
maintainer will find a private channel. See [SECURITY.md](SECURITY.md), **Reporting**.

### Where is everything else?

[CONTEXT_MAP.md](CONTEXT_MAP.md) says which file answers which question.
[GLOSSARY.md](GLOSSARY.md) defines the vocabulary, [DEPENDENCIES.md](DEPENDENCIES.md)
lists what the project needs, [OBSERVABILITY.md](OBSERVABILITY.md) says what it
records, and [INCIDENTS.md](INCIDENTS.md) what has gone wrong before.
