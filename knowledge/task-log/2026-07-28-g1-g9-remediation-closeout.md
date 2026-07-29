# 2026-07-28 -- G1-G9 HOD capture remediation closeout

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / hod-momo / archive / ibkr-ops
- **Related:** audit `docs/audits/2026-07-28-hod-scanner-capture-audit.md` §5b · per-finding task-logs G1-G9

## Task

Close the approved seven-phase remediation of capture-audit findings G1-G9.

## Goal

Every finding mapped to a shipped commit; audit doc updated; full backend suite green; 2026-07-17 replay identical to the audit baseline.

## Why it mattered

Without these fixes, reconnect zombies, delayed-data silence, missing L1/enrichment archives, restart grace loss, roster lag, and Former Momo crowd-out left "did we capture it?" unanswerable or false-negative.

## What we changed

Phased commits (newest last):

| Finding | Commit |
|---------|--------|
| G1+G4 | `79f749e` |
| G5 | `f17b3fd` |
| G2+G3 | `23bae29` |
| G9 | `c4e03ad` |
| G8 | `dceb6f3` |
| G6 | `c51e27f` |
| G7 | `bcd6283` |

Plus this closeout (audit §5b + aggregate log).

## How it works now

READY clears zombie L1 + installs session errors + requests live MD type. Active-set L1 ticks and enrichment snapshots archive. Roster commits wake reconcile. Former Momo capped at 20. Grace clock persists. Status/UI surface delayed.

## Why this approach

One commit per phase kept bisectability and risk isolation. Historical fixtures intentionally unchanged -- G5/G6 only cover new sessions.

## Verification

- `pytest tests/` (PYTHONPATH includes repo root) -- 1010 passed
- `hod_momo_replay.py --date 2026-07-17` -- 88 alerts; SDOT/BIYA/CJMB strategies 11/12 (matches audit)

## Follow-ups

P3: share consolidation-flush grouping between live alerts and replay mirror (harness drift only).

## Keywords

G1-G9, capture remediation, closeout, hod momo, archive
