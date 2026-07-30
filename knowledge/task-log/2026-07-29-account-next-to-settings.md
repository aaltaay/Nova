# 2026-07-29 -- Account control next to Settings on GlobalAppBar

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chrome
- **Related:** `CHANGELOG.md` §2026-07-29 -- Account control next to Settings on GlobalAppBar

## Task

Move Account from the scanner AppHeader next to Settings on the shared top bar.

## Goal

Account sits immediately left of Settings on GlobalAppBar; still opens the Account/Trading tab.

## Why it mattered

Account was mid-header beside Today/SYMBOL while Settings lived on GlobalAppBar -- inconsistent chrome.

## What we changed

- GlobalAppBar Account button → `requestOpenTradingTab()` (+ close Trader if open)
- Removed live AppHeader Account wiring; sample AppHeader keeps optional Account
- `accountNavActive` broadcast for active highlight

## How it works now

Top-right cluster: … mode chip | Account | Settings. Same open-trading latch as Working menu "View All Orders".

## Why this approach

Reuse existing `requestOpenTradingTab` latch instead of prop-drilling activeTab into GlobalAppBar. Sample mode keeps AppHeader Account because SampleShell has no SettingsProvider GlobalAppBar gear path for Account.

## Verification

Vitest GlobalAppBar Account click; e2e testid updated.

## Follow-ups

None.

## Keywords

Account, GlobalAppBar, Settings, requestOpenTradingTab
