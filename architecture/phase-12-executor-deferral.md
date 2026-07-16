# Phase 12 — Executor split deferral

**Status:** Deferred (safer to keep baseline) · **Date:** 2026-07-16  
**Plan phase:** Pattern-Driven Architecture Phase 12  
**Accepted baseline:** `backend/strategy/executor.py` = **494** lines (`BASELINE_ACCEPTED_LINES`)

## Entry gate

Phase 12 required explicit approval for a safety-sensitive split plus a security review of the diff. The program instruction allows deferral with written rationale when forced extraction would increase risk.

## Why deferral is safer

1. **`place_from_ticket` gate chain must stay one auditable function** — kill switch → concurrency → control mode → risk → plan → bracket. Splitting that chain across modules recreates the stale-alias / dual-path class of bugs Phase 10 fixed for HOD Momo.
2. Tests monkeypatch module-level `_open_positions` and `_kill_switch_tripped` on `executor` directly. A partial extract without a shared-state owner (like Phase 10's `HodMomoState`) would leave silent alias bugs.
3. Flatten helpers already live in `executor_flatten.py`. Remaining bulk is the placement gate chain + fill polling tightly coupled to those globals.
4. **`auto_live` remains rejected**; no live orders were placed during this program. A structural refactor of the executor without a dedicated shared-state migration (Phase 10 style) is higher risk than the 94-line overage.

## Allowed future work (not done here)

- Extract fill polling/resolution into `executor_fill.py` **only after** introducing an explicit executor state owner and updating monkeypatches (mirror Phase 10).
- Keep `place_from_ticket` intact in one module.
- Require security review of the diff before merge.

## Verification at deferral

- `executor.py` remains at accepted baseline 494 (no growth).
- Maintainer reports `file_size_baseline` only — not `baseline_growth`.
- No forced split performed.
