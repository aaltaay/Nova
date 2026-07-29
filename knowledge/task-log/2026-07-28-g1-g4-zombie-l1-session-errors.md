# 2026-07-28 -- Fix G1 zombie L1 subs + G4 session errorEvent

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / hod-momo
- **Related:** `CHANGELOG.md` § 2026-07-28 Fix G1/G4 · `PROBLEM_LOG.md` § zombie L1 · audit G1/G4

## Task

Remediate capture-audit findings G1 (zombie L1 subscriptions after reconnect) and G4 (unhandled IB error codes 1100/1101/1102/2104/2106/2108/101/10167).

## Goal

After READY, L1 ownership maps are cleared and a session-level errorEvent hook is installed; the former strict xfail reconnect test passes.

## Why it mattered

Silent capture death after Gateway reconnect -- HOD looked subscribed while no ticks flowed. Connectivity/farm/capacity/delayed notices were invisible.

## What we changed

- `ticks.clear_all_subscriptions` + `client._on_session_ready` at both READY sites
- New `ibkr/session_errors.py` + constants + `scanner_l1.note_capacity_error`
- Removed xfail; added `test_ibkr_session_errors.py`

## How it works now

READY clears zombie `_subs` (no cancelMktData on dead socket), installs errorEvent. Reconcile re-subscribes. 1100 -> DEGRADED; 101 -> L1 error string; 10167 -> delayed flag for Phase 3.

## Why this approach

Push clear at READY (same pattern as sticky-bridge-error clear) instead of polling -- avoids a zombie window. Session-level hook rather than per-feature hooks so codes fire even without tape/depth.

## Verification

`pytest tests/test_hod_pipeline_fake_feed.py tests/test_ibkr_session_errors.py tests/test_scanner_l1.py` -- 17 passed.

## Follow-ups

Phase 3 surfaces `is_delayed_data()` in `/api/ibkr/status` + UI badge.

## Keywords

zombie L1, session_errors, Error 1100, Error 101, Error 10167, clear_all_subscriptions
