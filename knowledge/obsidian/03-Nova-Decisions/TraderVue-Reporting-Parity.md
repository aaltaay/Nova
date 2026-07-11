# TraderVue Reporting Parity (Nova)

**Date:** 2026-07-11  
**Source:** Live session on `app.tradervue.com` (Free plan) via isolated `agent-browser`.  
**Screenshots:** `downloads/tradervue-research/` (gitignored; not committed).

## What TraderVue shows (reports that matter)

### Calendar (critical)

- **Entry:** Reports → Overview → **Calendar** (`/reports/overview?subrep=cal`), also a top-nav **Calendar** item.
- **Default:** **Year view** — 12 month mini-calendars in a grid; year selector (e.g. `2026`).
- Each month card has an **Open** control.
- **Open month:** expands to a full month grid:
  - Header: `Monthly P&L: $X.XX`
  - Each day cell: date number, **net $ P&L**, **trade count** (e.g. `$0` / `0 trades`)
  - Leading/trailing days from adjacent months are dimmed
  - Week **Total** column: week P&L + trade count
- Days with profit/loss are color-coded (green win / red loss) when data exists.
- P&L type: Gross (Net is Gold); view mode: `$ Value`.

### Other Overview modes

- **Recent:** 30 / 60 / 90 day aggregate P&L charts.
- **Year/Month/Day:** hierarchical rollups (not opened in depth this session).

### Report sub-tabs (growth / analytics)

| Tab | Notes |
|-----|--------|
| Overview | Calendar / Recent / YMD above |
| Detailed | Per-trade / deeper stats |
| Win vs Loss Days | Winning vs losing **days** totals & averages (Silver/Gold gated on Free) |
| Drawdown | Equity drawdown analysis |
| Compare | Period / tag comparisons |
| Tag Breakdown | Performance by tags |
| Advanced | Extra breakdowns |

Filters (all reports): Symbol, Tags, Side, Duration, date range, Custom Filters.

### Skipped for Nova

- **Import Trades** (and broker import UX) — Nova already journals trades.
- Community, New Trade manual entry, Gold-only Net/Risk modes.
- Tag system / custom filters (future).

## What Nova will mirror (v1)

1. **Reports** top-level tab with a **year calendar** of daily net P&L from journal closed trades (`closed_ts`, America/New_York calendar day).
2. **Open month** → monthly P&L + day cells ($ + trade count) + week totals.
3. **Growth summary:** year P&L, winning/losing/flat day counts, best/worst day (Win-vs-Loss-Days lite).
4. **Show demo data** toggle (same pattern as Journal) — mock trades excluded by default.
5. **API:** `GET /api/journal/calendar?year=YYYY` and optional `&month=M`.

## Explicit non-goals (v1)

- Broker import
- Tags / custom filters
- Drawdown chart, 30/60/90 Recent charts (follow-up)
- Gross vs Net commissions split
