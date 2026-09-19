# IMCC historical replay acceptance (D-052)

Target: IMCC, 2026-09-18, 04:00–09:30 America/New_York, half-open.
Same branch retained by explicit user instruction. PR #295 is merged; #294 is
open and carries this implementation. Order gates are unchanged.

## Acquisition evidence, 2026-09-19

Read-only Gateway qualified SMART/USD stock IMCC, NASDAQ, conId 912275669.
Durable storage: `F:\Nova\sim\_capture\historical\replay.sqlite3`.

- Trade job `386c1de699e51e11ff033029` **completed**: 279,573 prints in 271
  paced pages (11 s interval, client 29420), first print 04:00:00, last
  09:29:59, cursor exactly 09:30:00. Ordinals are contiguous 0..279,572,
  timestamps ascending, all inside [04:00, 09:30).
- Candle job `41a0f90361e4e241157a0c5a` completed with 330 one-minute bars and
  17,919,815 shares (one bounded, read-only request on client 29421).
- Identical prints are preserved: 22,832 repeats of an earlier
  (time, price, size, exchange, conditions) tuple. The busiest second holds
  540 prints, so pages routinely exceeded 1,000 rows to finish a second.

## Reconciliation, full window

| Measure | Shares |
|---|---|
| All downloaded prints | 23,446,163 |
| Prints IBKR marks `unreported` (204,162 odd-lot/Form T `TI`/`FTI`) | 5,526,348 |
| Reported prints | 17,919,815 |
| IBKR 1-minute bars (330) | 17,919,815 |

Reported-print volume equals IBKR bar volume in **every** minute (0 of 330
minutes differ). Aggregating only reported prints reproduces IBKR's open, high,
low and close in every traded minute (0 mismatches). Including unreported
prints would disagree in 220 of 280 traded minutes and invent highs, e.g.
04:02 high 2.00 against IBKR's 1.88. Replay therefore builds candles, last
price and volume from reported prints, lists every print in Time & Sales, and
marks unreported ones. The raw archive keeps all prints unaltered.

An earlier partial comparison differed by another 200 shares at 04:12 against
cached bars; a fresh IBKR bar request removed it. Historical data revisions and
cache age must be checked before attributing a mismatch to replay aggregation.

## Browser evidence

The existing chart verification page was opened with `external-api=1` on a
separate Vite/API pair (4174/8003), using actual persisted IMCC data and the
production SimSessionHeader, chart hooks, HistoricalQuoteTape and snapshot hook.
The acceptance API exposes only SIM controls and chart reads, no order routes.
This is component integration proof, not a claim that the already-running
operator backend has reloaded the new code.

- The default header displayed 04:00–20:00 and a 960-minute slider.
- Selected the persisted IMCC 04:00–09:30 job with **Use this window**, then
  **Load replay**. The header switched to HISTORICAL and its custom 330-minute range.
- At paused 04:00:00, one partial candle showed price 1.85 and volume 600.
  Time & Sales showed three reached prints, sizes 390, 10 and 200, all at
  04:00:00. Last price was 1.85; no historical quotes or depth were fabricated.
  (Captured before the reported-only candle rule; candle values at later
  minutes now equal IBKR's bars as reconciled above.)
- Advanced the paused slider to 05:39. Only reached candle/indicator data appeared.
  Rewinding to 04:00 removed later candles and restored the 04:00 state.

## Limits

Timestamps have one-second precision and preserve provider order inside each
second; no subsecond chronology is invented. Data availability depends on IBKR
qualification, permissions and retained history. No market-wide preload is claimed.
A 1-minute-only download cannot reconstruct 10-second candles; those require
prints or existing genuine 10-second bars. Missing intraday events use closed
OHLCV only. Minutes whose only prints are unreported have no replay candle.
Full scope remains Refs #292.
