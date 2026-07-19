# Hotkeys memory (living)

Living knowledge for the Nova `hotkeys` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hotkeys.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-19T03:35:00Z
source_revision: ""
result: fill_now_and_cancel_and_exit
metrics:
  nova_actions_default: 7
  cancel_nova_kinds: 2  # cancel_symbol, cancel_and_exit
  cancel_all_route: true
  map_to_nova_action: true
  working_orders_panel_in_dispatcher: false
  fill_now_panel: true  # per-order UI; not a Nova Action (needs order id)
  flatten_outside_rth: auto  # pre/after-market via extendedSession
blockers: []
dashboard_freshness: refresh-required
ownership:
  broker_cancel_ssot: execution.service.execute(operation=cancel)
  hotkeys_owns: cancel_symbol + cancel_and_exit + exit_pos dispatcher/quick-bar
  not_hotkeys: WorkingOrdersPanel Fill now / Cancel (widgets/IBKR UI → same ADR 007 path)
```

Machine-readable block only. Update after material runs.

---

## How to continue improving

> Use the hotkeys subagent to …

Or:

> Improve the hotkeys agent — work the next backlog item in `.cursor/agent-memory/hotkeys-memory.md`.

---

## Backlog

- [ ] Optional continuity one-liner: WorkingOrdersPanel per-order cancel is out of dispatcher scope (broker SSOT = ADR 007)
- [ ] P3 risk-dollar sizing / OTO / chart-stop recipes
- [ ] Server-synced hotkey profiles
- [ ] Bulk Map polish for very large `.htk` imports (row-at-a-time works)

## Completed

- [x] Agent scaffolded + continuity rule + fleet Owned (2026-07-18)
- [x] Phase G3 core: dispatcher, cancel-all, Nova Actions UI, quick-bar, L2 bid/ask (2026-07-18)
- [x] Map-to-Nova-Action + tester browser; G3 `[x]` (2026-07-18)

## Run log

| Date | Note |
|------|------|
| 2026-07-18 | Daddy audit: cancel ownership — hotkeys=`cancel_symbol` only; panel ✕ ≠ dispatcher; broker SSOT=`execute(cancel)`; gate gap (PIN/spend) → execution handoff. task_log=knowledge/task-log/2026-07-18-hotkeys-cancel-ownership-audit.md |
| 2026-07-18 | G3 verified: Map UX + browser on 127.0.0.1:5173; TriggerOrder reject; vitest 28 |
| 2026-07-18 | G3 shipped: typed Nova Actions + hotkeys specialist; vitest/build/contract green |
