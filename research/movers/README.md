# The day movers index (ADR 050)

One row per stock per session that moved, so an agent can answer "small caps whose high was +300%" across every
day of the operator's Massive files and show the match in the Sim. The backend reads it
(`backend/day_movers/`, `/api/agent/movers`); these scripts write it, through `backend/day_movers/store.py`, into
`<NOVA_MARKET_DATA_DIR>/movers/day_movers.sqlite3` (default `E:\Nova\massive\movers\`). Schema and wire: AGENTS.md
section 3, "Agents find stock-days and show them in the Sim".

## Build and extend

```text
py -3 research/movers/build_movers.py                    # every session not built yet, newest first
py -3 research/movers/build_movers.py --avoid-session    # stop before 03:45 ET on a weekday (leave the desk alone)
py -3 research/movers/build_movers.py --date 2026-09-25  # one session again
py -3 research/movers/build_movers.py --status           # what is built
py -3 research/movers/export_sec_shares.py               # SEC shares outstanding (float evidence), after a new companyfacts.zip
```

A session takes about 3 s of DuckDB; on the operator's E: drive, shared with the Massive downloader, 4-20 s. The
first build of all 2,515 sessions (Oct 2016 on) runs for hours in the background at below-normal priority and is
resumable; later runs build only the new days. A session built before its minute file arrived is built again.

## What a row means

- **Prior close**: the official close (Massive's day bar, the 16:00 closing cross -- not the 15:59 minute) of the
  session before in the files, times the factor of any split Massive lists, or `research/leaderboard/confirm_splits.py`
  proved, executing in between. None when the stock did not trade that session; never an older close.
- **The day bar** (`open`, `high`, `low`, `close`, `volume`): regular hours only. Checked: on 2026-09-09, 2,477 of
  11,866 tickers had a premarket or after-hours high above it; so the day's high and low (`day_high`, `day_low`)
  come from the minute bars 04:00-20:00 ET, with the first minute that printed each, beside `pm_*` (04:00-09:30)
  and `ah_*` (16:00-20:00).
- **Marks**: `up10_ts` .. `up300_ts` the first minute whose high reached +10% .. +300% over the prior close
  (`down10_ts` .. `down50_ts` for the low). A show parks five minutes before `up20_ts` (else `up10_ts`).
- **Kind**: the Massive reference's type for the ticker (today's dump; delisted tickers included, a reused ticker
  reads today's owner's type). The search's `common` default is `CS` / `ADRC` and type-less 1-4 letter tickers.
- **Splits**: an overnight open 1.8x or more (0.7x or less) the prior close with no split listed is a suspect,
  and a likely split when it traded no more shares than the session before. Massive's list starts in June 2021,
  so older reverse splits can only be caught this way. Measured on the day bars: of 6,104 stock-days with a
  regular-hours high +300% over the prior close (Oct 2016 - Oct 2026), 5,517 were warrants, rights, units, names
  under $0.50 or split-like days; 587 were common stocks, 522 of them on days whose trades are on disk.
- **Kept**: the high +10% or the low -10%, the close or the gap 5% either way, or a split suspect; a new listing
  (no prior close) when its high is 20% over its low. `sessions.tickers` counts the whole market that day.

## SEC shares outstanding

`export_sec_shares.py` reads every `dei:EntityCommonStockSharesOutstanding` (else us-gaap
`CommonStockSharesOutstanding`) from SEC's `companyfacts.zip`, as of its date and when it was filed; several
share classes keep the largest count. A float limit passes on it only when the count was filed by the session,
is at most 120 days old and is at or under the limit (a float cannot exceed the shares outstanding), put on the
session's share basis through the splits listed in between. Shares issued after the count are not in it.
