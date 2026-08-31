# 2026-08-31 -- Marketing hero density and fonts

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / productization
- **Related:** `CHANGELOG.md` §2026-08-31 Marketing hero fills the first screen · `PROBLEM_LOG.md` §2026-08-31 Marketing hero looked empty · Phase J local-first

## Task

Fill the empty first screen of the public landing page and replace the generic fonts.

## Goal

At 1440x900 the first viewport shows the headline, CTAs, and a desk screenshot. Headlines read as a designed serif, not a default sans.

## Why it mattered

Visitors saw nav + a dark void + FEED/HOME/CONTROL. The product line was in the DOM but hidden under the hero overlay, so the page looked unfinished.

## What we changed

- Two-column `.hero`: copy + Trader View frame
- Overlay z-index: media 0, copy/frame 1; dropped `min-height: 88vh`
- Fonts: Instrument Serif (headlines) + Outfit (body/nav)
- Larger proof labels; tighter section padding
- Desk heading no longer says "not a hosted demo"

## How it works now

`.hero` is an isolated grid. Absolute `.hero-media` stays behind. Content height drives the hero, not a viewport min-height. Proof strip sits right under the two columns.

## Why this approach

**Z-index first**, not a rewrite of the art: the overlay was the actual bug. **Real Trader screenshot in the hero** instead of more generated atmosphere -- the user already asked for screenshots, not a hosted app. **Instrument Serif + Outfit** instead of Syne + IBM Plex: one display serif for headlines, one geometric sans for UI; both load from Google Fonts like before.

Rejected: keeping 88vh and only raising copy z-index (would still look sparse). Rejected: putting all three gallery shots in the hero (too busy; gallery still exists below).

## Verification

Playwright Chromium 1440x900 against `http://127.0.0.1:4177/`: h1 `elementFromPoint` hit, font `"Instrument Serif"`, body Outfit, hero height 472px, lightbox from hero frame. Mobile 390x844: h1 still hit-tested.

## Follow-ups

Git push so Vercel `site/` Root Directory rebuilds `nova.altaystudio.com`. Higgsfield plates still need a working MCP session.

## Keywords

marketing, landing, site/, hero, z-index, Instrument Serif, Outfit, empty space
