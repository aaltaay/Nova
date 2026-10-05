# 2026-10-05 — Venue defaults and bot snapshot batch review

- **Status:** review complete; implementation planned, not claimed or started
- **Agent:** parent
- **Domain:** frontend, execution
- **Related:** [#657](https://github.com/aaltaay/Nova/issues/657), [#658](https://github.com/aaltaay/Nova/issues/658)
- **Source base:** `67f5ab36` (includes the merged delivery repair #738)

## Task

Review #657/#658 against current code, issue comments and cooperative claims,
and prepare one grouped fix plan while respecting the operator's local agents.
The selected numbered prompt requests a plan; it does not start implementation.

## Goal

Identify the unfinished scope without repeating #661 or #665. Resolve the
remaining routine preference choice using the operator's standing instruction
to infer decisions where possible, and provide concrete agent boundaries and
completion checks.

## Why it mattered

The original issue bodies list several faults already repaired. Acting on the
bodies alone would repeat account, risk, lock and allowlist work. The remaining
preference is still global, and the bot poller has no venue identity, so a
switch can display the previous venue's bot state and retain its ticket defaults.

## What changed

Only this review record and the task-log index. Product code, issue state,
assignments, claims and the authored backlog configuration were not changed.

| Scope | Fresh finding |
|---|---|
| #657 account/orders snapshots and Who trades | Implemented by merged #661; current account code clears on known venue changes and rejects other-venue rows. Retain its regressions. |
| #657 risk per trade | Implemented by merged #665 / ADR 042 through the venue sleeve. |
| #658 day locks, caps and bot stock list | Decided and implemented by #665; current buy-lock, sleeve and venue-level owners confirm the separation. |
| #657/#658 trade defaults | Still one `nova.trade.defaults.v1` record; Settings, compact-ticket TIF and submission read it without a venue. |
| #657 bot snapshot | Still lacks a venue stamp; HTTP and shared snapshots are accepted without venue validation. Its epoch protects against writes, not venue changes; refresh during an in-flight read is dropped. |

The ticket also seeds its defaults on symbol changes, while a venue change
only resets submission. Settings and compact TIF retain local React state.
The fix must update mounted consumers, not only the storage key.

## How it works now

The plan is one batch, `venue-defaults-and-bot-snapshots`, with proposed PR title
`fix(desk): keep trade defaults and bot snapshots on their own venue`.
Both issues remain open until all remaining scope is implemented and verified.
The accepted implementation would use `Closes #657` and `Closes #658`.

1. **Trade defaults:** keep independent Live/Paper/Sim stock-order defaults with
   a versioned storage contract. All readers and writers use the explicit,
   confirmed desk venue, including Settings, ticket seeding, compact TIF,
   protective-leg/submission defaults and chart/setup ticket entry points.
   Mounted consumers update on venue and preference changes, including other
   windows. Pending/unknown venue never means Live or a Gateway-mode guess.
2. **Legacy migration:** adopt the old shared preference once into the current
   confirmed venue, as the existing legacy risk migration does. Other venues
   start from existing factory defaults (DAY, optional legs off). Existing
   venue records win; migration waits for a known venue and preserves the
   legacy source if persistence cannot be verified. Do not clone practice
   customization into all three venues.
3. **Bot snapshots:** use one confirmed venue-change source and a generation
   token. Clear old bot state on transition, refresh immediately, queue a
   refresh if an older read is still running, and reject old-generation GETs,
   mutation replies and shared snapshots. Validate the session's existing
   `level_venue` evidence. Reuse the shared polling leader rather than creating
   one network poller per consumer. Notify other windows when the backend
   confirms a switch; follow the explicit venue, not the Gateway mode.
4. **Delivery:** one cooperative batch claim after rechecking current owners,
   one isolated implementation branch from freshly fetched master, one ready
   PR. Amend the relevant ADR/SOP before code; add the authored batch and file
   footprint when implementation begins. Cross-feature consumers use public
   barrels. Do not claim issue closure from a partial poll-only fix.

## Why this approach

Choose per-venue trade defaults under the operator's grant for routine decisions:
practice order lifetime and TP/SL choices should follow the venue that was
configured, matching the existing sleeves and locks. The deliberately shared
place-confirmation preference remains outside this repair, as the issue's
later comment states. No further operator choice is required for this batch.

Agent A can own preference storage, migration, Settings, ticket consumers and
their tests. Agent B can own the venue notification contract, bot poller,
HTTP/share/mutation fencing and their tests. Agree the confirmed-venue contract
before edits; keep separate isolated worktrees and combine reviewed commits
into the one delivery PR. The coordinator owns ADR, batch metadata and merge
integration. Existing backend locks/caps/allowlists provide regression coverage,
not another implementation scope.

## Verification

- Fresh issue bodies and every comment were fetched; #661/#665 were re-read as
  merged, and relevant current source owners were inspected on `67f5ab36`.
- GitHub returned no open PRs or issues labeled `claimed` at review time.
  Unpublished desktop work cannot be inferred from this; recheck before claiming.
- Required implementation tests: distinct venue defaults; one-time/failed/corrupt
  legacy migration; same-symbol mounted ticket and Settings switches; same-window
  and storage-event propagation; stale HTTP/mutation/shared responses; Paper →
  Live → Paper with an old read finishing last; failed refresh and in-flight
  queuing; explicit Live venue on the legacy IBKR Paper Gateway; sample isolation.
- Retain account/Who-trades, protective-leg/confirmation, day-lock/sleeve/list
  neighbors; run scoped Vitest, frontend type/build and lint, plus required
  documentation/architecture checks. No product tests were run for this plan-only
  review and no broker or trading-PC action occurred.

## Follow-ups

Execute the agreed grouped batch when implementation is requested, rechecking
claims and fresh PR file scopes before assigning agents. Verify the complete
remaining scope before marking either issue complete.

## Keywords

venue, preferences, TIF, protective legs, bot snapshot, late response, migration,
grouped PR, local agents, #657, #658
