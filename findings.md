# 🔬 findings.md -- Research & Discovery Log
>
> **HISTORICAL (2026-04).** Not current product law.
> Live SoT: `AGENTS.md`, `.cursor/rules/single-market-data-feed.mdc` (IBKR prices/scanner; Alpaca news/listing only).
>
> **Project:** Stock Alert Automation System
> **Status:** Archived discovery answers
> **Last Updated:** 2026-08-05 (banner only)

---

## Discovery Answers
>
> ✅ RECORDED ON 2026-04-14 (superseded for market-data SoT)

| Question | Answer |
|----------|--------|
| North Star (singular outcome) | Identify gappers (stocks gapping up from previous day) from pre-market until market open. |
| Integrations (external services) | Alpaca API, local web server. |
| Source of Truth (primary data) | HISTORICAL answer was Alpaca; current SoT is IBKR Gateway (see single-market-data-feed.mdc). |
| Delivery Payload (how/where results go) | Local web dashboard with API health status and config. |
| Behavioral Rules (tone, logic constraints) | HISTORICAL read-only scan era; gated IBKR orders exist now (Invariant #7); `auto_live` NO-GO. |

---

## Research Notes
>
> Will be populated after Discovery Answers are received.

### Potential Libraries

- `yfinance` — Yahoo Finance API wrapper (free, no key required)
- `alpaca-trade-api` — Brokerage + market data API
- `pandas` — Data manipulation
- `schedule` / `APScheduler` — Python job scheduling
- `smtplib` / `sendgrid` — Email delivery
- `slack_sdk` — Slack notification delivery
- `twilio` — SMS delivery

### Rate Limits & Constraints
>
> To be discovered in Phase 2 (Link)

---

## API Gotchas
>
> Will be populated as discovered during development.
