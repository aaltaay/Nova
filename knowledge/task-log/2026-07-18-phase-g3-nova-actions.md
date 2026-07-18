# 2026-07-18 — Phase G3 Nova Actions + hotkeys specialist

- **Status:** completed (verified)
- **Agents:** parent | hotkeys (scaffolded) | tester (browser)
- **Domain:** hotkeys
- **Related:** `CHANGELOG.md` §2026-07-18 Phase G3 verified · Phase G2 `645761b` · open `ce1da59`

## Task

Implement the hotkeys specialist verdict plan: scaffold a `hotkeys` agent, open Phase G3, ship typed executable Nova Actions, finish Map-to-Nova-Action, and close G3 with browser verification.

## Goal

Executable cancel / exit / Ask±/Bid± hotkeys and buttons via Settings → Hotkeys, without running raw DAS scripts; one dispatcher; paper-first; `auto_live` NO-GO.

## Why it mattered

G/G2 left hotkeys Continuity-only with authoring-only `.htk` import. Day-trading speed needs typed actions owned by a specialist, not rediscovered each session.

## What we changed

- Scaffolded `hotkeys` agent, continuity rule, `agent-hotkeys` canvas, fleet Owned
- Opened then verified Phase G3 in `Nova-Roadmap-Status.md`
- `DELETE /api/ibkr/orders?symbol=` cancel-all orchestration
- Shell `HotkeyDispatchProvider` + `event.repeat` guard; Automation registers into it
- Nova Actions profile slice, Settings table, Trading quick-bar
- L2 top-of-book context for honest Ask/Bid pricing
- Curated DAS-inspired defaults in Help
- **Map to Nova Action:** `suggestNovaActionFromDas` + dialog; creates disabled Nova Action; rejects TriggerOrder before BUY heuristics

## How it works now

Two systems: Automation six (executor ladder) vs Nova Actions (manual `source="manual"` path with PIN/spend/confirm). Imported `.htk` stays inactive until Map. Ask±/Bid± require subscribed L2 depth — never last-trade substitute. Local UI verify on `http://127.0.0.1:5173` (avoid `localhost` when another app owns `::1:5173`).

## Why this approach

**Typed Nova Actions over a DAS script interpreter** — avoids left-to-right variable mutation and unsafe ECN routes while covering the community core set. **One dispatcher** prevents double-firing if Automation and Trading UI are both mounted. **Cancel-all as orchestration** preserves per-order ADR 007 idempotency/audit. **Map creates disabled actions** so large imports cannot silently arm keys. Rejected: monitor-only agent; blind `.htk` execute; second Settings “Buttons” tab; mapping TriggerOrder/OTO without backend support.

## Verification

- `py -3 -m pytest backend/tests/test_trading_cancel_all.py -q` — 3 passed
- `npx vitest run src/hotkeys` — 28 passed (includes Map flow + TriggerOrder reject)
- `npm run build` — PASS (prior G3 commit)
- `py -3 tools/agent_contract.py` — PASS (15 agents)
- Tester browser: Settings → Hotkeys banner/Nova Actions/Map dialog; Stock View `.nova-trading-quick-bar`; console clean; no order APIs

## Follow-ups

- P3 risk-dollar sizing / OTO / chart-stop recipes
- Server-synced hotkey profiles

## Keywords

hotkeys, Phase G3, Nova Actions, DAS, Map to Nova Action, cancel-all, L2 top-of-book, HotkeyDispatchProvider, auto_live NO-GO
