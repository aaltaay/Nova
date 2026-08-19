# 2026-08-19 -- Paper/Live door trail

- **Status:** completed
- **Agents:** parent
- **Domain:** ibkr-ops
- **Related:** `CHANGELOG.md` 2026-08-19 Paper/Live door trail · ADR 013

## Task

Record who clicked Paper/Live and whether the IB account class actually switched, in a place agents can read without grepping blast.log.

## Goal

A durable trail: operator click + IBC plan, then attach or refuse.

## Why it mattered

Nova OS events and the execution ledger are for decisions and orders. Door switches were HTTP logs only. After a messy Live click nobody could answer "did we switch?" from the audit UI.

## What we changed

- `ibkr/gateway_trail.py` JSONL under cache (`ibkr-gateway-trail.jsonl`, schema_version 1)
- Writes from `request_gateway_mode` and `accept_connected_session` (including follow-paper / refuse)
- `GET /api/ibkr/gateway-trail` and last 8 rows on `/api/ibkr/status`

## How it works now

`actor=operator` is a click. `plan=noop` means already on that class. `plan=force_ibc` means Gateway restart was requested. Later `attached` / `refused` with `switched` true/false is the IB truth. No full account ids.

## Why this approach

Not Nova OS `record_receipt` -- that vocabulary is decide/execute. Not the execution ledger -- that is orders. A small JSONL with owner + schema_version matches persisted-state rules and stays readable.

## Verification

pytest `test_gateway_trail.py`, `test_gateway_mode_switch.py`, `test_ibkr_account_kind.py`.

## Follow-ups

No Activity-panel UI yet. Ask if that should show door rows next to orders.

## Keywords

gateway trail, Paper, Live, audit, switched
