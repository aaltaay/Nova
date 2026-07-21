# 2026-07-19 — Trader always-on Nova OS judgment

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / nova-os UX
- **Related:** `CHANGELOG.md` §2026-07-19 — Trader always-on Nova OS judgment

## Task

Embed Nova OS `decide()` as an always-visible real-time rating strip in Trader — gates, scores, and catalyst/news impact breakdown — so the user sees how the OS rates the name before Automation.

## Goal

Trader shows the live scoring trail (not a popup): verdict, gates, `news_impact`, ticket, holding exit note; Watchlist Decision shares the detail UI; no new sell decide or API contract change.

## Why it mattered

Automation trusts BUY paths after human review. Decision panel existed on Watchlist but Trader (where you trade the name) never called decide or surfaced news evidence, so the ratings trail was easy to miss.

## What we changed

- Extracted `NovaOsVerdictDetail` + `GateRow` from `DecisionPanel`; added typed `novaOsNewsImpact` helper and news interpretation block.
- Added `useNovaOsDecideSymbol` (2s poll, clear on symbol switch, loud 404).
- Built `TraderNovaOsBrain` under `StockViewHeader` in `StockViewPage`.
- Constants: `NOVA_OS_TRADER_DECIDE_POLL_MS`, disclosure/exit copy in `market_ui.ts`.
- Vitest coverage for news render, symbol clear, brain + 404.

## How it works now

Opening Trader mounts the brain band. It polls single-symbol decide (display, `record=False` on backend). Soft gate `catalyst` already carries `evidence.news_impact` from `evaluate_news_impact`; UI finally promotes it. Holding a position adds an exit note (stops/Flatten/hotkeys — no SELL decide). Signal-only copy points to Watchlist → Automation.

## Why this approach

- **Reuse decide payload** instead of a new LLM/authorizer — ratings already exist; Trader was the missing surface.
- **Shared verdict detail** avoids Decision vs Trader drift on gates/news/ticket.
- **Separate 2s hook** keeps Watchlist batch at 5s; symbol clear prevents quote-panel-style bleed.
- **Rejected:** inventing SELL decide; auto-raising Automation from Trader; growing `stockViewTerminal.css` further (brain CSS co-located).

## Verification

`npx vitest run` on `novaOsNewsImpact`, `NovaOsVerdictDetail`, `useNovaOsDecideSymbol`, `TraderNovaOsBrain`, `stockViewTerminal` — 18 passed.

## Follow-ups

Deep-link to Automation tab if URL/tab routing is added later.

## Keywords

trader, nova-os, decide, news_impact, catalyst, TraderNovaOsBrain, ratings
