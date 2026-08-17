# 2026-08-07 — Small Account Challenge PDF downloads + daily workflow plan

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / warrior library
- **Related:** `Local-Library-Inventory.md` · video `xGIa8Vg0PWM` · kit `warriortrading.com/small-account-kit/`

## Task

Download the four free PDF worksheets linked from Ross's $2k→$65k YouTube class into Nova's Warrior resources tree, update the local library inventory, and outline how to use the trading plan + trade log every day without hand-filling PDFs.

## Goal

PDFs on disk under the canonical resources root; inventory accurate; clear automation path that maps worksheet fields onto Nova journal/scanners/risk.

## Why it mattered

The worksheets are the daily operating system for a small-account challenge. Leaving them as printed PDFs guarantees they will not be used; wiring them into Nova is how the criteria become habit.

## What we changed

- Fetched CDN PDFs into `downloads/warrior-trading-resources/small-account-challenge/` (gitignored) + folder `README.md`
- Updated `knowledge/obsidian/01-Courses/Warrior-Trading/Local-Library-Inventory.md`
- Updated `downloads/warrior-trading-resources/README.md` folder table

Files:

| File | Role |
|------|------|
| `SAC2024-Strategy-PDF.pdf` | Small Account Strategy |
| `Sample-Trading-Plan.pdf` | Trading Plan Worksheet |
| `Warrior-Trading-Stock-Selection.pdf` | Stock Selection Guide |
| `PDF-of-Weekly-Reporting.pdf` | Trade Log / weekly reporting |

## How it works now

Kit page exposes four "Download PDF" links to `cdn.warriortrading.com/...`. Local copies live under `downloads/warrior-trading-resources/small-account-challenge/`. Inventory notes they are educational source criteria; daily execution should use Nova journal + scanners, not re-printing.

## Why this approach

- **CDN pull after kit page hrefs** -- form-gated landing page (`warrior.app/30-days-downloads`) does not expose PDFs; kit page does. Avoided inventing filenames or emailing through Marketo.
- **Resources root, not slides** -- these are free worksheets, not LMS chapter slides; matches existing `free/` / `excel/` layout.
- **Digitize-for-daily-use (proposed next)** -- rejected "open PDF every morning" as the workflow. Map plan fields → active plan config; map trade-log columns → journal enrichment + IBKR import; map stock-selection pillars → scanner/HOD filters. PDFs stay the reference; Nova is the ritual.

## Verification

- All four files start with `%PDF-`; sizes ~60KB–1.2MB
- agent-browser kit page showed four Download PDF links matching Ross's spoken list
- Inventory + resources README updated

## Follow-ups

1. Active trading-plan config (YAML/JSON + optional Premarket UI) with daily max loss / price range / setup
2. Journal column parity for trade-log fields (5 pillars, RVOL, float, news, hold time, cents/share)
3. EOD/weekly rollup from journal → Reports (avg win/loss, accuracy)
4. Optional Pinecone ingest of strategy + stock-selection PDFs (`--layout all`)

## Keywords

warrior trading, small account challenge, SAC, trading plan worksheet, trade log, weekly reporting, stock selection, downloads, journal automation
