# ADR 060 -- The Global page: where the world's stock money went, measured, never estimated

**Status:** Accepted · **Date:** 2026-10-20
**Builds on:** [[053-market-page]] (a read-only reference board, refused symbols stated per tile, the board's
requests kept off the stock session's flags) · [[054-quotes-someone-waits-on-read-a-brief-line]] ·
[[012-local-first-chart-bars]] (the paced historical service) · [[005-frontend-feature-slices]]
**Decided by:** the operator, 2026-10-15 and 2026-10-20 ("Does our dashboard show how much money entered and exited
the stock market? Like maybe have a new tab called Global that shows the entire world and how much money entered and
left each exchange"; mockups v1 and v2 as PNGs, v2 approved with both measures side by side -- "I think that would
be nice"; "We can use our ibkr for that of course"; "I want the tab to be above Market"; "we bought all the needed
data, we shouldn't have estimate unless we must, label those explicitly so we know they are not real").

## Context

Nova's Market page (ADR 053) reads the US market only. The operator wants one glance at the world: which markets
money is going into and out of, region by region, through the 24 hours as trading moves from Asia to Europe to the
US.

Every trade has a buyer and a seller, so no money literally enters an exchange. What can be measured is which side
was more eager -- trades at rising prices against trades at falling ones -- and in what size, and what the index did.
Two things cannot be measured live by any feed, IBKR included: an exchange's total market value and its total
turnover. IBKR also limits what Nova may ask: about 100 market-data lines shared with every platform the login uses
(53 learned on 2026-10-16), and 60 historical requests in 10 minutes, which sat full that morning until the Market page
was made to wait at 30 left (ADR 053 amendment, #1020). Reading every stock of 16 markets is out of reach.

## Decision

1. **A `Global` page, first on the nav rail, above Market** (`frontend/src/global_board/`, backend
   `backend/global_board/`). Read-only: it places, stages and cancels nothing and feeds nothing else. Nova still opens
   on the Scanner.
2. **Each market's money is the real trades of its own index futures, in its own hours.** One future per market
   (ES for the US, the DAX future for Germany, the Nikkei 225 future for Japan, ...), read as 1-minute TRADES bars
   through the paced historical service and kept to the market's own session: a bar closing above the one before it
   is up, below it down. Its notional -- volume x the bar's average price x the contract multiplier, at IBKR's own
   daily exchange rate -- is real money that traded. Pressure is up minus down, in dollars and as a share of all of
   it. A market with no index future on IBKR (Brazil, Saudi Arabia, South Africa, India, Taiwan), or whose future
   IBKR refuses, reads its US-listed country ETF instead -- real trades too, but US money in US hours -- and the row
   names it ("via EWZ") and shows IBKR's refusal.
3. **The second measure is the index move**, from the home index (a line held for a moment), else the home future,
   else the ETF, each labelled with its source. The v2 mockup's dollar "value change" (market value x the move) is
   dropped: it needs each exchange's total value, which no feed publishes live, and the operator ruled out estimates
   the page does not need. Bubble size is the money that traded in the market's instrument today, not the
   exchange's turnover. Nothing on the page is an estimate; were one ever needed, it would be labelled as one.
4. **One US row, not NYSE and Nasdaq apart.** The S&P 500's futures cover both exchanges' biggest stocks together;
   splitting the two would need every stock's trades.
5. **Global reads last.** It asks IBKR only while connected; it sends a historical request only while more than
   `GLOBAL_HISTORY_HEADROOM` (40) of the 60 are left -- after charts, the short check, the TraderTV exits, LULD and
   the Market page (30) -- under its own pacing kind, `global`, so the capacity strip names it; it opens a line only
   for a moment, through `ibkr.brief_lines`, and only with lines spare. Each read waits on the market's clock: an
   open market's flow every few minutes while the page shows, once more after its close, then nothing until its next
   session. Not shown, it keeps a slower cadence outside 09:30-16:00 ET only, so the desk's own hours are never
   shared with it, and its answers are kept across restarts.
6. **Its requests never touch the stock session's flags.** Futures, indexes and forex errors are recorded per
   instrument (`ibkr.reference_errors`, ADR 053 decision 3) and shown on the row; a refused instrument is not asked
   again for hours.

## Consequences

- The page shows where money is going from data the operator pays for. A future refused for a missing
  subscription shows on its row with IBKR's own words, and the row reads its ETF until the subscription is there.
- Futures pressure is the futures market's eagerness, not the cash market's: the row says which instrument it read.
  Bar-level up/down is coarser than trade-by-trade aggressor flags, which IBKR's limits rule out for 16 markets.
- Holidays outside the US are not in Nova's calendar; a market open by its clock on a local holiday shows no new
  bars, and its row says when the last one arrived.
- `request_reference_bars` returns each bar's volume and average price (additive) and takes a pacing kind, and the
  capacity strip's History hover gains "Global page".

## Rejected

- **Every stock's trades per exchange.** Thousands of lines or requests against a cap of about 100 lines and 60
  requests per 10 minutes.
- **Dollar value change from hand-kept exchange sizes.** Two published figures for Nasdaq a month apart differed
  by a fifth ($35.0T for May 2026, $43.6T for June), a hand table goes stale, and the result would be an estimate the
  operator did not want.
- **Switching the IBKR session to delayed data for markets without a subscription.** It is one setting for the whole
  connection, and the trading desk must never see a delayed quote.
