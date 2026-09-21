# ADR 020 -- Three venues on one feed: Live, Paper (Nova-managed), Sim (replay playground)

**Status:** Accepted · **Date:** 2026-09-21
**Builds on:** [[018-desk-venue-vs-spend-arming]] · [[019-practice-fills-on-replayed-sessions]]
**Supersedes:** the ADR 019 amendment "the live edge" (2026-09-21, withdrawn the
same day before any code shipped for it -- its intent, fake money on the live
feed, is the Paper venue below)

## Context

On 2026-09-21 the operator's IBKR paper login could not carry the tape: the
paper account inherits the live user's market-data subscriptions only through
"share real-time market data", the share reached L1 and Level 2 but tick-by-tick
came back `10168 not subscribed`, and IBKR's own rule that only one of the two
usernames may hold an active session made live and paper mutually exclusive.
The operator's decision: Nova stops relying on IBKR's paper account. Live data
comes from the live Gateway; fake-money trading is Nova's own account,
"literally very similar to live"; the replay desk is a playground where bots
and the operator trade recordings and can unwind time.

## Decision

1. **Three venues, one data door.** The desk venue is `live | paper | sim`,
   persisted by `sim/mode.py` in `desk-venue.json` (`schema_version: 2`,
   `{"venue": ...}`; the v1 shape migrates; unknown versions refuse loud, ADR
   018). Market data comes from the live Gateway (port 4001) in every venue
   that needs a feed. The IBKR paper Gateway (port 4002) is **legacy**: it stays
   reachable from the Desk checklist as "IBKR paper Gateway (legacy)" and is
   never what the Paper venue means.

2. **Paper is Nova's practice account on the live feed.** Orders enter
   `execution.service.execute` exactly as on Live (ADR 007); `broker_send`
   routes the Paper venue to the practice broker with the **live reference**:
   L1 last (fresh within `PRACTICE_LIVE_FRESH_SEC`), the live top of book from
   the depth state, and live tape prints for resting orders. The account is a
   persistent ledger (`practice-paper.json` under the operator cache, owner
   `practice/ledger.py`, `schema_version`), with IBKR-like commissions and
   regulatory fees, **enforced** buying power, day P&L that rolls at 04:00 ET,
   per-source attribution (`source`, bot id) on every row, and a reset that
   archives the old ledger instead of deleting it. Nothing is invented: the
   fill, fee and margin conventions follow the surveyed practice simulators
   (`architecture/practice-account.md`).

3. **Sim is the replay playground.** The same practice broker runs on the
   loaded replay's reference (ADR 019, unchanged rules), against a **scratch,
   event-sourced** account: every order and fill is stamped with replay time,
   scrubbing backwards unwinds everything placed after the new playhead (it
   never happened), and unloading the replay or loading another day clears the
   account. Bots trade a replay exactly as they trade Paper or Live.

4. **The venue never changes the bot or the operator.** Arming (ADR 018),
   autonomy level, Activate, allowlist, heartbeat and breakers gate identically
   on every venue; the venue only decides where the fill comes from. Spend
   status reads `paper_armed` / `sim_armed` when the latch is armed. The IBKR
   env gates (`IBKR_ORDERS_ENABLED`, `IBKR_LIVE_TRADING_CONFIRMED`) apply to
   Live only; fake money needs no `.env` permission, only the arm.

5. **Every practice fill is an estimate and says so** (`fill_estimated: true`,
   `fill_basis`), on Paper and Sim alike. A practice fill is never shown as a
   recorded print.

## Contract (agents build to this)

- `GET /api/practice/account?venue=paper|sim` →
  `{venue, account_id ("NOVA-PAPER" | "NOVA-SIM"), starting_cash, cash,
  buying_power, net_liquidation, gross_position_value, realized_pnl,
  unrealized_pnl, day_pnl, day_started_et, commissions_today, positions:
  [{symbol, qty, avg_cost, mark, unrealized}], working: [...order rows...],
  fills_today: integer, schema_version, updated_at}`; Sim adds `replay_key`.
- `POST /api/practice/reset` `{venue, starting_cash?}` → the new account;
  Paper archives the old ledger as `practice-paper-<YYYYMMDD-HHMMSS>.json`.
- `/api/ibkr/account` and `/api/ibkr/positions` answer from the venue's
  practice account when the venue is `paper` or `sim` (existing
  `sim/account_hooks.py` extended).
- `/api/ibkr/status`: `mode` ∈ `live | paper | sim` (paper = Nova paper),
  plus `venue` (the same value, explicit), `account_id` = `NOVA-PAPER` /
  `NOVA-SIM` on the practice venues, `spend_status` as in 4.
- Practice refusals: existing `SIM_*` codes on Sim; Paper adds
  `PRACTICE_NO_LIVE_PRINT` (no fresh L1 last and no recent tape print --
  never a guess) and both venues add `PRACTICE_BUYING_POWER`.
- `fill_basis` values: `quote | last_print | print_cross | stop_trigger |
  last_mark` (Sim, ADR 019) and `live_quote | live_print` (Paper at
  placement); resting fills on either venue use `print_cross` /
  `stop_trigger`.
- Constants live in `backend/constants_practice.py` (mirrored where the
  frontend needs them); tunables include starting cash, fee schedule, margin
  multipliers, freshness.
- Frontend: the header pills are **venue** pills (Paper switches the venue,
  never launches a Gateway); the Paper banner reads that orders go to Nova's
  practice account, fake money, live data; the account cluster shows the
  practice account's numbers; a Reset action lives in Settings > Trade.

## Consequences

- Paper works whenever the live Gateway does, with the full tape, and never
  fights the live login for a session.
- The operator owns the account: starting cash, reset, fee realism. Results
  are only as honest as the fee and margin model, which is why it is surveyed
  and written down rather than assumed.
- Sim gains time travel for the account, not only the tape.
- The IBKR paper Gateway loses its header pill; its IBC login stays usable
  from the Desk checklist for the rare day the operator wants IBKR's own fills.

## Rejected alternatives

- **Keep IBKR paper as the Paper venue.** No tick-by-tick, exclusive with the
  live session, and IBKR's eligibility rules outside the operator's control.
- **Sim "at the live edge"** (ADR 019 amendment). Two venues for one job; the
  clock as a venue switch confused what "Paper" means. Withdrawn.
- **One wallet for Paper and Sim.** A bot that trades a replayed open and then
  the real one produces a P&L nobody can read.
- **Bespoke fill and fee rules.** The practice simulators people actually use
  agree on the conventions; Nova adopts them and names its parameters.
