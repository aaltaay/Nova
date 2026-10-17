# ADR 058 -- Volume profile on the 5-minute chart

**Status:** Accepted · **Date:** 2026-10-17
**Decided by:** the operator, 2026-10-16 to 2026-10-17. The plan and its decisions D1-D8 are
`docs/plans/2026-10-16-volume-profile-large-caps.md` (#1014, PR #1015). The operator's words, in order:
- "I want this feature in nova ... It's going to be for large-cap strategies and I only want a way to hide that
  feature and enable it."
- "Maybe it's only needed on the 5mins?" (D4)
- "I can't even see the [anchored] volume profile ... On which chart? Which timeline?"
- On the plan's read card and plan card: "I don't need all of that. I just need the chart."
- "go ahead and build it! fast forward" -- the open decisions taken as the plan recommended them, where the chart-only
  scope still asks them.

## Context

The video the operator chose ("NEVER Read Candlesticks Again - Volume Profile Is 10x Better") reads volume by price:
the point of control, the value area that holds 70% of the volume, the high- and low-volume nodes, the shape. The plan
built a whole feature around it -- a read card, Large Cap columns, two watch-only signals and a research reading. The
operator kept the chart.

A working prototype on the demo desk (2026-10-17) showed two things the plan had not:
- The desk holds one day of 1-minute bars (`CHART_TIMEFRAME_BAR_LIMITS["1Min"]`, IBKR's `1 D`), so the browser
  cannot build yesterday's profile. The backend has to.
- The 5-minute pane opens on its last 96 candles, so yesterday's box is off screen until the operator scrolls out;
  its value area, carried into today as dashed lines, is not.

## Decision

1. **The chart only.** Today's profile and yesterday's regular-session profile on the Trader's 5-minute pane, the
   anchor the operator drags, and the toolbar's Profile switch. No read card, plan card, Large Cap columns, signals or
   research reading; they stay in the plan for a later ask.
2. **One switch, off until turned on (D1).** The Trader toolbar's Profile button, beside Eyes, Setups and Levels. It
   is the browser's setting, shared by every Trader tab and window. Off, the desk asks nothing and draws nothing.
3. **The 5-minute pane only (D4).** The other panes are unchanged.
4. **Every stock, not only large caps (D2, D3 answered by the switch).** The switch is the operator's gate; a
   market-cap filter would hide the profile on a stock whose market cap Nova has not read. The plan's large-cap
   universe matters for the signals, which are not built.
5. **Today's profile measures from 09:30 ET (D7)** -- the anchor. Dragging its handle snaps it to any candle of the day
   from 04:00, and today's profile is read again from there.
6. **Built from IBKR's 1-minute bars, served by the backend** (`GET /api/volume-profile/{symbol}`,
   `architecture/schema/volume-profile.md`). Today's from the chart store, with no IBKR request. Yesterday's from the
   chart store when it holds the session, else one paced IBKR request in `historical_service`'s budget, at background
   priority, never stored; the profile kept in memory per symbol and day.
7. **Drawn so it can be seen.** Today's in a blue box from the anchor to the axis, its histogram in a lane right of
   the last candle and left of the pane's tag column; yesterday's in a grey box where its session closed; a shaded
   value area, a red POC, a white outline tracing each histogram's shape. When the operator's own zoom leaves no room
   right of the last candle, today's histogram lies faintly over the candles: Nova never moves a view the operator
   took.
8. ~~**Not on a Sim replay.**~~ Superseded by the amendment below.

## Amendment 2026-10-17 -- the profile on a Sim replay

**Decided by:** the operator, on a Massive replay of AAPL whose chart said the profile is not drawn on a Sim replay:
"it doesn't work in the sim bro.. why it can't load data from data of massive we have? I still want a single source of
truth, so the data needs to be the same. In the sim, we're still going to have the same data feed, but instead of IBKR,
we're just injecting the data from Massive."

On a replay desk the profile reads what the replay's chart reads -- one feed, the replay's: today's from the replay's
own 1-minute bars up to the playhead (`sim.chart_replay.fetch_replay_bars`), yesterday's on a Massive replay from the
same Massive files' minute bars for the exchange day before, and on any other replay as live (those bars are IBKR's).
The answer names its `feed`, and the desk drops today's profile on every scrub so nothing after the playhead is drawn
(`architecture/schema/volume-profile.md`, "On a Sim replay"). Live bars are still never drawn under a replayed chart.

## Consequences

- One new IBKR request path, at most one request per stock per exchange day, and only while the switch is on and the
  chart store lacks yesterday's session.
- The plan's other pieces (D5, D6, D8: the Settings section, short signals, the re-entry rule) are not decided; they
  wait for an ask.
- Nothing trades on it. A bot on volume-profile signals would need the plan's research reading, an operator decision
  and its own ADR.
