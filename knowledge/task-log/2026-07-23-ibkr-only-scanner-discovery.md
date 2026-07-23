# 2026-07-23 — IBKR-only scanner discovery lock

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed
- **Related:** `CHANGELOG.md` §2026-07-23 — IBKR-only scanner discovery · `PROBLEM_LOG.md` §2026-07-23 — Alpaca still offered/defaulted as scanner source · Scanner-Provider-IBKR-Primary.md

## Task

Investigate and fix every remaining place where Alpaca could appear as a scanner source or mislead users that the live scanner feed was OK while Gateway was offline.

## Goal

Product surface is IBKR-only for scanner discovery; Alpaca is news/listing aux only; no Settings path can select or persist alpaca discovery.

## Why it mattered

Users saw green Alpaca/FEED chips while IB Gateway was still logging in. Defaults and a soft-toggle UI contradicted the IBKR-primary decision and the single-market-data-feed rule.

## What we changed

- `DISCOVERY_PROVIDER_DEFAULT=ibkr`, `OPTIONS=("ibkr",)` (backend + frontend)
- Coerce/persist ibkr in `alpaca.py` + `POST /api/config`
- Removed Scanner Source dropdowns from `SettingsPanel` + `DashboardTab` (read-only Gateway line)
- `useSettingsForm` / `workspaceConfig` always treat discovery as ibkr
- Header aux chip `Alpaca` → `News`; attribution always IBKR for scanner/quote
- Updated decision note, `single-market-data-feed.mdc`, tests

## How it works now

Scanner/quote/chart/L2/T&S = IBKR. Stale env or POST `alpaca` coerces to `ibkr`. Settings Alpaca fields are labeled news/listing aux. Green `News` chip is not scanner health — Gateway chip is.

## Why this approach

- **Lock product surface, keep adapters** — deleting Alpaca gapper modules is high-risk and unnecessary once unreachable; unit tests still exercise chart “no silent IBKR→Alpaca fallback.”
- **Coerce at API + FE hydrate** — closes Settings overwrite and boot-race FEED chip without requiring every caller to remember the invariant.
- **Rejected:** keeping the dropdown “for undo” — that was the original mistake that confused operators.

## Verification

- `py -3 -m pytest backend/tests/test_discovery_provider_lock.py backend/tests/test_config_secrets.py -q` → 6 passed
- Vitest: dataSourceMap, workspaceConfig, HeaderConnectionStatus, SettingsWorkspace, WorkspaceContext → 16 passed

## Follow-ups

- Restart Nova API/UI so running processes pick up the lock.
- Residual copy from explore inventory: Volume·RVOL label, TradingTab Gateway wording, HOD YF title, `.env.example`, data-sources hint (done same session).
- Optional later: delete unreachable Alpaca scanner adapters if unused for a release cycle.

## Keywords

discovery_provider, IBKR-only, Alpaca scanner, Settings, soft-toggle, News chip, FEED
