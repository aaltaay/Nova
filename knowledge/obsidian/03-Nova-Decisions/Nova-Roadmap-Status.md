# Nova Roadmap Status

> **Canonical product roadmap ledger** for the Master Roadmap A-Z. Short by design -- closed phases, verification baselines, and older History rows live in [[Nova-Roadmap-Archive]].
> **Continuity rule:** `.cursor/rules/nova-roadmap-continuity.mdc`
> **Canvas (project homepage):** `canvases/nova-home.canvas.tsx`
> **Nova OS engine status (closed map):** [[Nova-OS-Status]]
> **Live gate (Phase I):** [[Nova-OS-Live-Readiness-Review]] · **Productization (Phase J):** [[Productization-Decision]] · **Idea bank:** [[Nova-Expansion-Ideas]]

Checkbox legend: `[ ]` pending · `[~]` in progress · `[x]` verified / complete

## Current position

- **Product NEXT:** **Phase K -- short entry**, `[~]` IN PROGRESS. Code K0-K2/K4 shipped; **K3 paper short days are human work**.
- **`auto_live`:** **NO-GO** -- rejected in `backend/nova_os/control_mode.py`. Do not enable or implement.
- **Phase B (paper shadow ops):** **WAIVED** by user 2026-07-28 (0 evidence rows; not `[x]`). Do not block work on ≥5 shadow days.
- **Phase C (durable archive):** `[~]` PARTIAL -- remainder is optional operator work (see below).
- **Phase I (live readiness):** `[~]` framework ready, **verdict NO-GO**. Framework alone is not a GO.
- **Reliability track (WS0-WS7):** shipped 2026-08-18; only **WS1 proof** is open (first unattended 03:55 ET run).
- **Closed:** Phases A, D, E, F, G, G2, G3, H, J · Nova OS P0-P10 · Maintenance Phases 0-13 -> [[Nova-Roadmap-Archive]]
- **Last verified commit:** `aad9bf9` (architecture close remediation Phase 7). Tip SHA: `git rev-parse --short HEAD`.
- **Last updated:** 2026-09-08 (roadmap note trimmed; closed detail archived)

## Exact next action (human)

1. **K3 paper short days:** set `IBKR_SHORT_ENABLED=true` on paper Gateway; place `short_entry` orders; fill K3 Evidence (≥3 days) + sign-off before any live short.
2. **Reliability WS1:** configure a Discord/Telegram channel in Settings; run `.\scripts\Install-NovaDailyTask.ps1` once; leave the PC on overnight (wake timers). The first 03:55 ET line in `backend/logs/morning-check.log` closes the Jul 30 PROBLEM_LOG entry.
3. **Optional Phase C remainder:** Cloudflare Bucket Lock + R2 token rotation + cold `walk_day`.
4. **Hard ban:** no `auto_live`. Live short needs K3 sign-off **plus** `IBKR_LIVE_TRADING_CONFIRMED` on top of `IBKR_SHORT_ENABLED`.

## Open phases

### Phase K -- Short entry -- `[~]` IN PROGRESS

**User direction (2026-07-28):** shortable / HTB visibility next to Level 2, safe short entry on paper first, live later. Phase B gate removed. SSOT is this entry + ADR `architecture/decisions/009-short-entry.md`.

- **K0 design + constitution** `[x]` -- ADR 009, reworded anti-short invariant, reason codes `SHORT_DISABLED` / `SHORT_NOT_SHORTABLE` / `SHORT_STALE_BORROW`
- **K1 shortability truth** `[x]` -- `ibkr/shortability.py` tick-236 states (`shortable_est` / `thin` / `htb_likely` / `unknown`), fail-closed, `IBKR_SHORTABILITY_TTL_SEC`
- **K2 execution gate** `[x]` -- explicit `ExecutionCommand.short_entry`, inverse bracket legs, flatten covers shorts, `account.short_qty` SSOT
  - [ ] Journal `side="short"` + side-aware R-multiples on live short fills (follow-up when short automation setups exist)
- **K3 paper proof -> live unlock** `[~]` -- code drills + live criteria written; **human days open**
  - [ ] ≥3 clean paper short days (`confirm` then `auto_paper`) with borrow state captured in receipts
  - [ ] Phase I scorecard re-run including short metrics
  - [ ] Operator sign-off after those days
- **K4 UI** `[x]` -- Shortability chip beside L2 title, Long/Short ticket with `SHORT_*` reasons
  - [ ] Deferred: scanner-level shortable filter

**K3 live unlock criteria (operator):** `IBKR_SHORT_ENABLED=true` on paper with ≥3 days of `short_entry` receipts + kill/flatten drills · no unresolved `SHORT_*` false-allow bugs in PROBLEM_LOG · explicit sign-off in History · then live short only with `IBKR_LIVE_TRADING_CONFIRMED=true`. `auto_live` stays NO-GO.

**K3 Evidence:** none yet -- awaiting human paper short sessions.

