# 2026-08-18 -- Reliability track: morning autopilot wiring + root-pattern guards

- **Status:** completed (tooling); WS1 unattended proof still pending
- **Agents:** parent
- **Domain:** market-feed / ibkr-ops / docs
- **Related:** `CHANGELOG.md` 2026-08-18 Reliability track · `PROBLEM_LOG.md` 2026-08-18 pytest cache isolation · Jul 30 OPEN/DEFERRED premarket stack · `knowledge/task-log/2026-08-18-problem-log-pattern-analysis.md`

## Task

Implement the problem-root elimination plan: close each of the five PROBLEM_LOG root patterns with bounded workstreams, centered on unattended pre-04:00 ET bring-up plus a loud failure alert.

## Goal

Make whole bug classes mechanically hard to repeat. Do not claim the morning class FIXED until a real 03:55 ET evidence line exists.

## Why it mattered

The operator's lived experience is "broken every morning" despite 236 logged fixes. The pattern analysis showed 4 of 5 roots already had architecture patches; what was missing was wiring and guards.

## What we changed

- WS0: Reliability track section in `Nova-Roadmap-Status.md`
- WS1: `notify_system_event` + `POST /api/alerts/system-event`; `scripts/Invoke-NovaMorningCheck.ps1`; installer 03:40 start + 03:55 check tasks; IBC AutoRestartTime AM/PM warn
- WS2: `tools/maintainer_lib/ib_loop.py`; CI `--fail-on-kind ib_loop_sync_io` (not `--fail-on-findings` -- 50 pre-existing non-baseline findings would brick CI)
- WS3: `table_state` / `roster_ts` / `feed_error` on `/api/gappers`, `/api/movers`, `/api/afterhours`; smoke_check consumes them
- WS4: `.cursor/rules/persisted-state.mdc`; corrupt `alerts_channels.json` logs ERROR
- WS5: audit -- Alpaca bars path in `chart_bars.py` is gated behind non-ibkr discovery (config coerces to ibkr); qty SSOT remains `ib.positions()` with portfolio MTM join; Orders Today is ledger overlay. No anti-pattern list extension needed
- WS6: `conftest.py` sets `NOVA_CACHE_DIR` before backend imports; autouse rebinds cache snapshots + paper Gateway mode
- WS7: blast-radius table in `verification-before-completion.mdc`

## How it works now

Scheduled start at 03:40 ET (backstops at 06:00 + logon). Self-check at 03:55 walks Gateway port -> `/api/health` (IB loop not wedged) -> IBKR connected -> gappers honesty (`feed_error` / `table_state` / premarket row count) -> integrity. Failure POSTs a system event that names the leg; if the API is down, PowerShell POSTs the Discord/webhook URL from `alerts_channels.json`. Weekly 2FA still needs the phone.

## Why this approach

Rejected rewriting IBC or adding SMS. Phase D senders already existed; the gap was the check and the hook. Rejected CI `--fail-on-findings` because it would fail the tree on 50 unrelated findings -- `--fail-on-kind` matches the new invariant. Rejected claiming Jul 30 FIXED: verification-before-completion forbids proof-by-code-change.

## Verification

- backend focused alert/scan tests: 29 passed
- persist/isolation: 44 passed
- backend suite: 1239 passed (ignored `test_execution_latency_regressions.py` pre-existing `tools` import from backend cwd)
- `tools/test_maintainer_checks.py`: 28 passed
- `py -3 tools/maintainer_checks.py --fail-on-kind ib_loop_sync_io`: exit 0
- `py -3 tools/doc_invariants.py`: OK
- `py -3 tools/agent_contract.py --ci`: PASS
- `npm run build`: tsc + vite exit 0

## Follow-ups

- Human: configure a Phase D channel; `.\scripts\Install-NovaDailyTask.ps1`; wake timers; first overnight evidence line
- Do not flip Jul 30 PROBLEM_LOG to FIXED until that line exists
- Optional later: CI `--fail-on-findings` after baselining the 50 existing findings

## Keywords

morning check, system-event, feed_error, table_state, NOVA_CACHE_DIR, ib_loop_sync_io, blast radius, persisted-state, NovaDailyStart, 04:00 ET
