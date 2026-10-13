# ADR 028 -- Why it's moving: a rule-based read of what drove a mover

**Status:** Accepted · **Date:** 2026-09-23
**Builds on:** [[024-catalyst-classifier]] · [[023-scanner-leaderboard]] (halt log) · [[009-short-entry]] (IBKR shortability)
**Decided by:** the operator, 2026-09-23 ("I want to know why from the user interface ... especially if
it's squeezing and without news"; "run that through data and analytics where we don't need to consume
tokens"; intelligence deferred)

## Context

The 2026-09-23 news audit found that most small-cap movers have no news at all (24 of 28 checked; 40% of
the research's top-10 movers with honest clocks). The operator still wants to know why they moved. Done by
hand that day, the answer came from a handful of facts Nova already holds or can read for free: the
catalyst verdict, the halt log, float and volume, short interest, a recent reverse split -- and one it did
not read: what it costs to borrow the stock. On 2026-09-23 at 17:13 ET IBKR had 2,000 MSS shares to lend
at 105% a year and none of WHLR, VSA, ARTL or BENF, while TLSA borrowed at 1.3%.

## Decision

1. **A deterministic read, no model.** `backend/move_reason/rules.py` (pure) turns the facts into checks
   (`yes` / `no` / `unknown`, each with its value, source and age) and one **likely cause** from a fixed
   order: news halt, company news, short squeeze, routine company item, supply squeeze after a reverse
   split, low-float momentum, thin trading, nothing found. The cause is labelled as a rules read, and
   says `possible` instead of `likely` when a deciding input is unknown. An unknown fact is shown as
   unknown, never filled in (the desk's rule against inferred market data).
2. **The borrow market is recorded** (`move_reason/borrow_feed.py`): IBKR's public short-stock file
   (`usa.txt`, every US symbol's shares available, fee and rebate, refreshed about every 15 minutes) is
   polled every `MOVE_BORROW_POLL_SEC` into `borrow.sqlite3` under the operator cache -- one row per symbol
   only when its availability or fee changed -- so a restart keeps the day and the read can say "the fee
   went from 20% to 105% since the open". A symbol the file does not list has nothing to lend at IBKR.
3. **Where it shows:** a "Why it's moving" section at the top of the Trader tab's News panel
   (`GET /api/why/{symbol}`), its likely cause visible while collapsed.

## Consequences

- Short interest is FINRA's, reported twice a month about two weeks late, and Yahoo's float can lag a
  reverse split; the read says so beside the numbers. The borrow file is the live signal.
- The read is descriptive. It places nothing and feeds no bot gate.
- Not in v1: sympathy moves (peers on the same theme), options activity, promotions, and a model that
  writes the explanation. Each can join as a check without changing the payload's shape.

Rejected: an LLM explanation now (costs tokens per look, and the operator deferred it); inferring a
squeeze from price action alone (no positioning data behind it); polling the borrow file per symbol (it
is one 1.8 MB file for all 20,000 symbols).

## Amendment 2026-10-12 -- shares short must matter; a Sim replay is not read

Of 48 small caps up 100%+ between 2026-09-29 and 2026-10-08 the read called five a short squeeze (SDEV
twice, TGE, FLUX, PFAI), each on days to cover alone: Yahoo's ratio divides the shares short by the volume
from before the run, so a stock that traded about 1,000 shares a day read 9.1 days on 9,077 shares short
(PFAI, 0.25% of its float). Shorts are now heavy at a fifth of the float, or at three days to cover with a
tenth of the float short; without the share of the float the check is unknown (rules v3). The numbers are
proposed rules of thumb for the operator to tune. Days to cover over today's volume was rejected as the
gate: on a 100%+ day today's volume dwarfs any short position (MSS's hand-checked squeeze had its shorts at
0.09% of the day's volume), so it would never fire.

On a Sim replay desk the read had shown today's facts on a past day's desk. It now names the replayed day
and reads nothing (`likely.kind` `not_read`), the stated absence, until a replayed day can be read from
recorded sources. Schema: `architecture/schema/stock-read.md`, "Why it's moving".
