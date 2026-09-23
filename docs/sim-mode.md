# Sim mode -- weekend practice desk

Sim is a **local practice harness**. It is not IBKR paper and not live.

## Turn it on

1. Start Nova as usual (`Run Nova.bat` or Desktop).
2. In the header, click **Sim** on the Paper / Live / Sim capsule.
3. Confirm. The desk shows a magenta **SIM PRACTICE -- not IBKR** flag and a matching banner.

Load a replay: a **recorded capture** (Day + Ticker pickers) or a **Historical replay** window you downloaded. Quote, Time & Sales, Level 2 and the chart then play that real session. Place / cancel / flatten update a local practice ledger (positions, Orders Today, Day P&L, Net Liq / BP) without a Gateway.

With nothing loaded the Sim desk is empty and says so -- except at the **live edge**. While the Sim clock follows the wall clock on today's date (not paused, not scrubbed, no past day loaded) the session bar reads **Live edge** and a Sim tab shows the live IBKR feed exactly as a Paper tab does, filling the scratch account against it; scrub back and the tab shows the loaded replay (today's Session Record of that ticker loads by itself when one exists), **Follow wall clock** returns to the edge (ADR 020 live-edge amendment). There is no synthetic instrument: Nova never invents a tape (ADR 019).

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

## Your venue survives a restart -- your arming does not (ADR 018)

Two separate facts, with deliberately opposite lifetimes:

- **Venue** (Paper / Live / Sim) is remembered. Nova writes your click to
  `desk-venue.json` in the operator cache, so a backend restart -- including the
  localhost watchdog bouncing the API mid-session -- comes back on the venue you
  chose. Sim now behaves like Paper and Live, which were already sticky.
- **Arming** is never remembered. Every backend start is **disarmed**, in every
  venue. Unlock the header padlock to arm this session: one click on Paper and
  Sim (a bot may arm them through `POST /api/ibkr/arm`), your PIN on Live --
  checked by the backend (set it once with `py -3 tools/set_live_arm_pin.py`).

That pairing is what closes the old hole: a restart used to drop the desk from
Sim back to an armed live Gateway with nothing on screen to say so. Now, if the
venue file is missing or unreadable, Nova falls back to `NOVA_BROKER` and comes
up on IBKR **disarmed** -- charts, scanners and Level 2 work, and no order can
leave until you arm it by hand.

Changing venue also disarms, so switching Sim -> Live never hands you a live
desk that is already armed.

Cancel, flatten and KILL stay available while disarmed. A disarmed desk can
always get flat; it just cannot open.

## Optional bootstrap

`NOVA_BROKER=sim` in `.env` starts the process in Sim **only when there is no
saved venue** -- it is the default for a fresh clone, not the store. Your header
click wins over it. The header toggle is still the live control; do not treat
the env flag as the product activation.

## Hard rules

- While Sim is on, `ibkr.orders` refuses every Gateway place / bracket / cancel (`SIM_NO_IBKR`).
- The tape is a **real recorded or downloaded session**. Nothing is synthesised, and a practice order is refused unless the loaded replay's symbol has printed at the playhead.
- **Practice fills are estimates** and are marked as such -- never confuse one with a recorded print. Rules and known biases: [architecture/practice-fills.md](../architecture/practice-fills.md).
- Fills are always live (no `held_until` Monday).
- In-memory ledger only -- restart clears practice positions. The **venue**
  survives that restart (ADR 018); the practice ledger and the arming do not.
- `auto_live` stays NO-GO. Sim does not unlock live spend.

## Historical replay

The SIM clock defaults to 04:00–20:00 Eastern. Open **Historical replay** in
its header, enter a supported ticker, date (defaults to the latest completed
trading day) and session window, then download candles or trades. **Load
replay** selects that window. Load again after a partial download advances; the
playhead stays put. **Close replay** unloads it, keeping pause and the time of day. Other
ticker tabs use available archived candles for the same date. Data is not
preloaded for the entire market.

The Stock Quote rail looks the same as Paper/Live: the quote head (last,
change vs the prior close, Vol/Gap/High/Low for the replay so far) over
**Level 2 | Time & Sales**. Time & Sales is the live panel with a **REPLAY**
badge. Level 2 keeps its columns and shows the book **your own depth recorder**
archived for the second at the playhead, stamped with when it was recorded; an
IBKR download itself carries no book. Most replayed seconds were never
recorded, and the pane says so ("Level 2 was not recorded for this moment")
rather than showing an empty ladder. Rows are not tinted green/red, because
historical bid/ask is not downloaded.

Candles without trade coverage appear only after their interval closes.
Downloaded prints build partial candles and Time & Sales at one-second
precision. Identical prints remain separate. Prints IBKR marks unreported
(odd-lot/Form T) are listed in Time & Sales as dimmed rows but excluded from
candles, last and volume, so replay matches IBKR's own bars. Right-click the
tape and set a minimum size of 100 to hide odd lots. Historical bid/ask is unavailable, so
practice fills on a historical window price from its prints alone.
Pause/resume download keeps committed pages; failed jobs remain incomplete with
an error. Only one download runs at a time. The default persistent archive on
this Windows machine is `F:\Nova\sim\_capture\historical\replay.sqlite3`;
`NOVA_SIM_HISTORY_DIR` can override its parent directory. Downloaded candles
are also written to the existing Nova bars archive. See
`architecture/historical-replay.md`.
