# 2026-08-19 -- Installer IBKR_ENABLED and door-trail UI

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Desktop installer seeds IBKR_ENABLED · `PROBLEM_LOG.md` 2026-08-19 Installer .env missing IBKR_ENABLED

## Task

Make the installed Nova attach after phone 2FA, and show the Paper/Live door trail in the app.

## Goal

Installer desk: IBKR enabled without auto-unlocking spend. Operator can read the door trail without curling the API.

## Why it mattered

Gateway was already live on 4001. Nova said disabled because AppData `.env` never got `IBKR_ENABLED`. The trail lived only in the API.

## What we changed

- `electron/envMerge.mjs` + sidecar merge of missing IBKR connection keys
- `GatewayDoorTrail` on Trading prerequisites and Account → Activity
- Trading setup copy names `%APPDATA%\Nova\.env` for desktop

## How it works now

Desktop launch fills `IBKR_ENABLED=true` only if missing. Spend keys stay off unless the operator sets them. Trail file is `%APPDATA%\Nova\cache\ibkr-gateway-trail.jsonl`.

## Why this approach

Overwrite would clobber an intentional `IBKR_ENABLED=false`. Copying repo spend flags would auto-arm live orders. A dedicated Door trail is not the order Activity ledger.

## Verification

Vitest env merge + trail format/UI. Then AppData env + Nova restart + trail GET.

## Follow-ups

Rebuild NSIS so the packaged UI includes the trail panel. Do not copy `IBKR_ORDERS_ENABLED` unless asked.

## Keywords

installer, APPDATA, IBKR_ENABLED, door trail, audit
