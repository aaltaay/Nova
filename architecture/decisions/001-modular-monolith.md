# ADR 001 — Modular monolith

**Status:** Accepted · **Date:** 2026-07-16

## Context

Nova is a local-first single-operator trading workstation: one FastAPI process, one IBKR Gateway connection, Electron/Vite UI. Splitting into microservices would multiply ops cost and break the single IBKR session model.

## Decision

Keep **one deployable backend process** and one frontend app. Structure internals as a modular monolith with clear package boundaries (domain / application / adapters / delivery / composition).

## Consequences

- No message broker or service mesh.
- Shared-memory caches remain valid if owned by explicit state modules.
- Scaling is vertical / process isolation only if ever needed later — out of this program's scope.

## Rejected alternatives

- Microservices per scanner/HOD/execution
- Separate “market data service” process
