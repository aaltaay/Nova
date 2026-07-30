# 2026-07-29 -- Webull-style Settings shell + Trade defaults

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / hotkeys-adjacent UI / trading prefs
- **Related:** `CHANGELOG.md` §2026-07-29 -- Webull-style Settings overlay + Trade defaults

## Task

Upgrade Nova Settings to a Webull-like left-rail overlay, move existing config into it, and add Trade > Stocks default order values that the manual ticket reads.

## Goal

Settings reachable from Scanner and Trader; single home for exchange filter + Alpaca; editable stocks defaults (type, qty, hours, limit source, stop offset); skip-confirm under Order Preferences.

## Why it mattered

Config was split (Dashboard duplicate Alpaca form, exchange filter only on Dashboard, ticket defaults hardcoded, Settings missing on Trader because Dashboard unmounts). Webull's Trade > Stocks defaults page was the target UX.

## What we changed

- `SettingsProvider` at AppShell; gear on `GlobalAppBar`; removed AppHeader Settings button
- Left-rail overlay: General, Hot Keys, Trade, Alerts, Account
- General hosts Exchange Filter + SettingsPanel; Dashboard tab is a short pointer
- `tradeDefaultsPrefs` + Stocks/Order Preferences forms; `TICKER_TRADE_FORCE_QTY = null`
- `ManualOrderTicket` seeds from prefs + TopOfBook via `applyTicketDefaults` / `tradeDefaultSeed`

## How it works now

Opening Settings toggles AppShell overlay (z-index 85). One exchange-filter + config form owner feeds Dashboard filtering and General UI. Ticket reads `nova.trade.defaults.v1` on symbol change; Ask/Bid uses TopOfBook when symbol matches, else last. Extended hours only sticks when order type is LMT.

## Why this approach

- Overlay at AppShell (not Dashboard) -- Trader unmounts Dashboard, so page-local Settings can never work there
- GlobalAppBar gear only -- avoids dual entry points
- Nova-real categories only -- no Crypto/Options stubs that would lie
- localStorage prefs -- local-first; no backend trade-defaults API yet
- Clear FORCE_QTY rather than special-case Settings -- otherwise qty prefs would be dead UI
- Rejected: keep inline strip under header (not Webull-like; still Dashboard-bound)

## Verification

- Vitest: SettingsWorkspace, tradeDefaultsPrefs, tradeDefaultSeed, orderEntry, GlobalAppBar, ManualOrderTicket paper label, stockViewTerminal
- `npx tsc --noEmit`

## Follow-ups

- Backend TIF / GTC on place path
- Bracket TP/SL default checkboxes when Manual ticket supports brackets
- Theme / Modules menu under Settings (orphaned ModulesMenu still unused)

## Keywords

settings, webull, trade defaults, GlobalAppBar, SettingsProvider, FORCE_QTY, exchange filter, ManualOrderTicket
