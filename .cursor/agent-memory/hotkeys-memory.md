# Hotkeys memory (living)

Living knowledge for the Nova `hotkeys` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hotkeys.md`

---

## Current snapshot

```yaml
captured_at: 2026-09-16T05:10:00Z
source_revision: d047-hide-coming-soon
result: hide_dead_landing_tabs_and_ticket_automate
metrics:
  nova_actions_default: 14  # 7 classic + 7 nova-wb-*
  overlay_key_btn: true
  overlay_action_edit: true
  overlay_two_step_delete: true
  delete_tombstones: removedNovaActionIds
  landing_category_tabs: false
  landing_coming_soon: false
  order_ticket_automate: false
  desk_f1: buy_limit_ask_offset 1sh Ask+0.05 EH
  desk_f2: sell_limit_bid_offset 1sh Bid-0.05 EH
  desk_f5: sell_limit_ask_offset 1sh Ask+0.05 EH
  desk_epoch: f1-f5-eh-2026-08-17
  desk_epoch_apply: HotkeyDispatchProvider + useHotkeyProfile apply on epoch change (no hard refresh)
  cancel_nova_kinds: 3
  buy_market: true
  long_only_pct_exits: true
  map_to_nova_action: true
  flatten_outside_rth: auto
  paper_live_same_path: true
blockers: []
dashboard_freshness: refresh-required
ownership:
  broker_cancel_ssot: execution.service.execute(operation=cancel)
  hotkeys_owns: F1/F2 Ask+/Bid- + cancel_* + buy_market + long-% + exit_pos
  not_hotkeys: WorkingOrdersPanel Fill now / Cancel
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
| 2026-09-16 | D-047: hid unused Hot Keys landing tabs + OrderTicket Automate coming-soon stub. Keymap editor unchanged. `auto_live` untouched. |
| 2026-08-25 | Overlay Key / Edit / two-step trash on System 2; tombstones; Settings delete; reloadNovaActions moved off setProfile updater. |
| 2026-08-17 | Desk self-heal: F5 epoch applies without hard refresh. |
| 2026-08-17 | Rebound sell-Ask+$0.05 from F3 to F5. Epoch `f1-f5-eh-2026-08-17`. |
| 2026-08-17 | F3 Sell 1 Ask+$0.05 EH (`sell_limit_ask_offset`). Epoch bumped to f1-f3-eh. |
| 2026-08-17 | F1 Buy 1 Ask+$0.05 EH; F2 Sell 1 Bid-$0.05 EH. Same Nova Action kinds; `outsideRth` param; one-time desk epoch rewrite of local profile. Symbol chip F2 removed so it cannot steal sell. Vitest hotkeys 71. |
| 2026-07-30 | Webull-style set: Ctrl+1 Buy 1 MKT; Ctrl+Z Cancel All stocks; Ctrl+4/5/6 Sell % @ASK; Ctrl+2/3 Sell % @BID-$0.03. Long-only sizing; confirm + PAPER/LIVE label; merge-by-id for defaults; `all_symbols` cancel. Paper=live path. Vitest hotkeys 70; pytest cancel_all 5. |
| 2026-07-20 | User Q: live trades via shortcuts tomorrow? Answer: NO on current config. Shortcuts = Nova Actions → `runNovaAction` → `placeIbkrOrder` → `POST /api/ibkr/order` `source=manual` → `assert_orders_allowed`. Live money blocked by `IBKR_LIVE_TRADING_CONFIRMED` (false) + paper pin (`IBKR_GATEWAY_MODE=paper` / port 4002). Paper shortcut orders OK while `spend_status=paper_armed` + PIN unlock. `auto_live` irrelevant to System 2 / stays NO-GO. |
| 2026-07-18 | Daddy audit: cancel ownership — hotkeys=`cancel_symbol` only; panel ✕ ≠ dispatcher; broker SSOT=`execute(cancel)`; gate gap (PIN/spend) → execution handoff. task_log=knowledge/task-log/2026-07-18-hotkeys-cancel-ownership-audit.md |
| 2026-07-18 | G3 verified: Map UX + browser on 127.0.0.1:5173; TriggerOrder reject; vitest 28 |
| 2026-07-18 | G3 shipped: typed Nova Actions + hotkeys specialist; vitest/build/contract green |
