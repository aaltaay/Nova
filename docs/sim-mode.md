# Sim mode -- weekend practice desk

Sim is a **local practice harness**. It is not IBKR paper and not live.

## Turn it on

1. Start Nova as usual (`Run Nova.bat` or Desktop).
2. In the header, click **Sim** on the Paper / Live / Sim capsule.
3. Confirm. The desk shows a magenta **SIM PRACTICE -- not IBKR** flag and a matching banner.

Look up **SIM1**. Quote, Time & Sales, Level 2, and the shared chart path use a looping synthetic tape. Place / cancel / flatten update a sim ledger (positions, Orders Today, Day P&L, Net Liq / BP). Works 24/7 with no Gateway.

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
