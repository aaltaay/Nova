# ADR 061 -- The heat map: Level 2 over time on the Trader, from the book Nova already has

**Status:** Accepted · **Date:** 2026-10-20
**Builds on:** [[033-focus-and-book-watch-sensors]] (the desk's own read of the book) · [[045-orders-refuse-a-stale-view]] (the
desk must never lag: a slow screen locks orders) · [[044-one-bots-page]] (lent Level 2 lines) ·
[[005-frontend-feature-slices]] · [[058-volume-profile-on-the-5-minute-chart]] (a Trader toolbar switch, browser
setting)
**Decided by:** the operator, 2026-10-20, from a Bookmap-style YouTube thumbnail: "How do we create our own heat map?
Can you show me a PNG first?" Mockup v1 was rejected ("I can barely read it ... I don't know how Heatmap works. You got
to read Thinkorswim. They have a good one we can copy"; "I'm sure you can reverse engineer it"); v2 copied
thinkorswim's look (its order-book heat map is Bookmap inside its Charts tab); on v2's zooms: "Is this real data?
Something about it doesn't look right" -- it was real, the drawing was not -- and "fix the look. I don't think it needs
to be in a fixed time"; v3 approved ("1 go"). On opening it: "one click to replace all charts and one click to bring
them back ... we may iterate". Mockups and the scripts that drew them from Nova's recordings:
`F:/Nova/design/heatmap/` (private).

## Context

A heat map is the Level 2 ladder saved every moment and laid side by side: each row a price, time across, colour by
the shares waiting there. A big order that stays becomes a bright line; whether buyers eat it or it is pulled is
visible as it happens, which the ladder (one moment) cannot show. Trades go on top as dots.

Nova already streams what it needs on every Trader tab: IBKR's Level 2 (`/ws/ibkr/depth/{symbol}`, 10 rows a side,
SMART depth) and Time & Sales (`/ws/ibkr/tape/{symbol}`) with the desk's side verdict per print. IBKR keeps no book
history, and its 10 rows reach only a few cents past the bid and ask (4-7 cents on GLND, 2026-10-14). The desk shares
the PC with the order path: ADR 045 locks orders when the view lags.

## Decision

1. **A Heat map switch on the Trader's chart toolbar** (beside Eyes, Setups, Levels, Profile). One click covers the
   four charts with one full-size heat map of the same stock; its own switch (or the toolbar's) brings them back. The
   charts stay mounted and paused underneath (`chartActive` false), so going back asks IBKR for no bars. Off until the
   operator turns it on; one browser setting for every Trader tab and window.
2. **No socket or IBKR line of its own.** The Trader's depth and tape hooks hand each book, beat and print to the heat
   map's store (`frontend/src/heat_map/heatStore.ts`), hidden tab or not, so the heat map has history the moment it is
   shown: from when Nova opened that stock's Level 2, up to 30 minutes, at most 4 stocks (memory only).
3. **Real or black.** Every line is a book IBKR sent; a price outside the rows IBKR sent is black ("not seen"), never
   an empty level. The last book stays drawn only while the line keeps beating; a lent or refused line, a top-of-book
   only line, a quiet line and a stock with no book yet each say so on screen.
4. **The look of thinkorswim's Bookmap** (mockup v3): thin glowing lines per price on black, one blue-to-red scale
   (blue few, yellow to red many), green and red sphere dots, a thin line through the middle of the bid and ask, the
   book now as numbers on the right, volume bars underneath, dotted time lines.
5. **Trades are bursts, not clock slices.** A burst of buying (prints at the ask) lasts until a seller hits the bid,
   the tape pauses over a second, or the price moves more than two ticks; selling likewise; in-between prints burst
   apart and draw fainter. One dot per burst, area = shares. Bursts under the chosen size (500 / 1k / 2k / 5k, 1k by
   default) get no dot and still count in the volume bars.
6. **No candle time frame.** The trader picks how much time fits across the screen: 1, 5, 15 or 30 minutes (5 by
   default) or the mouse wheel between 30 seconds and 30 minutes. Each column is the time-weighted average of the books
   in force during it, so a flickering order fades instead of speckling on wide zooms.
7. **Cheap by construction.** One canvas, redrawn at most every 150 ms and only when the data or the clock moved, the
   window is visible and the heat map is shown; the book grid fills one ImageData at 2 CSS px per time column. A full
   redraw measured 4-8 ms on GLND's busiest 5 minutes (headless Chromium, software rendering).
8. **Market time.** Prints carry their own time (a Sim replay's, or Nova's receipt live); books are stamped with the
   browser clock plus the newest print's offset, so books and prints share the replay's clock on a Sim desk. A print
   far behind the newest, or the tape's `scrub_reset`, starts the stock over.

## Consequences

- Only the stock in the Trader tab's Level 2 has a heat map, from when its line opened. A deeper book for past,
  unrecorded days (Nasdaq's full book, Databento MBO) is a purchase and the operator's call; a backend history read from
  the Session Records is a later step if the 30 minutes in memory are not enough.
- Whether IBKR will send more than 10 rows (`IBKR_DEPTH_NUM_ROWS`) is untested; IBKR's API documentation gives no
  maximum. More rows widen the lines the heat map can show at no other cost.
- The dots and colours describe the book and tape. Nothing here places, stages or blocks an order, and nothing feeds a
  bot, a setup or a scanner row.
