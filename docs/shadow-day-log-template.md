# Phase B — Shadow day log template

Copy one row into `knowledge/obsidian/03-Nova-Decisions/Nova-Roadmap-Status.md` → Phase B Evidence after each market day. Do **not** mark Phase B `[x]` until ≥5 days are logged with reviews.

## Per-day checklist

| Field | Fill in |
|-------|---------|
| **Date (ET session)** | YYYY-MM-DD |
| **Modes used** | `signal` → `confirm` → `auto_paper` (note which hours) |
| **IB Gateway** | paper port connected? Y/N — API port |
| **Discovery provider** | `ibkr` / `alpaca` |
| **Signals seen** | count + setups (gap_and_go / bull_flag / abcd) |
| **Staged / approved** | count staged; count approved; count rejected |
| **Paper fills** | count closed brackets (non-mock journal) |
| **Evening review** | `GET /api/archive/review/YYYY-MM-DD` — ok / empty / error |
| **walk_day** | ran? Y/N — note if cold day missing |
| **Bugs filed** | PROBLEM_LOG entry titles or “none” |
| **Notes** | slippage, UI issues, feed honesty, operator mistakes |

## Hard rules reminder

- `auto_live` is **NO-GO** — do not attempt to enable
- Empty scanners with discovery=`ibkr` → check Gateway login first
- Demo/mock journal rows do **not** count toward live-readiness sample

## Progress tracker

| # | Date | Modes | Review artifact | PROBLEM_LOG |
|---|------|-------|-----------------|-------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

**Exit:** five completed rows + still NO-GO for live until Phase I evidence review.
