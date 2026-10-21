# ADR 062 -- The Forex page: the whole currency market's size, and each currency's day

**Status:** Accepted · **Date:** 2026-10-20
**Builds on:** [[060-global-page]] (its layout, its reads last in line, its kept answers, its published-size
amendment) · [[053-market-page]] (a read-only reference board; refused instruments stated per row, never on the
stock session's flags) · [[054-quotes-someone-waits-on-read-a-brief-line]] · [[005-frontend-feature-slices]]
**Decided by:** the operator, 2026-10-20, looking at the Global page: "I want something similar but for forex", "But a
PNG first, of how it looks"; after mockup v1: "Really, is that the only Forex market? I thought it was a lot larger",
"We got to also say the total market, dude", "For each market, we want to see what's going on, like how big it is and
everything"; mockup v2 approved: "All right, build this to be on top of the global".

## Context

Forex has no exchange. About $9.5 trillion changes hands a day, nearly all of it privately between banks, dealers and
their clients, so no feed -- IBKR's included -- sees the market's total, or any currency's, live. The only measure of
its size is the BIS Triennial Central Bank Survey: 1,100+ dealers in 52 jurisdictions report a month's turnover every
three years (the last, April 2025; final results June 2026). What can be read live is narrower:

- **Prices of the whole market.** A currency's rate is one rate wherever it trades (arbitrage keeps it so), and IBKR
  quotes spot forex on IDEALPRO with no extra market-data subscription. Mockup v1 drew only the second measure
  below and read as if forex were a $58B market; the operator rejected that.
- **Trades of a public slice.** Exchange-traded currency futures and options are about $0.2T a day of the $9.5T (BIS
  memo), CME's FX futures about 1%. Their trades are public, one by one, as the Global page's index futures are.

## Decision

1. **A `Forex` page, first on the nav rail, above Global** (`frontend/src/forex_board/`, backend
   `backend/forex_board/`). Read-only: it places, stages and cancels nothing and feeds nothing else.
2. **The whole market's size comes first, labelled as what it is.** The page's head strip states the total ($9.51T a
   day), how it splits by instrument, where the desks are (UK 38%, US 19%, Singapore 12%, Hong Kong 7%), and that the
   19 currencies shown are 95% of it -- every figure the BIS survey's, April 2025 daily averages, shown with that
   month and source ("published every three years, not live"). Each currency's size is its BIS turnover (it is on one
   side of every trade it is in, so the shares add to 200%), with its rank and its biggest pair. These sizes size the
   map's bubbles. They are the only numbers on the page that are not IBKR's, and they compute nothing.
3. **What is going on is read from IBKR, two ways, never mixed.**
   - **Strength** (the whole market): each currency against an even mix of the others IBKR prices, from IDEALPRO spot
     midpoints -- a line held for a moment for "now", one-hour bars for the day's path, daily bars for 7 D / 30 D. The
     FX day starts at 17:00 New York, as the market's does. The map is coloured by it by default.
   - **Futures** (a public slice): the money in rising one-minute bars minus falling ones of each currency's CME
     future, as ADR 060 measures index futures. Every CME currency future is priced against the US dollar, so the
     dollar's row is the other side of all of them. A currency with no CME future, or one IBKR refuses, says so.
   - A currency IBKR has no spot quote for says "no price" with IBKR's reason; a spot refused where a future exists
     (the Brazilian real) moves by its future, and the row says so. Nothing is filled in.
4. **The day, by session.** Asia (17:00 ET until London opens), London (until New York opens) and New York (to
   17:00 ET) each name the currency that rose most and fell most in its hours, beside its desks' BIS share. "Follow
   the sun" shows each currency's strength (or its futures pressure, by the switch) hour by hour over the FX day under
   the Asia, London and New York sessions. These two always show the current FX day, whatever the period.
5. **Forex reads last, taking turns.** Like Global it asks IBKR only while connected; it sends a historical request only
   while more than `FOREX_HISTORY_HEADROOM` (30) of the 60 are left -- the Market and Global pages' own number, so the
   three take turns -- and 40 while the Market or Global page shows and this one does not; Global now also yields
   while this page shows. Its pacing kind is `forex`. Spot quotes use a line held for a moment, only with lines
   spare. Not shown, it keeps a slower cadence outside 09:30-16:00 ET only, and its answers are kept across restarts.
6. **Its requests never touch the stock session's flags** (`ibkr.reference_errors`, ADR 053 decision 3); a refused
   instrument is not asked again for hours.

## Consequences

- The operator sees the market's real size beside the live slice, and never a slice standing in for the whole.
- The sizes age: the next BIS survey is April 2028. A newer survey replaces the table by hand; the month is shown.
- Futures pressure is the futures market's eagerness, about 1% of forex; the page says which instrument it read.
- Not yet proven live: the CME symbols IBKR uses for the peso (`MXP`), real (`BRE`), rand and yuan futures, and which
  currencies IDEALPRO quotes (the rupee, won and Taiwan dollar are expected to answer "no price"). Each row shows
  IBKR's answer.
- The Global and Forex pages share one kit (`frontend/src/world_board/`: the world map's land and projection, the box
  hook, the number words, the board's look) rather than two copies.

## Rejected

- **Sizing currencies by their futures money.** v1 did; it showed forex as a $58B market.
- **A live total from another feed** (CLS settlement data, dealer platforms). Paid, delayed, a different source from
  the desk's one market-data feed, and still a slice; the BIS figure is the only whole-market measure.
- **Estimating today's turnover from the April 2025 average.** The operator ruled out estimates the page does not
  need; the average is shown as an average.
