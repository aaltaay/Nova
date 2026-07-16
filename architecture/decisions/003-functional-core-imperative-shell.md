# ADR 003 — Functional core / imperative shell

**Status:** Accepted · **Date:** 2026-07-16

## Context

Pure gate evaluation already exists (`hod_momo_filters.py`, Nova OS decision pieces). I/O, retries, WebSocket broadcasts, and IBKR SDK calls must stay at the edge.

## Decision

- **Functional core:** pure calculations, filters, scoring, serialization helpers — no FastAPI, filesystem, network, or module globals.
- **Imperative shell:** loops, subscriptions, persistence, broadcasts, adapter calls.

## Consequences

- New business rules prefer pure modules with explicit inputs/outputs.
- Characterization tests can pin pure cores without mocking Gateway.
- Shell modules may be larger but must stay within file-size limits via focused extraction.

## Rejected alternatives

- Object-heavy domain model with entity graphs for every scanner row