**Safety invariants (must never regress):** short entry is explicit per-order opt-in + env gate, default OFF · anti-short default path unchanged · fail closed on unknown / stale borrow · every refusal leaves a receipt with a reason code.

### Phase C -- Durable archive -- `[~]` PARTIAL (optional operator work)

Done: R2 keys + connectivity, `ARCHIVE_MAINTENANCE_ENABLED`, L2 failures folded into `archive_health`, Bucket Lock + rotation steps documented in `docs/r2-archive-setup.md`. Hot `bars_1m` backfilled from tape (331 bars, 2026-07-17).

- [ ] R2 Bucket Lock enabled in the Cloudflare console (operator)
- [ ] Temporary/test R2 token rotated (operator)
- [ ] Upload/restore on a **real** compacted production day, then `walk_day` on that cold day

Do not fake Phase C `[x]`.

### Phase I -- Live-readiness evidence -- `[~]` framework ready / verdict NO-GO

- [x] GO/NO-GO thresholds in [[Nova-OS-Live-Readiness-Review]]; `auto_live` stays rejected in code
- [ ] Re-run the review against real paper metrics (now sourced from K3 short days, not waived Phase B)

### Reliability track -- problem-root elimination (2026-08-18)

Closes the five PROBLEM_LOG root patterns. Not a Master Roadmap letter phase; product NEXT stays Phase K.

| WS | Status | Closes |
|----|--------|--------|
| 0 Ledger | `[x]` | This section |
| 1 Morning autopilot | `[~]` | Tooling shipped. Proof = first real 03:55 ET line in `backend/logs/morning-check.log`; Jul 30 PROBLEM_LOG stays OPEN until then |
| 2 IB-loop purity guard | `[x]` | `tools/maintainer_lib/ib_loop.py` + CI `--fail-on-kind ib_loop_sync_io` |
| 3 Fail-loud REST | `[x]` | `table_state` / `roster_ts` / `feed_error` on gappers/movers/AH |
| 4 Persisted-state rule | `[x]` | `.cursor/rules/persisted-state.mdc` + corrupt channels ERROR log |
| 5 SSOT audit | `[x]` | Remaining dual-read is gated (`chart_bars.py` Alpaca path); qty SSOT is `ib.positions()`; Orders Today is a ledger overlay |
| 6 Test isolation | `[x]` | conftest import-time `NOVA_CACHE_DIR` + paper Gateway pin |
| 7 Blast-radius verification | `[x]` | Table in `verification-before-completion.mdc` |

### Phases L-Z -- `[~]` DEFERRED (parking lot)

Conversational scans, Holly-like coach, L2 scrubber, SMS/email, multi-broker, cloud Gateway, community, native mobile, CI expansion, mission canvas, reserved U-Z. **Not scheduled** until explicitly promoted.

## Crash or blocker

- **Phase K:** in progress; K3 needs human paper short sessions.
- **Phase B:** WAIVED (2026-07-28) -- not a blocker.
- **Phase C remainder:** needs Cloudflare console work + a fresh session compact/walk (optional).
- **Phase I verdict:** NO-GO; short metrics arrive after K3 paper days.
- **`auto_live`:** permanent NO-GO in this roadmap window.

## History (append-only)

Newest first. Append here; do not rewrite prior rows. Rows before 2026-07-28 are in [[Nova-Roadmap-Archive]].

| Date | What | Commit |
|------|------|--------|
| 2026-09-11 | Unprotected public `master` tracked as P0 **D-041 / #63** (blocked on human Administration). Phase NEXT unchanged (K3). `auto_live` NO-GO. | (this commit) |
| 2026-09-11 | Public source home is `aaltaay/Nova`. Marketing CTA retargeted. `Nova-public` is a private archive. Phase NEXT unchanged (K3). `auto_live` NO-GO. | (this commit) |
| 2026-09-08 | Roadmap note trimmed to a live status page; closed phases, verification baselines, maintenance track, and pre-2026-07-28 History moved verbatim to [[Nova-Roadmap-Archive]]. Task narratives now default to PR bodies. No phase state changed; `auto_live` NO-GO. | (this commit) |
| 2026-08-31 | Public domain `nova.altaystudio.com` is a static marketing page (`site/`), not the hosted scanner. CTA is Nova-public. Phase J local-first. `auto_live` NO-GO. | (that commit) |
| 2026-08-18 | Reliability track WS0-WS7: morning check + system-event alerts, fail-loud scanner REST, pytest cache isolation, IB-loop purity CI gate, blast-radius + persisted-state rules. WS1 proof still needs first unattended 03:55 ET run. `auto_live` NO-GO. | (that commit) |
| 2026-07-28 | Phase B WAIVED + Phase K E2E ship: ADR 009, shortability module, `IBKR_SHORT_ENABLED` + `short_entry` gates, flatten cover, Shortability chip + Long/Short ticket. K3 human paper short days still open. `auto_live` NO-GO. | `125f3ce` |
