# 2026-08-25 -- Graphify always-on wrapper + token meter

- **Status:** completed
- **Agents:** parent
- **Domain:** docs
- **Related:** `CHANGELOG.md` §2026-08-25 Graphify always-on wrapper · `PROBLEM_LOG.md` §2026-08-25 Graphify wired opt-in

## Task

Fix Graphify wiring so agents actually query it, and add a must-have token-savings counter so we can keep or delete the tool on evidence.

## Goal

Every vault/decision "what connects X" ask goes through a wrapper that records honest savings. The scoreboard is visible on session start.

## Why it mattered

The CLI worked. Agents skipped it. `cost.json` only counted rebuilds. Without a savings number, Graphify was an unpaid tax.

## What we changed

- `graphify.mdc` is always-on and short (`alwaysApply: true`)
- `tools/graphify_ask.py` + `tools/graphify_usage.py` record cited-note savings
- Session brief prints the meter
- Skill copies / vault notes / `CLAUDE.md` / `AGENTS.md` §12 point at the wrapper

## How it works now

`saved = tokens(cited source notes) - tokens(query stdout)`. `src=None` or missing files count as 0. Footer: `graphify_usage used=.. avoided=.. saved=.. queries=.. total_saved=..`. Status: `py -3 tools/graphify_ask.py status`. If `total_saved` stays 0, delete Graphify. ADRs stay in `architecture/decisions/` -- the graph does not contain them.

## Why this approach

A wrapper beats "please remember save-result" because agents already forgot that. Cited-note savings beats "whole vault minus query" because the second number is fake (nobody reads the whole vault). Always-on rule is tiny so the per-chat tax stays small; the 600-line rebuild skill stays on-demand.

Rejected: making Graphify an MCP tool this turn (CLI already works). Rejected: ingesting ADRs into the graph this turn (separate rebuild, not the skip-it bug).

## Verification

`py -3 -m pytest tools/test_graphify_ask.py tools/test_session_brief_hook.py` and a live wrapper query that prints the footer.

## Follow-ups

Rebuild the vault graph when notes go stale. Optional later: ingest `architecture/decisions/`. Do not treat `cost.json` as query usage.

## Keywords

graphify, graphify_ask, usage.json, token savings, alwaysApply, keep/kill
