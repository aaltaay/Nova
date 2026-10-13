# 2026-10-13 — Level 2 stuck on "Waiting for book data…" (IBKR 309 audit)

- **Status:** audit complete; no code changed
- **Agents:** parent
- **Domain:** market-feed, execution
- **Related:** ADR 045 (market view / order gate) · ADR 023 (auto-record yields lines) · #540 · #562

## Task

Operator report, 11:21 ET: BKYI's Level 2 showed "Waiting for book data…" for 30+ seconds while
Time & Sales was LIVE. The operator asked for an audit trail of why before any fix, and stated the
standing rule: if the market on screen is not live, the operator must not be able to trade.

## Goal

Name the exact failure, with log evidence, and every place Nova let it pass silently.

## Why it mattered

The desk looked healthy (socket "subscribed", heartbeats flowing, no error badge) while there was
no book at all. The order lock and the backend order gate both treated that state as live.

## What we found (audit trail)

All times ET, `backend/logs/blast.log*`.

1. **IBKR refused the line; Nova logged success.** `11:21:29.006 IBKR: subscribed depth for BKYI`,
   then `11:21:29.374 Error 309: Max number (3) of market depth requests has been reached [BKYI]`.
   `ibkr/depth/subscribe.py` logs "subscribed" right after `reqMktDepth` returns, before IBKR answers.
2. **The 309 is dropped.** `ibkr/depth/handlers.py::on_ib_error` acts only on 10092 (no depth → L1)
   and 317 (book reset). A 309 leaves the symbol in `state._subscriptions`, so
   `/api/ibkr/depth` lists it, `needs_subscribe()` is False, nothing retries, and no viewer is told.
3. **The socket says "subscribed" and beats forever.** `routes/trading_depth_ws.py` sends
   `subscribed`, then a `beat` every `MARKET_VIEW_BEAT_SEC` (0.25 s) with `seq: 0`. A live probe at
   11:31 on BKYI and ABLV: `{'subscribed': 1, 'book_watch': 1, 'luld': 1, 'beat': 15}` in 4 s,
   **zero `book` frames**. The ladder's `depthEmptyMessage` shows "Waiting for book data…" (connected,
   no error), forever.
4. **The order lock does not trip.** `frontend/src/market_view/viewRegistry.ts::viewLockReason`
   locks on silence, slow transit, or an undrawn newer book. Beats keep `lastWordWall` fresh and no
   book ever arrives, so none of the three fires: orders on BKYI stay enabled with no Level 2.
5. **The backend gate does not refuse either.** `market_view/gate.py::_lag_ms` returns `(None, False)`
   when the stamp's `book` is null (nothing drawn), so `check()` passes an order priced from no book.
6. **Reconnect bookkeeping vouches for dead lines.** On the 11:30:30 IBKR connectivity restore (1102),
   `IBKR depth: ABLV's Level 2 line survived the connectivity restore (IBKR kept it)`. ABLV's line had
   been refused with 309 at 11:25:06; it never existed.
7. **IBKR does not always answer.** BKYI's retry at 11:30:35 got neither a grant (2152) nor a 309, and
   still no books at 11:31. Error codes alone cannot detect a dead line.

### Who used the 3 depth slots

- Auto-record (`capture.feed_hold` / `leaderboard.auto_record`) opens a symbol's depth, holds it
  ~0.75 s, releases it, and moves to the next, about one every 1–3 s (11:17:50–11:18:14: PDSB, ZURA,
  ABLV, ENSC, LIFE, LOFD, SNK, TEAD, YMAT, AEC, CGNG, CRMG, FGI, HTCO, ITOC, NCT, SNDQ, XTND, YJ).
  The Level 2 the operator opens competes with that churn for the same 3 slots.
- 309 counts per log: Oct 12 = 0; Oct 13 = 6 (08:21–10:56) and 24+ (10:56–11:31). First 309 at
  **10:29:11** (AEC).
- After the 11:19:29 API restart (new Gateway connection, Nova holding nothing), exactly one request
  was granted (NB 11:19:52) and every other got 309: **2 of IBKR's 3 slots were held outside this Nova
  process.** One freed when NB was cancelled (YHC granted 11:26:07). Who holds the other 2 is not
  provable from Nova's side (IB Gateway logs are encrypted). Today's 1100/1102 connectivity blips at
  09:30 (×2), 09:40 and 11:30 precede the first 309 and are the leading suspect: a cancel lost
  during a blip would leave a slot held for the Gateway session's lifetime. A Gateway restart would
  confirm or rule this out.
- Tick-by-tick has the same pressure: `11:31:09 Error 10190: Max number of tick-by-tick requests has
  been reached [YHC]`.

### Incidental

- Two TCP connections to IBKR servers (`64.190.197.40`, `8.17.22.31`, `103.38.91.3`) are still
  ESTABLISHED, owned by PIDs 64016 / 53336, which no longer exist; their connections date from the
  previous IB Gateway instance (10/11–10/12). Not shown to hold depth (no 309 before 10:29 today).

## Why this approach

Audit only, at the operator's request. Fixes are proposed below, not applied, so the operator can
pick the policy (especially the trading lock) before code moves.

## Verification

- `curl /api/ibkr/status`: `connected`, `market_data_type 1`, capture ABLV `l2: 0, quotes: 0`.
- `curl /api/ibkr/depth` → `["ABLV","BKYI"]` while both had zero books.
- WebSocket probe of `/ws/ibkr/depth/{BKYI,ABLV}` for 4 s each: beats only, no books.
- Log greps quoted above.

## Follow-ups (proposed fix, one PR)

1. Treat 309 as a refusal: drop the slot, push an `error` to viewers with a plain reason
   ("IBKR's 3 Level 2 lines are in use: …"), and let auto-record yield to the operator's ladder.
2. First-book watchdog: a line with no book within N s of subscribe is dead → error to viewers,
   cancel, retry with backoff. Covers the silent case (finding 7).
3. Order lock on "no book": `viewLockReason` locks while a Level 2 is open with no book received;
   `gate.check` refuses an order whose stamp has no book when the symbol has a live depth line.
4. `drop_stale` / "survived" only for lines that delivered at least one book.
5. Throttle auto-record's depth churn (and tick-by-tick) so it never competes with an open ladder.

## Keywords

level 2, depth, 309, max market depth requests, waiting for book data, auto-record, feed_hold,
order lock, ADR 045, view gate, beat, stale book, BKYI, ABLV
