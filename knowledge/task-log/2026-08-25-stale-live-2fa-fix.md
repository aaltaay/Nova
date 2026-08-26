# 2026-08-25 — Stale live 2FA login fix

- **Status:** completed (code + tests); overnight live verification outstanding
- **Agents:** parent
- **Domain:** ibkr-ops / market-feed adjacent (Gateway login lifecycle)
- **Related:** `CHANGELOG.md` 2026-08-25 "Live Gateway keeps the week-long login token..." · `PROBLEM_LOG.md` 2026-08-25 "Wake up, approve IBKR Mobile 2FA, login still doesn't complete" · `architecture/decisions/013-ibkr-account-vs-port.md`

## Task

User reported: on waking up, IB Gateway shows the IBKR Mobile Second Factor prompt, they approve it, and nothing happens -- they have to go back into the Nova UI and click login/launch again. Asked for a deep-dive investigation using any existing audit trails, a root cause, and a fix plan, with replication if needed.

## Goal

Find the real root cause (not a workaround), fix it so approving a 2FA prompt reliably completes the login, and give the operator an honest, working one-click recovery when a prompt genuinely can no longer be honored.

## Why it mattered

This blocked live trading readiness every single morning and, on at least one occasion (2026-08-20), turned an unattended 2FA timeout into an 8-attempt login retry loop that hit IBKR's own account-level rate limit twice ("Too many failed login attempts"). That is a real risk to a funded live account, not just an inconvenience.

## What we changed

- `backend/constants_ibkr.py`: replaced `IBKR_IBC_LIVE_AUTO_LOGOFF_TIME` with `IBKR_IBC_LIVE_AUTO_RESTART_TIME` (mirrors paper); added `IBKR_SECOND_FACTOR_STALE_AFTER_SEC = 180.0` (must track IBC's own `SecondFactorAuthenticationTimeout`).
- `backend/ibkr/launch_gateway.py`: `_align_ibc_trading_mode("live")` now sets `AutoRestartTime` and blanks `AutoLogoffTime`, same as paper. New `force_fresh_login` parameter on `launch_or_focus_gateway` -- only this flag clears the `jts.ini` `Restart=OK` token (via `jts_ini.clear_restart_token()`) and stops the stuck windowed process (`_stop_gateway_process()`). A routine launch/attach no longer clears that token.
- `backend/ibkr/second_factor.py` (new): parses the newest local IBC log for the last `Second Factor Authentication initiated` with no later `Login has completed`; reports `pending` / `age_sec` / `stale`. Gated on the Gateway process actually running (a prompt that outlived the whole process is not something an operator can act on).
- `backend/routes/trading.py`: `GET /api/ibkr/status` now includes `second_factor_pending` / `second_factor_age_sec` / `second_factor_stale`; `LaunchGatewayRequest` gained `force_fresh_login`.
- Local (`%USERPROFILE%\.nova\ibc\config.ini`, not in git): `ReloginAfterSecondFactorAuthenticationTimeout=no` -- stop IBC's own unattended retry loop.
- Frontend: `IbkrStatus` type, `tradingPrerequisites.ts` (`stale_second_factor` action, priority above the port-mismatch follow action), `TradingPrerequisitesGate.tsx` ("Start fresh login" CTA), `GatewayDisconnectedBanner.tsx` (routes the existing Open Gateway buttons through `force_fresh_login` when stale), `launchIbGateway.ts` (new `forceFreshLogin` param), `WorkspaceContext.tsx` / `DashboardPage.tsx` (thread the new status fields through).
- `scripts/Invoke-NovaMorningCheck.ps1`: warn on `ReloginAfterSecondFactorAuthenticationTimeout=yes` or a `SecondFactorAuthenticationTimeout` that has drifted from 180 (the value `second_factor.py` assumes).

## How it works now

IBC times its own Login-In-click-to-dialog-close window and silently discards anything longer than `SecondFactorAuthenticationTimeout` (180s), then restarts the login -- regardless of whether the operator just approved it. Nova's own nightly `AutoLogoffTime` on the live door made a cold 2FA structurally certain every morning, and the 03:40 scheduled task meant nobody was there within the 180s window. Removing the nightly logoff (both doors now use `AutoRestartTime`) removes the daily cold login entirely; the only 2FA that should remain is IBKR's own mandatory weekly re-auth, which an operator is far more likely to be present for. When a prompt does go stale, the fix is not to retry silently (that's the rate-limit incident) or to just refocus the dead window (it holds no LISTEN port to even prove it's still alive) -- it's to detect the staleness honestly from the IBC log and let the operator explicitly restart the login in one click, which both clears the Restart token and kills the stuck process so IBC opens a genuinely new prompt.

## Why this approach

Considered and rejected:
- **Raise `SecondFactorAuthenticationTimeout` past 180s.** This is IBKR's own server-side limit, not a client-tunable grace period -- IBC's comment explicitly warns not to change it unless IB itself changed the limit. Raising it would not fix anything (IBKR still expires the challenge server-side) and could mask a real timeout as a Nova bug later.
- **Set `ExitAfterSecondFactorAuthenticationTimeout=yes` / rely on IBC's own retry.** This is the exact mechanism that caused the Aug 20 rate-limit incident. An automated retry loop with no human in the loop is worse than an inert stale prompt that a person can act on later.
- **Keep the nightly logoff and just detect staleness.** This treats the symptom (a doomed prompt) without removing its guaranteed daily trigger. The operator would still be woken by a login that can only be salvaged by luck (being awake within 180s of 03:40). Removing the unnecessary nightly logoff is the actual fix; stale-prompt detection is the safety net for the cases that remain (weekly forced re-auth, unattended crashes).
- **Auto-click "fresh login" the moment staleness is detected.** Rejected -- an unattended auto-restart-loop is exactly the failure mode this incident already produced once. A human must explicitly ask for a fresh login.

## Verification

- `pytest backend/tests/test_launch_gateway.py backend/tests/test_second_factor.py backend/tests/test_gateway_mode_switch.py backend/tests/test_routes_trading.py` -- all green, including two new/rewritten cases proving a routine `force_restart` does NOT clear the Restart token, and `force_fresh_login` does (and kills the stuck process).
- Full backend suite: `py -3 -m pytest -q` -- 1352 passed.
- Frontend: `npx vitest run` -- 733 passed; `npx tsc --noEmit` clean; `npm run build` clean.
- Live evidence (not a synthetic repro -- happened during this session): the exact discard pattern reproduced twice on this machine's real IBC logs, once this morning (03:40 → 08:52, `Duration since login: 18754 seconds` / `Re-login after second factor authentication timeout`) and once again at 20:30-20:38 while this fix was being written.

## Follow-ups

- **Not yet verified:** tomorrow's 03:40 `NovaDailyStart` run should show 4001 LISTEN with no new `Login attempt` line in the IBC log (proving the week token held). Check `backend/logs/daily-start.log` and the newest `IBC-*.txt` after that run.
- **Not yet verified:** one week of observation to confirm the only 2FA prompt that appears is IBKR's own mandatory weekly re-auth, and that it can be approved successfully within 180s when a human is present.
- Do not reopen "give live AutoLogoffTime" without a new, specific reason -- that was the root cause here, not a safety feature.

## Keywords

IBKR Mobile, Second Factor Authentication, 2FA, IBC, SecondFactorAuthenticationTimeout, ReloginAfterSecondFactorAuthenticationTimeout, AutoRestartTime, AutoLogoffTime, Restart=OK, jts.ini, stale prompt, force_fresh_login, launch_or_focus_gateway, rate limit, NovaDailyStart
