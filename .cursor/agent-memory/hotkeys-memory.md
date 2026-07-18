# Hotkeys memory (living)

Living knowledge for the Nova `hotkeys` subagent. **Read at the start of every run. Update at the end when something new was learned.**

Companion to: `.cursor/agents/hotkeys.md`

---

## Current snapshot

```yaml
captured_at: 2026-07-18T21:05:00Z
source_revision: ""
result: verified
metrics:
  nova_actions_default: 6
  cancel_all_route: true
  map_to_nova_action: true
blockers: []
dashboard_freshness: clean
```

Machine-readable block only. Update after material runs.

---

## How to continue improving

> Use the hotkeys subagent to …

Or:

> Improve the hotkeys agent — work the next backlog item in `.cursor/agent-memory/hotkeys-memory.md`.

---

## Backlog

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
| 2026-07-18 | G3 verified: Map UX + browser on 127.0.0.1:5173; TriggerOrder reject; vitest 28 |
| 2026-07-18 | G3 shipped: typed Nova Actions + hotkeys specialist; vitest/build/contract green |
