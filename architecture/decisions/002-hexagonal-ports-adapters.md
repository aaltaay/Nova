# ADR 002 — Selective hexagonal ports/adapters

**Status:** Accepted · **Date:** 2026-07-16

## Context

Provider branching (IBKR vs Alpaca) currently leaks into orchestration (`ticker.py`, scanners). Silent fallbacks are forbidden by `single-market-data-feed.mdc`.

## Decision

Introduce **narrow Python `Protocol` ports** only where boundaries pay for themselves:

- Discovery / scanner snapshots
- Market data (quotes, bars, depth, tape) with **explicit provider selection**
- Execution (already gated via IBKR module)
- Persistence (JSON/SQLite/R2)

Concrete IBKR/Alpaca/R2 code lives in **adapters**. Application use cases depend on ports, not SDKs.

## Consequences

- Ports must **not** invent Alpaca fallback when `discovery=ibkr`.
- Not every function needs a port — avoid generic Repository wrappers that only rename calls.
- Phase 8 ticker/scanner work is the primary consumer of new ports.

## Rejected alternatives

- Full DI container / framework-wide service locator
- Rewriting all Alpaca calls behind ports in one pass
