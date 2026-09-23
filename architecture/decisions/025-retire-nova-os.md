# ADR 025 -- Retire Nova OS: the verdict, the Signal / Confirm / Auto Paper modes and the approval queue

**Status:** Accepted · **Date:** 2026-09-23
**Supersedes:** the Nova OS P2-P5 and P9 decision / execution layers (Nova-OS-Status.md), the Phase D executor
**Builds on:** [[007-execution-service]] · [[016-bot-localhost-api]] · [[022-setup-scanner-tape-gate]]
**Resolves:** #481 as option (a), retire (operator decision, 2026-09-23)

## Context

Nova OS was the July decision layer: `nova_os.decide()` judged every watchlist
name through ordered gates into `BUY | WAIT | NO_BUY`, and a control-mode
ladder (`signal | confirm | auto_paper`) decided whether that verdict was only
shown, staged as a ticket for the operator to approve, or placed as a paper
bracket by the Phase D executor (`strategy/executor*.py`).

By September none of that carried weight:

- The verdict judged every name against **Gap and Go** (`NOVA_OS_PRIMARY_SETUP`),
  a setup that failed gate 1 of the Bot-Trading-Plan. The setup scanner (ADR 022)
  replaced it with the first pullback, a tape read and a scoreboard.
- ADR 022 retired `strategy/setups_stream.py`, the only caller of
  `executor.on_signal()`. The staged queue never filled again, and Confirm / Auto
  Paper had nothing to act on. #481 asked the operator to retire the executor or
  feed it; the operator retired it.
- The same ladder was drawn three times (Watchlist > Automation, the Trader
  action bar, the attention strip's help text) beside the bot's own
  Off / Eyes / Strategy + Activate ladder (ADR 016). Two automation paths for one
  strategy is one too many.

## Decision

### 1. Removed

| Piece | Where it lived |
|-------|----------------|
| The verdict | `nova_os/decide.py`, `nova_os/gates.py`, `GET /api/nova-os/decide*`, `GET /api/nova-os/policy`; Watchlist > Decision; the Trader dock's "Nova OS" tab |
| The decision replay | the `decide()` half of `archive/replay.py` (its bar reads stay for the backtest), `archive/evening_review.py`, `GET /api/archive/replay|walk|review/*`; Watchlist > Archive |
| The mode ladder | `nova_os/control_mode.py`; Watchlist > Automation; the Trader action bar's Signal / Confirm / Auto Paper controls |
| The approval queue | `nova_os/staged_tickets.py`, `/api/strategy/executor/staged*` |
| The Phase D executor | `strategy/executor.py`, `executor_place.py`, `executor_flatten.py`, `executor_cancel.py`, the fill poll loop, `nova_os/recovery.py` (startup recovery of executor positions), `/api/strategy/executor/*` |
| The Automation hotkeys | approve / reject staged, raise to Confirm, drop to Signal, open Flatten, Stop Automation (System 1). Nova Actions (System 2) are unchanged. |
| Execution sources `approve` and `auto_paper` | a new command naming either is refused `SOURCE_INVALID`; ledger history that carries them still reads |

The bot's ladder (ADR 016) is now the only way a strategy places, and the setup
scanner (ADR 022) stays Eyes only.

### 2. Kept

- **The kill switch latch** (D-037) moves to `backend/kill_switch/` unchanged in
  meaning: a persisted latch that `execution.service.execute` checks before every
  non-protective place or bracket from any source, manual included, and that only
  an explicit reset clears. Tripping it latches first, then cancels every open
  order on the account. Routes: `GET /api/kill-switch`, `POST /api/kill-switch`
  (trip), `POST /api/kill-switch/reset`. Its control is a card on the Bots page.
  The header's Emergency KILL (bot to L0, desk lock, cancel, flatten) is a
  separate composite and is unchanged.
- **The event log** (`nova_os/events.py`, `events_db.py`, `codes.py`) stays: it
  still records kill switch trips, risk halts and archive-health failures, and it
  feeds the attention strip and the alert channels. Renaming the package is a
  later, mechanical change.
- **The NYSE holiday table** (`constants_nova_os.NOVA_OS_NYSE_HOLIDAYS`) stays:
  the leaderboard recorder and the Sim trading calendar read it.
- **The walk-away rules** (`strategy/risk.py`: daily max loss, consecutive
  losses, half-peak giveback) stay as they are. Before this ADR only the executor
  consulted them -- the manual ticket and the bot both pass `skip_risk=True` -- so
  after it nothing is gated by them. Whether they should gate manual and bot
  orders, or be removed, is an operator decision recorded on the delivering PR;
  this ADR does not change who they gate.
- The Journal, Backtest and cold-archive storage (compaction, R2 upload, day
  listing) are unchanged.

## Consequences

- Watchlist keeps Watchlist, Setups, Journal and Backtest.
- The event log (`nova_os_events.db`) history stays readable; no new decision, staged or
  executor rows are written.
- A tripped latch from before the upgrade is still read from the same cache file
  (`KILL_SWITCH_STATE_FILENAME`, same `schema_version`) and still blocks until
  reset from the Bots page.
