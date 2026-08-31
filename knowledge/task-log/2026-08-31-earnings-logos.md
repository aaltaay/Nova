# 2026-08-31 -- Earnings card Finnhub logos

- **Status:** completed
- **Agents:** parent
- **Domain:** earnings / UI
- **Related:** `CHANGELOG.md` 2026-08-31 Earnings logos · prior task-log `2026-08-31-earnings-scanner-tab.md`

## Task

Show company logos on Earnings calendar cards.

## Goal

Cards look more distinctive: Finnhub logo when available, letter fallback when cold/missing/broken.

## Why it mattered

Calendar rows alone read as a dense text list. Logos make the desk scan faster and feel less generic.

## What we changed

- New `backend/earnings_logos.py`: paced Finnhub `profile2` warm + disk cache (`earnings-logos.json`, `schema_version`, hit/miss TTL).
- `earnings_calendar._decorate` attaches `logo_url` cache-only; visible-range symbols queued on each view build.
- Constants for profile2 URL + pacing/TTL; `EarningsCard` + CSS letter/image chip; `logo_url` on the TS type.

## How it works now

`/calendar/earnings` still has no logos. Each symbol may get one background `GET /stock/profile2`. HTTP never waits on that. After warm, polls include `logo_url`; the UI paints `<img>` or the first letter of the ticker.

## Why this approach

**Required.** Rejected bundling logos into the calendar fetch (Finnhub does not offer that). Rejected Clearbit-by-domain (needs another lookup). Rejected blocking decorate on profile2 (would stall the tab under free-tier limits). Paced single-flight warm + long hit TTL matches how we already warm yfinance fundamentals for names.

## Verification

- `py -3 -m pytest tests/test_earnings_logos.py tests/test_earnings_calendar.py tests/test_earnings_enrich_hooks.py tests/test_routes_earnings.py -q` -- 21 passed
- `npx vitest run src/earnings` -- 11 passed
- `npm run build` -- exit 0
- Live `/api/earnings?range=today`: `logo_url` filling in after paced warm (e.g. 3+ of 21 within seconds); IBKR still connected; Vite up

## Follow-ups

Busy week/month views fill logos over ~1s per missing symbol on free tier; leave the tab open or re-poll. Do not invent implied move/IV.

## Keywords

earnings, logo, finnhub, profile2, earnings_logos, EarningsCard
