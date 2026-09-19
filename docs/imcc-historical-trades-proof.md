# IMCC historical trades availability proof

Observed on 2026-09-19. Related: D-052 / [issue #292](https://github.com/aaltaay/Nova/issues/292).

## Result

The local IB Gateway returned historical IMCC trades for 2026-09-18 in both
premarket and regular hours. This is an actual account-access test, not merely
confirmation that an API exists. September 18 was selected from Nova's IMCC
references; availability for other dates has not been established.

| Request start (America/New_York) | Returned prints | First timestamp | Last timestamp |
| --- | ---: | --- | --- |
| 2026-09-18 04:00:00 | 1,003 | 04:00:00 | 05:40:44 |
| 2026-09-18 09:30:00 | 1,021 | 09:30:00 | 09:30:20 |

The first premarket print was 200 shares at USD 1.85 on DRCTEDGE. The first
regular-session print was 50 shares at USD 3.25 on ARCA. These are historical
observations, not current quotes. Premarket included 195 distinct seconds;
the regular-session response included 21 distinct seconds.

## Request and validation

- Python `ib_async.IB`, local Gateway port 4001, separate client ID 29419.
- Connection used `readonly=True` and `fetchFields=StartupFetch(0)`.
- Qualified `Stock('IMCC', 'SMART', 'USD')`: conId 912275669, primary exchange NASDAQ.
- Each `reqHistoricalTicksAsync` request used the start above with explicit
  `US/Eastern`, empty end time, `numberOfTicks=1000`, `whatToShow='TRADES'`,
  `useRth=False`, and `ignoreSize=False`.
- Returned fields inspected: time, price, size, exchange, special conditions.
- Only informational farm messages 2104, 2106, and 2158 arrived. No request or
  entitlement error occurred. The probe disconnected in a `finally` block.
- No orders, order-gate changes, replay changes, or full-day download occurred.
  Raw responses were inspected in memory; no durable tick archive was created.

## Limits and next step

IBKR may exceed the requested count to finish a whole second. Historical ticks
have second-level timestamps; this evidence does not establish millisecond
timing, full-day completeness, quote history, or depth history. IBKR also
documents that some non-reportable real-time AllLast trades are absent from
the historical database.

The next implementation should download a bounded day in paced pages, preserve
all prints within each completed second and their returned order, verify day
boundaries and gaps, and persist the source and contract identity. It must then
feed only reached events into partial candles and volume. Rewind determinism
and volume reconciliation need verification before claiming faithful replay.
Historical availability is proven; acquisition and playback remain in D-052.

## Sources

- [Historical Time and Sales](https://interactivebrokers.github.io/tws-api/historical_time_and_sales.html)
- [Tick-by-Tick data and historical exclusions](https://interactivebrokers.github.io/tws-api/tick_data.html)
- [Current HistoricalTicksRequest schema](https://www.interactivebrokers.com/docs/tws-api/protobuf/historical-ticks-request)
