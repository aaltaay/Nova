# ADR 054 -- A quote someone waits on is read from a line held for a moment, not a snapshot

**Status:** Accepted · **Date:** 2026-10-13
**Amends:** [[040-cryptos-page]] (decision 3: the bridge stocks' last trades) · [[053-market-page]] (its 2026-10-13
amendment: the line held for a moment moves to `ibkr/` and is shared) · [[010-ib-loop-isolation]] (the inventory rows
for `ticker_ibkr.py` and `ibkr/reprice.py`)
**Builds on:** [[026-performance-recorder]] (the perf record every number below comes from)
**Decided by:** the operator, 2026-10-13 13:29 ET, on the Market page: "everything is frozen, data is so so so slow.
has this never been measured?" PR #912 fixed that page and asked for every other read a person waits on to be
measured and moved the same way. The design is the agent's.

## Context

IBKR answers a snapshot (`reqTickersAsync`) only at its snapshot end when a field it waits for never comes. For a
stock that happens from midnight until the regular session opens. The perf record times every
`ibkr.snapshot_quotes` call (one or more batches of 5). Calls alone in a 5-second sample, by window:

| Day | 00:00-04:00 ET | 04:00-09:30 ET | 09:30-16:00 ET | 16:00-20:00 ET |
|-----|----------------|----------------|----------------|----------------|
| 10-08 | median 20.0 s, 3% under 4 s | median 11.0 s, 0% under 4 s | 0.6 s, 99% | 0.5 s, 99% |
| 10-09 | 11.0 s, 11% | 14.2 s, 5% | 4.6 s, 31% | 0.0 s, 100% |
| 10-12 | 11.1 s, 0% | 11.1 s, 0% | 4.6 s, 33% | 1.3 s, 96% |
| 10-13 | 0.0 s, 81% | 11.4 s, 2% | 1.5 s, 86% | -- |

Premarket, even the quickest tenth of the calls took 11.0 s. The operator trades 07:00-10:00 ET. A median of 0.0 s
is calls that gave way to a chart load in the cold slot (`ib_scheduler.cold_slot`) and asked IBKR nothing. That slot
is single-flight: a snapshot also queued there behind HOD Momo's own 11 s batches.

After PR #912 three reads a person waits on still asked for a snapshot:

1. **The Trader's quote head** (`ticker_ibkr.fetch_ticker_snapshot_ibkr`). When no scanner row, Level 1 line or
   today's stored bar has a price, the first frame of `/ws/ticker/{symbol}` waited for a snapshot capped at 4 s.
   Premarket 0-5% of snapshots answered in 4 s, so the head waited 4 s and got nothing.
2. **The ticker-detail backstop** (`ibkr/reprice.reprice_detail_symbols`). Every 3 s, for an open Trader whose line
   was quiet for 8 s, it snapshotted the symbol: ~11 s premarket, a line and the cold slot held for it, so the panel's
   backstop came every ~14 s. The symbol usually had its own line open already.
3. **The Cryptos page's bridge stocks** (`crypto/ibkr_reads.quotes`): eight stocks in two batches, ~23 s premarket.
   The page is open around the clock, and its daily closes and listing check waited behind that read on one thread.

Not a person waiting, unchanged here: HOD Momo's enrichment (#891), the movers and after-hours scan-loop reprices
(`discovery._get_movers`, `scanner_runners/afterhours`) and scanner hydrate. Their rows arrive from scans and stay
live on Level 1 lines.

## Decision

1. **One shared read: `ibkr/brief_lines.py`** (moved from `market_board/`, its rules kept). At most
   `IBKR_BRIEF_LINE_BATCH` (5) lines are open at once, **every reader together**, and each takes IBKR's first ticks
   and is cancelled at most `IBKR_BRIEF_LINE_WAIT_SEC` (2.5 s) after it opened. The single cold slot used to run one
   snapshot batch at a time; brief reads run side by side, and `spare_lines` counts only the desk's own lines, so
   without a shared count the four readers could hold ~13 lines. A reader waits its turn: at most one batch, 2.5 s.
   - A line someone else holds is never cancelled. A contract the desk already streams is read from its own ticker,
     with no request and no spare line needed.
   - A line the desk joins during the read is left open for the desk.
   - A line this read opens starts from a cleared ticker, so a price it returns is this line's.
   - No line opens with fewer than `IBKR_BRIEF_MIN_FREE_LINES` (6) free beyond Nova's own reserve
     (`IBKR_L1_STREAM_RESERVE`, kept for an opening Trader tab). The read raises `NoHeadroom` instead.
   Each read is timed as `ibkr.brief_lines`.
2. **Stocks** (`brief_lines.stock_quotes`) answer in `snapshot_quotes`' own shape (`quote_rows.quote_from_ticker`):
   with no print by the deadline the price is IBKR's prior close, flagged `close_fallback` (#541).
   - **A stock is priced by a print, not a quote.** In the first probe (PLUG, 14:10 ET) the quote and the prior close
     came first, and the Market page's rule (a quote prices a line) returned no last trade.
   - **A stock's line asks the desk's own generic ticks** (`IBKR_L1_GENERIC_TICKS`). When the desk subscribes a
     contract that already has a line, ib_async hands it that line's ticker without a new request and without its
     generic ticks. Mid-read the desk therefore keeps a line carrying RTVolume, the day volume its candles count.
     A snapshot was never joined this way: ib_async keeps snapshots out of its one-line-per-contract index.
3. **The three readers move to it**, each timed in the perf record:

   | Read | Op | With too few spare lines |
   |------|----|--------------------------|
   | Quote head | `ticker.cold_quote` | No read; the desk's own line, opened from the reserve, fills the head |
   | Detail backstop | `ibkr.detail_reprice` | The pass is skipped |
   | Cryptos bridge stocks | `crypto.bridge_quotes` | The page says "waiting for spare market-data lines" |

   Every Cryptos read is now timed as `crypto.<read>`, and the time from the page opening to its first answer as
   `crypto.first.<read>`, the way the Market page's are. The Market page keeps its reads and its bars fallback.

## Measured

The probe was read-only, on its own Gateway client id (94, never Nova's 17), with at most 5 lines open. It took each
read both ways, alternating which went first.

| 2026-10-13 ET | Snapshot | Line held for a moment |
|---------------|----------|------------------------|
| 14:10, 14:25 (session): bridge stocks, 8 | 0.71-1.49 s | 0.72-1.73 s |
| 14:10, 14:25 (session): SOFI, PLUG, F, one at a time | 0.11-1.21 s | 0.10-0.88 s; every one with its last trade since the print rule |
| 14:28 (session): ES, NQ, CL, GC | 0.43-0.59 s | 0.45-0.98 s |

In the session the two answer alike. Premarket a brief line ends within 2.5 s by construction, answered or not. The
snapshot it replaced held the head 4 s for nothing and the other two ~11 s a batch. The same probe at 04:10 and 07:30 ET on
2026-10-14 is recorded on the pull request that made this ADR. From the desk's next start the four ops above give
the numbers directly.

## Consequences

- At most 5 lines for 2.5 s, where a snapshot held up to 5 for ~11 s premarket: line-time falls. The peak is unchanged.
- A line IBKR refuses (another platform on the login took the lines between the headroom check and the request) is
  a quote with no price, as a refused snapshot was.
- Rejected:
  - a longer cap on the quote head's snapshot (a person would wait 11 s);
  - waiting on the desk's own Level 1 line alone (the REST path and the detail backstop have no line of their own,
    and when the desk's line exists the brief read borrows it at no cost);
  - leaving the Cryptos bridge on snapshots (the page is used most outside the session).
