# 2026-07-18 — Double-click Gateway chip opens IB Gateway

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed (UI)
- **Related:** `CHANGELOG.md` §2026-07-18 Double-click Gateway chip · `docs/ibc-gateway-setup.md`

## Task

Double-click the header Gateway status chip to summon IB Gateway so the user doesn’t have to hunt for it when it’s offline.

## Goal

One gesture opens or focuses Gateway; Nova still waits for real login/2FA before marking connected.

## Why it mattered

Gateway offline is a frequent blocker for IBKR discovery. The chip already told the truth; it should also reduce friction to fix it.

## What we changed

- `POST /api/ibkr/launch-gateway` → `ibkr/launch_gateway.py` (IBC script → exe → focus window)
- Header Gateway chip is a double-clickable button calling `launchIbGateway()`
- Constants for default Gateway path + IBC launcher location

## How it works now

1. Double-click **Gateway** chip → API launches/focuses desktop Gateway.
2. Prefer `%USERPROFILE%\.nova\ibc\start_gateway.ps1` when present.
3. Else start `IBKR_GATEWAY_EXE` or newest `C:\Jts\ibgateway\*\ibgateway.exe`.
4. Chip shows “opening…” briefly; tooltip carries the API message. User still completes login + 2FA.

## Why this approach

Browser cannot spawn desktop apps, so the local API process does it (same pattern as Start API). Rejected Electron-only IPC so Vite/`Run Nova.bat` users get the same path. No credentials in the request body — launch only, never auto-type passwords in-repo.

## Verification

- `py -3 -m pytest backend/tests/test_launch_gateway.py -q` (5 passed)
- Vitest `launchIbGateway` + `HeaderConnectionStatus`
- Live resolve: `C:\Jts\ibgateway\1045\ibgateway.exe`

## Follow-ups

- User must complete Gateway login / 2FA after summon
- Optional: Electron IPC mirror for packaged desktop

## Keywords

IB Gateway, launch-gateway, double-click, header chip, IBC, 2FA
