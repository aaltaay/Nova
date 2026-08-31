# 2026-08-31 -- After-hours VWAP resets at 16:00

- **Status:** completed
- **Agents:** parent
- **Domain:** market-feed / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-31 -- After-hours VWAP resets at 16:00; `PROBLEM_LOG.md` 2026-08-31 -- After-hours VWAP sat frozen; `DEFERRED_LOG.md` D-007 closed

## Task

Match industry VWAP after the cash close. Operator compared Nova vs Webull on LABT: Nova's orange line did not move in after hours.

## Goal

Keep the daytime orange VWAP (04:00-16:00). At 16:00 start a new after-hours VWAP through 20:00 so the grey zone walks. Do not mix AH volume into the daytime number.

## Why it mattered

VWAP is a decision level. Freezing $2.46 under a $3.50 AH runner looks broken. Dumping 8.5M AH shares into 362k RTH shares would have deleted the daytime level. D-007 was parked until a live Webull look plus platform docs.

## What we changed

- `sessionVwapPoints` resets the accumulator at 16:00 and accumulates until 20:00 (`CHART_VWAP_AFTERHOURS_END_SEC`)
- Premarket stays in the daytime segment (no 09:30 reset)
- `tools/vwap_probe.py` prints daytime vs AH vs RTH-what-if
- Closed D-007

## How it works now

One orange LineSeries. 04:00-16:00 is the daytime VWAP. At 16:00 the math starts over. 16:00-20:00 is the after-hours VWAP; that value carries until midnight. Next ET day still whitespaces overnight so leftover cannot diagonal into 04:00. Axis tag after 16:00 is the AH number.

## Why this approach

Investopedia / TradingView help / CFA treat VWAP as one session, open to close. DAS draws extra pre/post lines rather than blending. Webull (community recreation plus the LABT screenshot) resets at 16:00 and keeps the RTH orange on the left. Keep-adding (TradingView ETH-on) was rejected: on LABT it would print $3.37 and erase $2.46. A second color series is the same math as a same-color reset; one series matches the screenshot. Do not reset at 09:30 -- that would undo the 2026-08-28 premarket blend the operator asked for.

## Verification

- `npx vitest run src/chart/vwapSession.test.ts src/chartIndicators.test.ts`
- `py -3 -m pytest tools/test_vwap_probe.py -q`
- Live `py -3 tools/vwap_probe.py LABT`
- `npm run build`

## Follow-ups

None for D-007. Overnight leftover rule unchanged.

## Keywords

vwap, after-hours, 16:00, LABT, D-007, session reset, Webull, DAS
