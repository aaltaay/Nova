# 2026-07-19 — Isolated Sample data route

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / UX demo
- **Related:** `CHANGELOG.md` §2026-07-19 — Isolated Sample data route

## Task

Add a massive sample-data switch in the header so gappers, gainers, losers, catalysts, HOD Momo, and watchlist (plus decide/Trader) show populated fixtures — never mixed with live data.

## Goal

`?view=sample` is its own route/shell; flipping the switch remounts away from live Dashboard; no silent fallback of empty live lists to fixtures.

## Why it mattered

Live feeds are often empty (IBKR login, session, cold start). User needed a reliable way to see every major surface populated for product review.

## What we changed

- Header checkbox → `enterSampleView()` / `leaveSampleView()`
- `SampleShell` + `SampleDashboardPage` + fixture modules under `frontend/src/sample_data/`
- Hook short-circuits when `SampleDataProvider` is mounted
- Sample Trader via `?view=sample&symbol=`
- Banner + Vitest isolation checks

## How it works now

Live and sample are mutually exclusive App shells. Sample never calls scanner/HOD/watchlist/decide network for table data. Leaving sample restores the live dashboard URL without `view=sample`.

## Why this approach

- **Hard route gate** (not “fill empty rows”) — only way to honor never-mix.
- **Frontend fixtures** — matches orders/chart sample precedent; no backend `/api/sample` alias risk.
- **Rejected:** history-select fake date; seeding live caches; mixing mock into `useScannerData` when empty.

## Verification

`npx vitest run src/sample_data src/pages/SampleDashboardPage.test.tsx` — 6 passed.

## Follow-ups

Account/Trading tab under sample still uses shared IBKR UI with sample stubs (paper, locked spend). Journal stays empty on purpose (no fixture set yet).

## Keywords

sample data, view=sample, fixtures, gappers, hod momo, isolation
