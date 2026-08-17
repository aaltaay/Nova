# 2026-08-07 — Paper scanners empty: quiet window + Error 10089 delayed fallback

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed | ibkr-ops
- **Related:** `CHANGELOG.md` §2026-08-07 — Paper scanners empty · `PROBLEM_LOG.md` §2026-08-07 — Paper scanners empty · ADR 008

## Task

Investigate empty scanners while paper Gateway was connected; decide if the user must switch to live or can keep paper-testing with paid live market data.

## Goal

Scanners populate on paper without forcing live-account order risk; explain paper vs live honestly.

## Why it mattered

Connected paper looked healthy (`connected=true`) while Gappers/Gainers/Losers stayed empty -- looked like "no market" and blocked paper testing.

## What we changed

- `in_ready_quiet_window` is timed-only (no forever wait on empty `_shadow`)
- Flipped `IBKR_SCANNER_PERSISTENT_AUTHORITATIVE=true` (ADR 008 cutover) so persistent leases own UI caches
- Detect IB Error 10089; fall back to `reqMarketDataType(3)` delayed quotes when live API MD is not entitled on paper
- ADR 008 status note + regression tests

## How it works now

1. Persistent scanner stream is authoritative; one-shot membership polls are skipped when discovery=ibkr.
2. READY still requests live MD (type 1). If IB raises 10089, `session_errors` marks live blocked + delayed; `scanner_stream.manager_loop` calls `client.maybe_fallback_to_delayed_market_data()` and switches to type 3.
3. Status shows `market_data_type=3` and `market_data_delayed=true` until live entitlements are shared with paper.
4. Orders stay on paper (`spend_status=paper_armed`) as long as Gateway is paper.

## Why this approach

- **Rejected "just switch Nova to Live Gateway":** gets paid MD, but orders become live-account risk unless spend gates stay locked -- worse for paper testing.
- **Rejected leaving shadow+one-shot dual pipeline:** empty-shadow quiet used `not []` (True forever); competing one-shot `TOP_PERC_*` timed out against the same clientId leases.
- **Delayed fallback over hard-fail:** paper can still show scanners for practice; UI already has delayed signaling. True live on paper still requires Account Management "share market data with paper."

## Verification

- `pytest tests/test_scanner_stream_quiet_window.py tests/test_ibkr_session_errors.py` -- 12 passed
- Separate clientId probe: live type 1 → Error 10089 empty quotes; type 3 → prices
- After restart: `/api/movers` → 49 gainers + 49 losers; status `md_type=3 delayed=true mode=paper spend=paper_armed`

## Follow-ups

- User: Client Portal → enable share real-time market data with paper trading account, then restart Gateway/Nova for live (type 1) on paper
- Optional UI banner copy for Error 10089 / delayed fallback (status fields already set)
- Today's Gappers may stay empty if they froze empty at 09:30 before the fix; Gainers/Losers are the RTH truth

## Keywords

paper, Error 10089, delayed, reqMarketDataType, quiet window, IBKR_SCANNER_PERSISTENT_AUTHORITATIVE, empty scanners, share market data
