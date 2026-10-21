# ADR 065 -- Ahead: the forecast zone on the 1-minute chart

**Status:** Accepted · **Date:** 2026-10-20
**Builds on:** [[036-the-bots-read-on-one-stock]] (Nova's trend lines, level zones and setup lanes) ·
[[058-volume-profile-on-the-5-minute-chart]] (a chart study behind a toolbar switch, causal on a Sim replay) ·
[[005-frontend-feature-slices]] · [[020-three-venues-one-feed]] (one feed, the playhead as the clock on a replay)
**Decided by:** the operator, 2026-10-20: to "see the future prediction on the charts like how you had them drawn",
from a PNG mockup of the Trader's 1-minute chart with a hatched zone right of the newest candle, and the go-ahead to
build it.

## Context

The operator asked to see the next 15 minutes drawn on the Trader's chart: where price and volume could go, how
Nova's own support and resistance lines run on to where they meet, which of the nearest walls a move reaches first,
and what would happen to a setup if it triggered.

A forecast is not data. Drawn in the candles' own style it would read as a record of something that happened, which
Nova never does with a guess. So the zone has to look unlike the chart it sits on, every number in it has to say it
is a forecast, and nothing from it may reach an order.

The model does not run inside Nova. It is a private service on the same PC, reached over loopback with a token,
under its own contract (`ahead-forecaster/1`, `architecture/schema/ahead.md`). Nova owns the market data (IBKR live,
the replay's own bars on Sim), the lines and levels, and everything drawn; the forecaster gets completed 1-minute
bars from Nova and reads no market data itself.

A first plan had the backend work out the lines to the meet, the walls and the setup odds from the stock read. The
stock read is cached for about 2 seconds under a key that includes the plan's entry and stop, so Ahead's polls would
have missed the page's own read almost every time and rebuilt it in the process that carries the order path. The
page already holds that read.

## Decision

1. **A chart study only.** Nothing in Ahead places, stages, sizes, delays or blocks an order, and nothing feeds a
   scanner row, a setup, an alert or a bot (#791). Every answer carries that sentence (`never`).
2. **The Trader's 1-minute pane only, behind a toolbar switch that is off by default.** The switch is the browser's
   setting (`nova.ahead.prefs`), shared by every Trader tab and window. While it is off the desk asks nothing and
   draws nothing.
3. **The backend serves only what needs the forecaster.** `GET /api/ahead/forecast/{symbol}` sends the completed
   1-minute bars of the session, the desk clock and the prior close (null when Nova does not know it) and answers
   the forecaster's view; `GET /api/ahead/status` reports whether one is set up and what its health says.
   `backend/ahead/` never calls the stock read.
4. **Nova's own parts are worked out on the desk.** The lines to the meet, the walls, the wall-first odds, the "if it
   triggers" odds and the MACD fan are computed in `frontend/src/ahead/` from the answer, the stock read the Trader
   page already holds and the chart's own candles. The chart and Ahead cannot disagree about a line, and the order
   path's process does no extra work for them.
5. **Nova's lines to the meet need no AI.** Its holding 1-minute support and resistance, carried on from the newest
   completed candle to where they meet, show whenever Ahead is on -- on every desk, with or without a forecaster.
   Their slopes are rounded, so a meet's time and price are labelled "≈".
6. **The forecaster is reached on loopback only, with a token.** `NOVA_AHEAD_URL` must name this PC (127.0.0.1,
   localhost or ::1); `NOVA_AHEAD_TOKEN` is a secret kept in `.env`. Proxies and redirects are not followed, the
   token goes only to that address, and an answer is read strictly: a missing or wrong field is an `error` naming
   the field, never filled in.
7. **Honesty on the chart.** A hatched zone labelled "AI view, not data", the 50% and 80% bands, 16 drawn paths
   labelled as a few of the forecaster's, ghost volume in outline, and every number marked as a forecast. No bar or
   whitespace is added to any series, and the chart's right offset is never changed.
8. **The exam decides what shows.** The AI view shows only when the forecaster reports a passed exam (its answer's
   `exam_passed` and the exam itself both say passed; a pass whose exam Nova cannot read is not one), or when the
   viewer's "Show before it has earned it" switch (off by default) is on -- and then with the exam's numbers and its
   scope printed in amber. The chip says "passed its exam" with the scope and sample, never a bare claim of skill:
   the exam covered the stocks and hours its scope names, not every stock at every hour. An exam with no scope reads
   "scope not stated".
9. **Never over a real candle.** The AI view is drawn only when the chart's newest completed candle is the one the
   answer was made from. A newer candle on the chart means "Reading the minute that just closed…"; a chart behind
   the answer means "Catching up to the chart…". A previous minute's forecast is never kept on screen.
10. **Odds from paths say what they assume.** The forecaster gives a range per minute; its paths join those ranges by
    an assumed path shape (`paths.joined_by`), and they are closes only, so a wick that touches is not seen. Wherever
    the desk shows odds from paths it says so, and it says that the nearer wall wins more often by distance alone.
11. **On a Sim replay it is causal.** The desk clock is the playhead: no bar that ends after it is ever sent, the
    forecast starts at the end of the newest completed bar, and after a scrub the desk drops any answer made after
    the playhead and asks again.
12. **One request per symbol per completed minute.** One in flight per symbol, the newest minute wins, successes
    are kept per minute, and a failure (`offline`, `warming`, `error`) is kept only 5 seconds, so a forecaster that
    has just finished starting up is picked up on the next poll. Three transport failures in a row stop asking for 30
    seconds and the desk says when it asks again.
13. **Every absence is said in words.** Not set up, offline, warming, not enough candles, quiet, reading, error, not
    yet passed its exam, the Lines scope, no 1-minute pane, no room at the right edge, a replay with no candles, and
    Nova's API not yet restarted after the update -- each has its sentence (`architecture/schema/ahead.md`).
14. **The routes are always registered.** Unset, the forecast route answers `not_set_up` and no request leaves Nova.

## Consequences

- At most one loopback request per symbol per completed minute while the switch is on and a 1-minute pane shows.
- The API has to restart after the update for the new routes, and a restart disarms the desk (ADR 018). Until it
  does, the desk says Nova's API has no Ahead yet.
- The report card is filled by the forecaster from later requests; it counts Live and Paper requests only, never Sim
  replays of past days the model may have seen. A score not yet made shows "— not scored yet", never a zero.
- The MACD fan costs one MACD run over the day's real closes and fifteen steps per path, done once per minute.
- Nothing trades on it. A bot, an alert or a veto built on Ahead would need its own ADR and the operator's decision.

## Rejected

- **The model inside the API process.** Its CPU and memory would compete with the order path in one process.
- **Future whitespace bars or a wider right offset** to make room for the zone: they add to the series or move a
  view the operator owns. The zone is placed by the time scale's own logical coordinates.
- **Forecasting the MACD directly.** It is worked out from the forecast paths with Nova's own MACD.
- **A stand-in drawn in place of the AI** when no forecaster is set up: Nova draws its own lines and says the rest is
  absent.
- **The backend working out lines, walls and odds** from its own stock read: it would rebuild that read in the order
  path's process and could disagree with the chart.
- **Keeping the last forecast on screen while the next is read:** its first minute is by then a real candle.
- **Routes absent when unset:** Nova's lines and the "not set up" sentence would have nothing to answer them.
