# 🏛️ gemini.md — Project Constitution
> **Status:** BLUEPRINT — Awaiting User Approval
> **Last Updated:** 2026-04-13
> **Project:** Nova — Stock Alert Automation System

---

## ⚖️ Architectural Invariants (Law)

1. **Data-First:** No tool is written before the JSON schema is confirmed here.
2. **Deterministic Tools:** All Python scripts in `tools/` must be atomic, testable, and side-effect-free unless explicitly noted.
3. **Secrets in `.env` only:** No API keys, tokens, or credentials ever appear in source code.
4. **`.tmp/` is ephemeral:** Never treat `.tmp/` files as a source of truth.
5. **SOP before code:** If logic changes, update `architecture/` first.
6. **Self-Annealing:** Any error → Analyze → Patch → Test → Update `architecture/` SOP.

---

## 📐 Data Schema
> ⚠️ PENDING — Awaiting Discovery Question answers before schema is defined.

### Input Payload (Raw)
```json
{
  "symbol": "AAPL",
  "previous_close": 150.00,
  "current_price": 155.00,
  "gap_percent": 3.33,
  "volume": 1200000,
  "timestamp": "2026-04-14T08:30:00Z"
}
```

### Output / Delivery Payload
```json
{
  "health": {
    "status": "connected",
    "latency_ms": 45
  },
  "gappers": [
    {
      "symbol": "AAPL",
      "previous_close": 150.00,
      "current_price": 155.00,
      "gap_percent": 3.33,
      "volume": 1200000
    }
  ]
}
```

---

## 🔗 Integrations & Services
> ✅ CONFIRMED

| Service | Purpose | Status |
|---------|---------|--------|
| Alpaca API | Source of truth for market data | ❌ Unverified |
| Web UI (Localhost) | Delivery dashboard for gappers | ❌ Unverified |

---

## 📋 Behavioral Rules
> ✅ CONFIRMED

- **Read-Only Mode**: The system only reads market data from API and does not execute or manipulate trades.
- **Market Open Halt**: The gapper dashboard stops updating its data feed once the market formally opens.
- **Configurable**: API keys and base URLs must be configurable via UI.
- **Git Commit & Push After Every Task**: After completing any task, the assistant MUST run `git add .`, `git commit -m "<descriptive message>"`, and `git push origin master`. No exceptions — the user should never have to remind this.

---

## 🔧 Maintenance Log

| Date | Change | Author |
|------|--------|--------|
| 2026-04-27 | Added mandatory git commit & push rule | User Directive |
| 2026-04-13 | Project Constitution initialized | System Pilot |
