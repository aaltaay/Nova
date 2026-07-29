# 2026-07-28 -- Phase K short entry defined in roadmap (not started)

- **Status:** completed
- **Agents:** parent (in-session, zero-hop)
- **Domain:** roadmap / governance / execution-planning
- **Related:** `CHANGELOG.md` 2026-07-28 "Phase K short entry defined in roadmap" · `Nova-Roadmap-Status.md` Phase K ledger entry

## Task

User asked to add a short-entry phase to the detailed roadmap: testability, validity, and safety for both paper and live accounts, a single source of truth, and UI changes so shortable / hard-to-borrow status is visible next to Level 2.

## Goal

A fully specified Phase K in `Nova-Roadmap-Status.md` -- scoped checklists K0–K4, test matrix, safety invariants, sequencing gates -- with zero product code written, and the ledger entry established as the SSOT for scope.

## Why it mattered

Short selling inverts a load-bearing Nova invariant ("every SELL is risk-reducing"). If that work starts from a chat memory instead of a written phase contract, the anti-short gate gets nibbled ad hoc and flatten/reconcile silently break. The user also needs borrow visibility at decision time (next to L2), so scope had to cover UI, not just the order path.

## What we changed

- `Nova-Roadmap-Status.md`: new Phase K ledger entry (K0 constitution + ADR 009; K1 shortability truth; K2 execution gate; K3 paper proof → live unlock; K4 UI chip + ticket toggle), Current position + Last updated stamps, K–Z parking lot retitled L–Z, History row appended.
- `CHANGELOG.md`: entry prepended.
- This task-log entry + `INDEX.md` row (scaffolder).

## How it works now

Phase K is `[ ]` DEFINED / NOT STARTED, gated on Phase B shadow days. The ledger entry is the single source of truth for scope (the referenced `nova_master_roadmap_a_z.plan.md` file is absent from repo root and Cursor plans folder -- noted in the entry rather than fabricated). Short entry will require: explicit per-order opt-in + `IBKR_SHORT_ENABLED=true` + fresh shortable state (tick 236, fail-closed) for paper; plus `IBKR_LIVE_TRADING_CONFIRMED` + K3 sign-off for live. The no-flag anti-short path (`NO_POSITION` / `OVERSELL`) is specified as byte-for-byte unchanged.

## Why this approach

- **Definition-only, not implementation:** continuity scope guard forbids shipping non-active phases; the user asked for a roadmap addition, so the deliverable is a contract, not code. K0 explicitly reserves the ADR and constitution reword for when the phase opens.
- **Letter K:** A–J were used; K was the head of the deferred parking lot, and promoting it required user direction -- which was given verbatim in the request.
- **New env gate `IBKR_SHORT_ENABLED` instead of reusing order flags:** matches the existing two-key pattern (`IBKR_ORDERS_ENABLED` / `IBKR_LIVE_TRADING_CONFIRMED`) so live short is three deliberate operator acts, never a side effect.
- **Explicit opt-in field, never inference:** inferring short intent from "SELL with no position" would make every oversell bug look like a short request; a flag keeps the default path's refusals meaningful.
- **Tick 236 as estimate, TWS as truth:** IBKR's API exposes shortableShares but not exact fee/HTB state; the UI copy and validation both fail toward "confirm in TWS" instead of overclaiming a locate.
- Rejected: creating the missing master plan file now -- fabricating a retroactive A–J plan doc is a bigger, separate cleanup; the History row records the gap honestly.

## Verification

Docs-only change. Verified by re-reading the ledger entry end-to-end, cross-checking every code anchor it names (`execution/validate.py` anti-short block, `EXECUTOR_ENTRY_SIDE_IBKR` in `constants_ibkr.py`, `ibkr/listing_flags.py` tick 236, flatten path), and confirming ADR 009 is the next free decision number.

## Follow-ups

- Start K0 only after Phase B records shadow days (sequencing gate in the entry).
- Decide separately whether to recreate `nova_master_roadmap_a_z.plan.md` or retarget the status-note header to the ledger as plan-of-record.

## Keywords

phase k, short entry, short selling, shortable, hard to borrow, htb, tick 236, IBKR_SHORT_ENABLED, buy-to-cover, roadmap, level 2 ui
