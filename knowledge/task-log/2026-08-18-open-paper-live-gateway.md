# 2026-08-18 -- Open paper and Open live Gateway

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-18 -- Open paper and Open live Gateway side by side

## Task

Stop the daily full-screen Trading prerequisites overlay for Gateway-only mornings. Put that checklist on the Gateway chip. Give two buttons together -- Open paper Gateway and Open live Gateway -- so the operator can pick a door.

## Goal

Desk stays usable when only Gateway is down. Click Gateway for the checklist. Paper and live launch sit side by side on the checklist and on the red banner.

## Why it mattered

A full-screen block every morning treated a missing Gateway login like a dead Nova API. One generic Open button also hid which IBKR door was about to start.

## What we changed

- `autoOverlay` is Nova API down only (including a real IB-loop wedge). Gateway-only sets `blockDesk` but does not cover the desk.
- Header Gateway chip click opens the checklist. Double-click still launches the current target.
- Red banner title opens the same checklist. Banner CTAs are the paired Open buttons.
- `POST /api/ibkr/launch-gateway` accepts optional `{mode: paper|live}`. Mode path persists Nova mode, sets intentional-follow grace, rewrites IBC `TradingMode` + `OverrideTwsApiPort` only, stops the windowed Gateway process, starts `start_gateway.ps1 -TradingMode`.
- Vite fallback accepts `?mode=`.
- Loud-warn rule updated: checklist is on the chip; banner stays; no silent Gateway-down.

## How it works now

1. Gateway offline: thin red banner + offline chip. Desk is not covered.
2. Click Gateway (or banner title) for the checklist. Close or click the backdrop to dismiss.
3. Open paper / Open live pick 4002 or 4001. Look at the desktop for IBKR Mobile 2FA.
4. Follow-Gateway still attaches to the listening port after the intentional-mode grace if the requested door stays dark.
5. Spend flags are unchanged. Live Open + existing live spend flags = `live_armed`.

## Why this approach

Rejected keeping the auto-overlay for Gateway-only: that was the pain. Rejected one generic Open button: the operator asked to pick the door. Rejected putting both buttons in the header chrome: the chip stays one control; the pair lives on the checklist and banner where there is room.

Stopping only the windowed IB Gateway process (title / `ibgateway`) avoids killing unrelated `java.exe`. INI rewrite is limited to `TradingMode` and `OverrideTwsApiPort` so credentials never move through this path.

## Verification

See CHANGELOG Verified by. Fresh pytest + Vitest + `npm run build` this session.

## Follow-ups

Do not commit `.env` or `%USERPROFILE%\.nova\ibc\`. Live IBC still needs a live username in the local IBC config or IB will keep landing on Simulated Trading / 4002.

## Keywords

Open paper Gateway, Open live Gateway, Trading prerequisites, Gateway chip, launch-gateway, IBC TradingMode, 2FA
