# 2026-07-29 — HOD strategy config schema v9 repair

- **Status:** completed
- **Agents:** parent
- **Domain:** hod-momo
- **Related:** `CHANGELOG.md` §2026-07-29 -- HOD Momo schema v9 · `PROBLEM_LOG.md` §2026-07-29 -- HOD strategies 2–9 mass-disabled

## Task

Investigate why HOD Settings showed price filters as zeros for several strategies (user highlighted 3, 6, 9, 13) and ensure those strategies work correctly.

## Goal

Clarify intentional zeros vs stale/broken config; repair live persisted config so float strategies and Approaching HOD evaluate again.

## Why it mattered

Only Squeeze (#10/#11) and Running Up (#12) were enabled in production config. Float Rel Vol strategies and Approaching HOD were silent, which looks like "stale work" in the Settings UI and misses Warrior-parity alerts.

## What we changed

- Schema v9 migration in `hod_momo_persist.py`: re-enable non-Former; add #13; restore price bands 4/6/8/9 when zeroed
- `HOD_MOMO_CONFIG_SCHEMA_VERSION = 9`
- `get_configs()` always returns strategies 1..13
- Settings UI: Load Defaults when a strategy is missing from the API payload
- Test `test_schema_v9_reenables_mass_disabled_and_adds_approach`
- Restarted local API so migration wrote disk schema 9

## How it works now

- **0 = gate disabled** on price/float/RVOL/surge fields. Squeeze #10/#11 correctly have price 0; their real gates are surge + new HOD.
- **#3** Low Float Med Rel Vol: price 0; gates are `max_float=10M`, `min_rvol=2`, `max_rvol=4.9`.
- **#6** under $20: look at **Max Price 19.99** (Min stays 0).
- **#9** $20+: look at **Min Price 20** (Max stays 0).
- **#13** Approaching HOD: custom latch path; no price/surge defaults; now present and enabled.

## Why this approach

Chose a one-shot schema migration (same pattern as v5/v7) over asking the user to click Reset All -- preserves Former Momo list and any intentional surge tweaks while fixing the known mass-disable + missing-#13 shape. Rejected treating Squeeze price zeros as a bug (would invent fake price filters Warrior does not use). Rejected only documenting the issue without migrating -- live disk was already wrong.

## Verification

- `pytest tests/test_hod_momo_persist.py::test_schema_v9_reenables_mass_disabled_and_adds_approach` PASS
- Live `GET /api/hod-momo/config`: keys 1–13; enabled 2–13; #6 max_price=19.99; #9 min_price=20; disk `schema_version: 9`

## Follow-ups

- Refresh/reload the UI Settings drawer to see repaired values.
- If the user intentionally wanted only Squeeze on, they can disable float strategies again in Settings (v9 will not re-run).

## Keywords

HOD Momo, schema v9, strategy config, Approaching HOD, mass-disable, price filter, surge
