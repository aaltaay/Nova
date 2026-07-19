# 2026-07-18 — IBKR paper hard-pin (no accidental live)

- **Status:** completed
- **Agents:** parent
- **Domain:** execution / IBKR safety
- **Related:** `CHANGELOG.md` §2026-07-18 IBKR paper hard-pin · `PROBLEM_LOG.md` §2026-07-18 Paper Gateway could still attach to live

## Task

Make paper practice have no automatic path onto live Gateway / live account spend.

## Goal

When `IBKR_GATEWAY_MODE=paper`, Nova must not connect to live for spend, must verify IB account ids look like paper, and must refuse place on any mismatch. Live remains behind `IBKR_LIVE_TRADING_CONFIRMED`.

## Why it mattered

Self-heal could flip paper→live when 4002 was down. `account_mode` was only a port/env label, not proof of a DU paper account. User asked for zero chance of messing up while practicing.

## What we changed

- Added `ibkr/account_kind.py` (DU/DF = paper; classify managedAccounts).
- `gateway_heal`: only live→paper; `heal_target_allowed`.
- `client.py`: after connect, classify accounts; disconnect on paper pin fail; never heal paper→live; status field `broker_account_kind`.
- `safety.assert_orders_allowed`: paper requires env+connection+kind all paper; live env always needs `IBKR_LIVE_TRADING_CONFIRMED`.
- Wired kind through orders / execution validate / auto_paper gate.
- Tests + `.env.example` + CHANGELOG / PROBLEM_LOG.

## How it works now

Three layers: (1) preferred port from env, (2) self-heal only toward paper, (3) managedAccounts must be paper when mode is paper, else disconnect + refuse place. Cancel stays softer (protective).

## Why this approach

- Rejected “trust the port” — IB can have the wrong login on a port.
- Rejected bidirectional heal — fail-safe is always paper.
- Rejected deleting spend gates — keep ORDERS_ENABLED + LIVE_CONFIRMED.
- Account-id heuristics (DU/DF) match IB’s conventional paper prefixes; unknown/mixed fail closed in paper mode.

## Verification

- `pytest` paper-pin suite: 82 passed (account_kind, gateway_heal, safety, execution, auto_paper, routes, executor).
- Live `GET /api/ibkr/status`: `mode=paper`, `broker_account_kind=paper`, `spend_status=paper_armed`, `live_trading_confirmed=false`.

## Follow-ups

- Do not set `IBKR_LIVE_TRADING_CONFIRMED=true` for practice.
- If IB ever changes paper account prefixes, extend `account_kind.py`.
- Commit/push when user asks (working tree may include unrelated WIP).

## Keywords

paper pin, managedAccounts, DU, self-heal, IBKR_GATEWAY_MODE, broker_account_kind, live money
