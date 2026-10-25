# Commercial licence

Last updated **2026-10-25T15:11:42+05:30**.

SnipShare (this repository, `wastatus`) is **dual licensed**:

| Table CL-1: the two licences | Who it suits | What it asks of you |
|---|---|---|
| **AGPL-3.0-only**, in [LICENSE](LICENSE) | personal use, study, research, open source projects, and any company willing to publish its changes | keep the copyright and licence notices; if you change the code and let people use it over a network, offer them the source of your changed version under the AGPL |
| **A commercial licence**, by agreement with PalWorks | a business that wants to build on this code, or run a changed copy as a service, without publishing its changes | terms agreed in writing: scope, term and fee |

Nothing in the commercial licence takes anything away from the AGPL. If the AGPL's
terms work for you, you need nothing from us.

## When you need the commercial licence

- You run a modified copy of the hosted site (`wastatus/portal.py` and the pages) for
  other people and do not want to publish your modifications.
- You ship the extension (`src/`) or the engine inside a product whose source you do
  not release under the AGPL.
- Your organisation's policy does not allow AGPL code.

You do **not** need it to run the tool on your own machine, to study it, to change it
for yourself, or to run an unmodified copy with a link to this repository.

## Third-party code is not covered

A commercial licence covers PalWorks' own code only. The packages this project uses
keep their own licences whatever you agree with us, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). In particular `aksharamukha`
(AGPL-3.0), used to romanise Tamil titles, stays AGPL: a closed commercial deployment
has to remove it (titles then fall back to `Unidecode`, which is GPL-2.0-or-later and
has its own terms) or comply with its licence.

## How to ask

Open an issue on this repository titled **Commercial licence enquiry**. Say what you
want to build and roughly at what scale; leave out anything confidential. We will
reply on the issue with a private way to continue.

## Contributions

Because the code is offered under two licences, contributions are accepted only
under the terms in [CONTRIBUTING.md](CONTRIBUTING.md#licence-of-contributions), which
let PalWorks offer your contribution under both.

This page describes the licensing model. It is not legal advice, and the commercial
terms themselves are only those agreed in writing.
