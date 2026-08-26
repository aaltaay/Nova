# 2026-08-26 -- Reclaim Trader header space

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / trader UI
- **Related:** `CHANGELOG.md` §2026-08-26 Trader last/change under Stock Quote · `deferred_log=none`

## Task

Move ticker last/change under Stock Quote, put the ET clock next to Desk, drop the After Hours label under the clock, and delete the leftover Trader command bar so charts get the vertical space.

## Goal

No second header row of CRE $price + clock. Session is the existing mode badge. Pop-out / close still work.

## Why it mattered

That bar duplicated Stock Quote and the header AFTER HOURS chip. It stole a full row of chart height for information the operator already had.

## What we changed

- Deleted `StockViewHeader` (symbol chip + clock + session span).
- `StockViewQuotePrice` renders symbol / last / change inside the Stock Quote card (`StockViewDepthTape` all branches, and `StockViewQuoteCard` by default).
- `StockViewMarketClock` is time-only (`19:05:22 ET`); session stays on `title`.
- `HeaderConnectionStatus` mounts that clock immediately after the Desk chip.
- Tab strip padding tightened; tab strip itself stays (needed for add / pop out / close).

## How it works now

Global bar owns Desk + clock + Paper/Live + account numbers + the session mode badge. Stock Quote owns last/change. Trader tabs own ticker identity for pop-out/close. Paper banner still shows when Gateway is paper.

## Why this approach

Putting price in Stock Quote is the same surface the operator already stares at for bid/ask. Putting the clock next to Desk is always visible on Scanner and Trader without a second bar. Dropping the session span under the clock avoids two After Hours labels. Keeping the tab strip (instead of deleting every pixel under the global bar) is required: that is how a tab pops out and closes. A draft-tab `+` cannot live only in the global SYMBOL box without a new ADR.

Rejected: stuffing last/change into the tab label (tabs would grow and fight the 3-tab cap). Rejected: moving the clock into the mode badge (that chip is session name, not a ticking clock).

## Verification

- `npx vitest run` in `frontend/`: 170 files, 819 passed.
- `npm run build`: `tsc -b && vite build` exit 0.
- Playwright system Chrome, `http://127.0.0.1:5173/?view=sample&symbol=AAPL`: `stock-view-header` count 0, quote price visible, clock text matches `HH:MM:SS ET` with no After Hours, clock x immediately after Desk.

Live Playwright e2e (`/?view=stock`) was not used as proof: API on :8000 was refused this turn, so ticker rail never hydrates. Sample route supplies ticker fixtures without a second API.

## Follow-ups

Do not start a second `run_api.py` to make live e2e green while an instance lock may still claim a PID. Tab strip stays unless the operator asks to fold it into the global bar.

## Keywords

trader, stock quote, market clock, desk, after hours, header, vertical space
