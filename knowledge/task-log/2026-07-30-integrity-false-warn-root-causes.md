# 2026-07-30 -- Integrity banner false warn root causes

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo | market-feed | ibkr-ops
- **Related:** `CHANGELOG.md` §2026-07-30 Integrity banner · `PROBLEM_LOG.md` §2026-07-30 Integrity warn false positives

## Task

Stop the Integrity warn/fail banner from scaring the user on healthy sessions. Do not hide or silence it -- fix why the warnings occur. Include IBC for the daily Gateway re-auth.

## Goal

A green (hidden) banner when the feed is healthy; a loud banner only when Gateway needs login or the feed is genuinely dead.

## Why it mattered

The banner was product-hostile: recurring yellow/red on afterhours and with a chart open made the scanner look broken while HOD was LIVE and alerts were firing.

## What we changed

- `scanner_l1_stream` uses socket event liveness (`ticks_handler.get_last_event_ts`), not price-change recency
- Session-aware HOD tick warn thresholds (RTH 3s, extended 12s; closed = pass); warmup 90s
- Wire `is_delayed_data()` / `max_tickers_hit()` into evaluators (informational, not alarm)
- Surge seed: requeue transient failures; classify `no_history`; open-chart 503 no longer scars the session
- Extracted `ibkr/ticks_handler.py` (file-size)
- Local IBC: `AutoRestartTime=23:45`; registered Windows task `NovaDailyStart` at 06:00

## How it works now

Integrity overall status is still worst-of-all-checks. False triggers (flat quote, thin AH tape, chart contention, illiquid no-data) no longer produce warn/fail. Real Gateway disconnect and 15s hard-stale still fail. Daily Gateway logout is handled by IBC auto-restart + morning NovaDaily task (phone 2FA may still be required).

## Why this approach

Rejected "self-heal by clearing sticky errors only" and "mute the banner" -- user wanted root-cause prevention. Rejected auto-restarting scanner loops (accuracy-only). Measuring price-change as liveness was the largest false positive; fixing the variable is cheaper and more correct than widening thresholds alone. Delayed-data was already detected in `session_errors` -- wiring it in avoids pretending Nova is broken when IBKR line limits apply. Seed retry bounded at 3 keeps pacing safe while fixing chart contention.

## Verification

`py -3 -m pytest` on integrity, surge_seed, engine, session_errors, scan_runners -- 65 passed. Maintainer checks: `ticks.py` under 400 after extract.

## Follow-ups

- Align local IBC `TradingMode` with Nova Live if trading live (was paper)
- Optional UX: GATEWAY chip vs account "IBKR offline" are different signals -- unify or label clearer
- Confirm live market-data line limit vs L1 budget if delayed-data flag stays sticky in RTH

## Keywords

Integrity, hod_ticks_flowing, scanner_l1_stream, surge seed, HistoricalBusy, delayed data, IBC AutoRestartTime, afterhours
