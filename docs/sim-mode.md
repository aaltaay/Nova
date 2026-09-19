# Sim mode -- weekend practice desk

Sim is a **local practice harness**. It is not IBKR paper and not live.

## Turn it on

1. Start Nova as usual (`Run Nova.bat` or Desktop).
2. In the header, click **Sim** on the Paper / Live / Sim capsule.
3. Confirm. The desk shows a magenta **SIM PRACTICE -- not IBKR** flag and a matching banner.

Look up **SIM1**. Quote, Time & Sales, Level 2, and the shared chart path use a looping synthetic tape. Place / cancel / flatten update a sim ledger (positions, Orders Today, Day P&L, Net Liq / BP). Works 24/7 with no Gateway.

Real tickers (SPY, IMCC, ...) chart their archived IBKR bars up to the Sim
clock. On a weekend or NYSE holiday the Sim session is the last open exchange
day at the same time of day (Saturday 04:41 ET replays Friday 04:41 ET); the
Sim header shows that date. A pane still reads "No bars available at this
replay time" when the archive has no bars for that ticker/timeframe before the
playhead -- for example 10-second bars, which IBKR only backfills for the last
four hours before a chart was opened. Download the day under **Historical
replay** to fill it.

## Pause and play

The Sim session bar has one **Pause / Play** icon button. Pause freezes the
Sim timestamp and stops new simulated tape updates; Play resumes from that
point without jumping forward by the time spent paused. You can move the
slider while paused to inspect another moment. The same button then resumes
playback. **Follow wall clock** explicitly resumes the wall-clock view.

This control applies only to Sim, including capture replay. It does not pause
IBKR paper or live data. Clock controls preserve the active Trader tab.

Clock contract: `architecture/sim-clock.md`.

## Turn it off

Click **Paper** or **Live**. Nova disables Sim, then uses the existing Gateway door (same as today).

## Optional bootstrap

`NOVA_BROKER=sim` in `.env` starts the process already in Sim. The header toggle is still the live control. Do not treat the env flag as the product activation.

## Hard rules

- While Sim is on, `ibkr.orders` refuses every Gateway place / bracket / cancel (`SIM_NO_IBKR`).
- v1 tape is **SIM1 only**. No fake SPY / AAPL ticks.
- Fills are always live (no `held_until` Monday).
- In-memory ledger only -- restart clears practice positions.
- `auto_live` stays NO-GO. Sim does not unlock live spend.

## Historical replay

The SIM clock defaults to 04:00–20:00 Eastern. Open **Historical replay** in
its header, enter a supported ticker, date (defaults to the latest completed
trading day) and session window, then download candles or trades. **Load
replay** selects that window. Load again after a partial download advances; the
playhead stays put. **Return to SIM1** keeps pause and the time of day. Other
ticker tabs use available archived candles for the same date. Data is not
preloaded for the entire market.

The Stock Quote rail looks the same as Paper/Live: the quote head (last,
change vs the prior close, Vol/Gap/High/Low for the replay so far) over
**Level 2 | Time & Sales**. Time & Sales is the live panel with a **REPLAY**
badge; Level 2 keeps its columns but stays empty because historical depth is
not recorded. Rows are not tinted green/red, because historical bid/ask is not
downloaded.

Candles without trade coverage appear only after their interval closes.
Downloaded prints build partial candles and Time & Sales at one-second
precision. Identical prints remain separate. Prints IBKR marks unreported
(odd-lot/Form T) are listed in Time & Sales as dimmed rows but excluded from
candles, last and volume, so replay matches IBKR's own bars. Right-click the
tape and set a minimum size of 100 to hide odd lots. Historical bid/ask and Level 2 are
unavailable, and SIM1 practice fills wait until historical replay is closed.
Pause/resume download keeps committed pages; failed jobs remain incomplete with
an error. Only one download runs at a time. The default persistent archive on
this Windows machine is `F:\Nova\sim\_capture\historical\replay.sqlite3`;
`NOVA_SIM_HISTORY_DIR` can override its parent directory. Downloaded candles
are also written to the existing Nova bars archive. See
`architecture/historical-replay.md`.
