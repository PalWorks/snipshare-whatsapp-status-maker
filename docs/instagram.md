# Instagram as a source

What accepting an Instagram link would take, researched on 2026-08-22 for
[TASKS.md](../TASKS.md) T-033.

**Nothing here is built.** This is the record of an investigation, so the decision
starts from findings rather than from guesses. Two things in it were measured on
this machine; everything else is Meta's own documentation, and it is marked which
is which.

## The one fact that shapes everything

**Your own posts and other people's are not the same problem, and no amount of
engineering makes them one.** Every official Instagram endpoint is scoped to an
account that has authorised your app through OAuth. There is no endpoint, at any
price or tier, that returns an arbitrary public account's media. That is a policy
position, not a gap waiting to be filled, and it has been tightening for four years.

So the honest shape of this is two features that share a name:

- **Your own posts.** An official, supported, permanent route exists. It costs an
  account type change and a Meta app.
- **Anybody else's posts.** Exactly one mechanism exists, it is unofficial, and it
  needs a logged in session. There is no second option to fall back to.

## What was measured here, 2026-08-22

**yt-dlp 2026.07.04, anonymous, is dead against Instagram.**

```
$ yt-dlp --simulate --dump-json https://www.instagram.com/reel/<any>/
ERROR: [Instagram] <id>: Instagram sent an empty media response. Check if this
post is accessible in your browser without being logged-in.
```

The same message came back for a shortcode that was invented and cannot exist, so
this is not a per-post permission gate. **The whole anonymous path returns nothing**,
and the extractor cannot tell a private post from a missing one. Anything written
about public reels working without a login is describing an earlier month.

**The oEmbed endpoint answers without a token.**

```
$ curl 'https://graph.facebook.com/v23.0/instagram_oembed?url=<post url>'
{"error":{"message":"The requested resource does not exist", ... }}
```

A structured Media Not Found rather than an authentication failure, which confirms
Meta's June 2026 change: oEmbed for public content no longer needs an access token
or App Review. It returns **embed HTML**, never a media file, so it can confirm that
a URL is a real public post and give the author name and a thumbnail. It cannot give
you anything to render.

## Table IG-1: the five routes

| Route | Your own posts | Other people's | What it needs | Standing |
|---|---|---|---|---|
| yt-dlp with a session cookie | yes | whatever that account can see | `WASTATUS_COOKIES_FROM_BROWSER`, which this tool already has | unofficial. Instagram may act against the account |
| yt-dlp anonymous | no | no | nothing | **measured dead**, above |
| Instagram API with Instagram Login | yes | no | a Meta app, OAuth, and a Business or Creator account | official and supported |
| Instagram API with Facebook Login for Business | yes | no, beyond hashtag search with thin fields | the same, plus a linked Facebook Page | official and supported |
| oEmbed | metadata only | metadata only | nothing, since June 2026 | official, and not enough on its own |
| Driving a logged in browser, as posting already does | yes | yes | the CDP machinery this tool already has | unofficial, but at human speed in a real browser |

## The account type question, answered

The owner asked whether a creator or business account is needed, or whether a
private personal account will do.

**For your own posts through the official API: a personal account will not do.**
The Basic Display API, which was the personal account route, was shut off on
**4 December 2024**. Its replacements, Instagram API with Instagram Login and
Instagram API with Facebook Login for Business, both state Business and Creator
accounts on Meta's own platform page.

Some third party write ups claim the Instagram Login variant supports personal
accounts. Meta's documentation does not say that. **Treat it as unresolved**, and
resolve it by switching the account rather than by reading more blogs.

**Switching to Creator is free, instant and reversible**, and it does not change how
the account is used day to day. It is not the same as Business: Creator keeps the
account feeling personal and is the lighter of the two.

**For your own posts through yt-dlp with your own cookie: any account type works,
including a private one**, because you are simply a logged in viewer of your own
posts. This is the reason the cookie route is tempting and the reason it is risky.

**For other people's posts: no account type helps.** Not Business, not Creator, not
a paid tier. The official API will not return them at all.

## Table IG-2: the risk in the cookie route, stated plainly

| | Posting to WhatsApp, as built | Instagram via yt-dlp with a cookie |
|---|---|---|
| What drives it | a real Chrome, a real logged in session, at human speed | an unbranded HTTP client against a private API |
| What it looks like to the service | a person using the web client | not a browser |
| What is on this machine | nothing. Chrome holds its own login in its own profile | a session cookie, copied out of a browser profile |
| Worst case | the tool stops working | rate limit, checkpoint, or the account is actioned |

This is the same reason [DECISIONS.md](../DECISIONS.md) D-012 chose CDP over an
unofficial WhatsApp library. The difference is that here the unofficial route is the
**only** one that answers the question actually being asked.

**If the cookie route is taken, take it on a second account.** Not as an ethical
hedge, as a blast radius one.

## What Instagram content does to this tool's assumptions

The YouTube path is "a link and two timestamps become a card". Three of its
assumptions do not survive contact with a reel:

| Assumption | What a reel does to it |
|---|---|
| The source is long, so a window has to be chosen | a reel is already short. There is usually nothing to trim |
| The source is landscape, so it must be framed into 9:16 | it is already 9:16. The crop, the blurred fill and D-023 have nothing to do |
| There is artwork and an artist, so a card can be drawn | there is no album art and no channel-as-artist. Card mode is meaningless |

What does survive is the caption carrying a tappable link back, which works for an
Instagram URL exactly as it does for a YouTube one.

**So this is not the existing pipeline with a new extractor bolted on.** It is
"fetch a finished vertical video and re-post it", which uses the posting half of
this tool and almost none of the making half. That is a smaller feature than it
sounds, and a differently shaped one.

## The part that is not technical

Instagram's Terms prohibit collecting content by automated means without their prior
permission. Separately, and regardless of mechanism, re-posting somebody else's
video to your own Status is their copyright, not yours. Neither point is a reason
this cannot be built, and both are the owner's call rather than this document's, but
neither should be discovered afterwards.

## What is needed to plan this properly

Listed in [TASKS.md](../TASKS.md) T-033, Table T33-2. The short version: which of the
two features is wanted, whether the account can become Creator, whether a cookie is
acceptable and on which account, whether the output is re-encoded or passed through,
and two or three real links to measure against. Every other source in this project
was settled by measurement, and there is nothing to measure until those links exist.

## Sources

- [Instagram Platform, Meta for Developers](https://developers.facebook.com/docs/instagram-platform)
- [oEmbed, Instagram Platform](https://developers.facebook.com/docs/instagram-platform/oembed/)
- [Deprecation of the Instagram Basic Display API](https://lightwidget.com/basic-display-api-deprecation)
- [Instagram API integration, rate limits and challenges](https://www.getphyllo.com/post/instagram-api-integration-101-for-developers-of-the-creator-economy)
- [After Basic Display EOL: Instagram's 2026 API rules](https://storrito.com/resources/Instagram-API-2026/)
- [Meta undid the change that broke Instagram embeds](https://wpmayor.com/meta-tokenless-oembed-wordpress/)
- [yt-dlp for Instagram](https://ytdlp.org/guides/yt-dlp-for-instagram)
- [yt-dlp issue 17074: empty media response without cookies](https://github.com/yt-dlp/yt-dlp/issues/17074)
