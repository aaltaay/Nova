# 2026-07-18 — Phase G3 Nova Actions + hotkeys specialist

- **Status:** completed
- **Agents:** parent | hotkeys (scaffolded)
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-18 Phase G3 · Phase G2 `645761b`

## Task

Implement the hotkeys specialist verdict plan: scaffold a `hotkeys` agent, open Phase G3, and ship typed executable Nova Actions toward DAS-grade hotkeys.

## Goal

Executable cancel / exit / Ask±/Bid± hotkeys and buttons via Settings → Hotkeys, without running raw DAS scripts; one dispatcher; paper-first; `auto_live` NO-GO.

## Why it mattered

G/G2 left hotkeys Continuity-only with authoring-only `.htk` import. Day-trading speed needs typed actions owned by a specialist, not rediscovered each session.

## What we changed

- Scaffolded `hotkeys` agent, continuity rule, `agent-hotkeys` canvas, fleet Owned
- Opened Phase G3 in `Nova-Roadmap-Status.md`
- `DELETE /api/ibkr/orders?symbol=` cancel-all orchestration
- Shell `HotkeyDispatchProvider` + `event.repeat` guard; Automation registers into it
- Nova Actions profile slice, Settings table, Trading quick-bar
- L2 top-of-book context for honest Ask/Bid pricing
- Curated DAS-inspired defaults in Help

## How it works now

Two systems: Automation six (executor ladder) vs Nova Actions (manual `source="manual"` path with PIN/spend/confirm). Imported `.htk` stays inactive until mapped. Ask±/Bid± require subscribed L2 depth — never last-trade substitute.

## Why this approach

**Typed Nova Actions over a DAS script interpreter** — avoids left-to-right variable mutation and unsafe ECN routes while covering the community core set. **One dispatcher** prevents double-firing if Automation and Trading UI are both mounted. **Cancel-all as orchestration** preserves per-order ADR 007 idempotency/audit. Rejected: monitor-only agent; blind `.htk` execute; second Settings “Buttons” tab.

## Verification

- `py -3 -m pytest backend/tests/test_trading_cancel_all.py -q` — 3 passed
- `npx vitest run src/hotkeys src/hooks/useHotkeys.test.ts src/ibkr/exitPosition.test.ts src/components/SettingsWorkspace.test.tsx` — 40 passed
- `npm run build` — PASS
- `py -3 tools/agent_contract.py` — PASS (15 agents)

## Follow-ups

- Map-to-Nova-Action UX for large imports
- P3 risk-dollar sizing / OTO
- Tester browser pass on Settings → Hotkeys + quick-bar clicks

## Keywords

hotkeys, Phase G3, Nova Actions, DAS, cancel-all, L2 top-of-book, HotkeyDispatchProvider, auto_live NO-GO
