# Hotkeys memory (living)

Living knowledge for the Nova `hotkeys` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hotkeys.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-30T18:10:00Z
source_revision: ""
result: webull_style_nova_actions
metrics:
  nova_actions_default: 14  # 7 classic + 7 nova-wb-*
  cancel_nova_kinds: 3  # cancel_symbol, cancel_and_exit, cancel_all_orders
  cancel_all_route: true  # DELETE /api/ibkr/orders?all_symbols=true
  buy_market: true  # shares default 1; confirm shows PAPER|LIVE
  long_only_pct_exits: true  # sell_pos_pct_ask / sell_pos_pct_bid_offset
  map_to_nova_action: true
  working_orders_panel_in_dispatcher: false
  fill_now_panel: true
  flatten_outside_rth: auto
  paper_live_same_path: true  # System 2 only; spend/Gateway differ
blockers: []
dashboard_freshness: refresh-required
ownership:
  broker_cancel_ssot: execution.service.execute(operation=cancel)
  hotkeys_owns: cancel_* + buy_market + long-% Ask/Bid + exit_pos dispatcher/quick-bar
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
| 2026-07-30 | Webull-style set: Ctrl+1 Buy 1 MKT; Ctrl+Z Cancel All stocks; Ctrl+4/5/6 Sell % @ASK; Ctrl+2/3 Sell % @BID-$0.03. Long-only sizing; confirm + PAPER/LIVE label; merge-by-id for defaults; `all_symbols` cancel. Paper=live path. Vitest hotkeys 70; pytest cancel_all 5. |
| 2026-07-20 | User Q: live trades via shortcuts tomorrow? Answer: NO on current config. Shortcuts = Nova Actions → `runNovaAction` → `placeIbkrOrder` → `POST /api/ibkr/order` `source=manual` → `assert_orders_allowed`. Live money blocked by `IBKR_LIVE_TRADING_CONFIRMED` (false) + paper pin (`IBKR_GATEWAY_MODE=paper` / port 4002). Paper shortcut orders OK while `spend_status=paper_armed` + PIN unlock. `auto_live` irrelevant to System 2 / stays NO-GO. |
| 2026-07-18 | Daddy audit: cancel ownership — hotkeys=`cancel_symbol` only; panel ✕ ≠ dispatcher; broker SSOT=`execute(cancel)`; gate gap (PIN/spend) → execution handoff. task_log=knowledge/task-log/2026-07-18-hotkeys-cancel-ownership-audit.md |
| 2026-07-18 | G3 verified: Map UX + browser on 127.0.0.1:5173; TriggerOrder reject; vitest 28 |
| 2026-07-18 | G3 shipped: typed Nova Actions + hotkeys specialist; vitest/build/contract green |
