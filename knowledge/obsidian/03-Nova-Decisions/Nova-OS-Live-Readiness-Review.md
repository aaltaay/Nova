# Retired Live-Readiness Review

**Status:** Retired by operator decision, 2026-10-13, #791.
**Canonical status:** [[Nova-Roadmap-Status]]

The operator decides whether research evidence is convincing. Required Paper samples, reviewed days,
expectancy/adherence thresholds, drills, GO/NO-GO verdicts and the Live short proof are not trading permission
and are no longer an operator workflow. `tools/live_readiness_scorecard.py` is retired and removed.
Research results and measurements can remain informative, with their assumptions and limitations stated.

Explicit operator Live opt-ins/PIN, broker/account eligibility and common order safety remain. Nothing in
this decision arms the desk, changes a configuration key, places an order or authorizes a Live bot.
`auto_live` remains NO-GO because the product prohibits Live bots, not because a scorecard has not passed.

The former Nova OS mode ladder and executor were retired by ADR 025. Paper/Sim use Nova's practice ledgers
and their own clocks; the legacy paper Gateway is not a prerequisite or an automatic fallback.
