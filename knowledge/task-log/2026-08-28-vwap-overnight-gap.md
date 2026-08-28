# 2026-08-28 -- Chart VWAP overnight gap and soak trail

- **Status:** completed
- **Agents:** parent
- **Domain:** widgets / chart UI (continuity-only; no specialist hop)
- **Related:** `CHANGELOG.md` 2026-08-28 -- Chart VWAP no longer draws a leftover-to-open diagonal; `PROBLEM_LOG.md` 2026-08-28 -- VWAP leftover-to-open diagonal

## Task

Soak why AEMD 1Min VWAP looked wrong (straight orange line through premarket) and leave a trail so the next "does this VWAP look right?" question is a command, not a guess.

## Goal

Prove what the line is doing on a live overnight window, stop LineSeries from drawing leftover-to-open as a diagonal, and add a probe that reprints RTH vs extended on any ticker.

## Why it mattered

VWAP is a decision level. A diagonal from yesterday's $2.25 leftover to today's $2.91 open is not a VWAP -- it is the chart library connecting two points 571 minutes apart. The operator could not tell whether premarket "failed to paint" or the math was wrong.

## What we changed

- `frontend/src/chart/vwapSession.ts` -- pane paints only the newest ET day; skipped bars are whitespace
- `frontend/src/chart/vwapSession.test.ts` -- AEMD-shaped overnight window (fail-then-pass)
- `frontend/src/chartIndicators.ts` -- axis title walks back past whitespace; empty title is `VWAP (09:30 ET)`
- `tools/vwap_probe.py` + `tools/test_vwap_probe.py` -- live soak trail

## How it works now

Accumulation is still 09:30-16:00 ET from 1Min bars (unchanged product). After the close, that day's value still carries on a same-day after-hours pane. On a morning pane that includes last night, yesterday leftover is not drawn. Premarket has no RTH points, so the orange line is absent until 09:30 and the tag says when it starts. `py -3 tools/vwap_probe.py AEMD` prints the leftover/open pair, the 04:00 what-if, and the latest-day paint.

## Why this approach

The screenshot had two stacked issues: (1) a real paint bug (LineSeries interpolation across a hole), and (2) a product rule the operator had forgotten (RTH-only, chosen 2026-08-25 over 04:00). Fixing (1) without a trail would leave the next premarket morning looking "empty" and starting this chat over. Changing the anchor to 04:00 was rejected this session -- that is a product flip, not required to stop the fake diagonal, and AEMD's extended vs RTH at 09:52 was only $3.111 vs $3.083. Whitespace matches how RSI/MACD already keep a slot per bar. Latest-day-only hides leftover that is not today's VWAP; painting both sessions with a gap would still leave a $2.25 line under overnight candles.

Rejected re-implementing VWAP on the backend. The bug is entirely in how the browser samples points into LineSeries. Rejected trusting the axis tag alone -- $3.01 was a plausible RTH number while the line itself was the lie.

## Verification

- `npx vitest run src/chart/vwapSession.test.ts -t "does not paint yesterday leftover"` -- failed first (21:50 still $2.18 leftover), then passed after the paint change
- `npx vitest run src/chart src/chartIndicators.test.ts` -- 18 files / 138 passed
- `py -3 -m pytest tools/test_vwap_probe.py -q` -- 4 passed
- Live `py -3 tools/vwap_probe.py AEMD`: leftover $2.2547 at 23:59 -> open $2.9133 at 09:30, gap 571 min, `would_interpolate=YES`; new paint from 09:30, last ~$3.10
- Browser (AEMD Trader 1Min, EMAs off): orange dashed line starts at 09:30 ET, absent through overnight and premarket, axis `VWAP $3.10` while last ~$3.19
- `npm run build` (`tsc -b && vite build`) exit 0

## Follow-ups

If the operator wants the orange line to hug premarket (04:00-09:30), that is a constant change (`CHART_VWAP_SESSION_START_SEC`) plus a re-run of the probe -- do not silently flip it. IBKR tick 233 (RTVolume) is still the live scalar cross-check parked in the 2026-08-25 task-log.

## Keywords

vwap, overnight, premarket, LineSeries, whitespace, AEMD, vwap_probe, 09:30, leftover, interpolation
