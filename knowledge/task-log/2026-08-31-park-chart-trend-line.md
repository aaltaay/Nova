# 2026-08-31 -- Park chart Trend Line two-click (D-010)

- **Status:** completed
- **Agents:** parent
- **Domain:** docs / widgets
- **Related:** `CHANGELOG.md` 2026-08-31 DEFERRED_LOG to-do list · `DEFERRED_LOG.md` D-010

## Task

Record that Trend Line drawing is broken (two-click place pans the chart instead) and do **not** fix it. Make the deferred-log tool the to-do / what's-missing / priorities list, and make every agent check that page before starting a fix.

## Goal

D-010 exists, `priorities` lists it, and the next session cannot "improve" chart drawings without reading that entry.

## Why it mattered

The operator uses trend lines as a daily desk control. The current click path pans the X-axis instead of dropping two anchors. They do not want another custom armed/ready click collector, and they do not want a later agent to start a parallel fix that ignores this page.

## What we changed

- Parked **D-010** in `DEFERRED_LOG.md` (status `parked`, P1, Effort L). No chart / drawing-manager code changed.
- Added CLI alias `py -3 tools/deferred_log.py priorities` (= `status`).
- Tightened always-on rules so agents search `DEFERRED_LOG.md` **before any fix**, and answer "what's missing / priorities" from that tool: `deferred-log.mdc`, `constitution.mdc`, `specialist-routing.mdc`, `self-annealing.mdc`, `AGENTS.md` §7.2c / §9 / §11 / §12, `docs/agent-operations.md`.

## How it works now

The parking lot file is repo-root `DEFERRED_LOG.md`. Ranked list:

```text
py -3 tools/deferred_log.py status
py -3 tools/deferred_log.py priorities
```

`parked` means do not start it. D-010 unblocks only when the operator names that ID. Then the job is a library that already does two-click place, not more Nova `pendingAnchorRef` code.

## Why this approach

Recording-only this session, because the operator forbade a drawing rewrite while the desk is live. A durable `D-NNN` plus a real `priorities` alias beats a chat note or an agent-memory Backlog line, because the next chat's session brief and the "what's on the to-do" ask both hit the same file.

Rejected: fixing the gesture now (explicitly forbidden). Rejected: another custom click state machine (operator asked for a library that already does two clicks). Rejected: a second to-do tracker (Roadmap-Status is product NEXT, not this queue).

## Verification

`py -3 -m pytest tools/test_deferred_log.py -q` and `py -3 tools/deferred_log.py priorities` (must include D-010). No Nova app launch -- record-only, no product code.

## Follow-ups

Do not start D-010 until named. When unblocked: two-click Trend Line without pan; prefer `lightweight-charts-drawing` native placement or a replacement library.

## Keywords

DEFERRED_LOG, D-010, priorities, Trend Line, two-click, pan, lightweight-charts-drawing
