# 🔬 findings.md — Research & Discovery Log
>
> **Project:** Stock Alert Automation System
> **Status:** Blueprint in Progress
> **Last Updated:** 2026-04-13

---

## Discovery Answers
>
> ✅ RECORDED ON 2026-04-14

| Question | Answer |
|----------|--------|
| North Star (singular outcome) | Identify gappers (stocks gapping up from previous day) from pre-market until market open. |
| Integrations (external services) | Alpaca API, local web server. |
| Source of Truth (primary data) | Alpaca Market Data API. |
| Delivery Payload (how/where results go) | Local web dashboard with API health status and config. |
| Behavioral Rules (tone, logic constraints) | Read-only mode for market data; stops updating once market opens. |

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
