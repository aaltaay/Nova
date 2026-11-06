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

## Amendment 2026-10-12 (2) -- a Sim replay reads its own day as of the playhead

The stated absence above is replaced: a Sim replay desk reads the replayed day as of the playhead
(operator decision 2026-10-12), with one law: no lookahead. Every fact comes from a record
that reaches the playhead and nothing after it -- the recorded board row at the playhead (price, volume,
RVOL, the float Nova held then, the exported news verdict), the loaded replay's own price and volume, the
recorded catalyst feed's items published by then, FINRA's newest settlement already published, the borrow
record's last poll at or before it, Massive's splits executed by the day, and the halt log up to it. A fact
no record reaches is unknown, its check names why ("borrow record starts Sep 28"), and the rules are the
same. Only a replay no record of the stock reaches says it is not read (`likely.kind` `not_read`).

Decisions inside it:

- **FINRA's publication lag is a rule, not a calendar.** FINRA publishes about seven business days after a
  settlement, after the close; a settlement counts from the 8th exchange day after it. A day late is safe; a
  day early is lookahead.
- **The float is the one Nova held then.** The recorded board row's float is what the live desk showed that
  minute, so the replay reads what the desk read, with its #532 check. A rebuilt board carries the session's
  enrichment-snapshot float, which may be later than the playhead, so there it is the newest snapshot taken
  at or before the playhead. Massive's free float was not used: it
  keeps only the latest value per ticker, so most past days predate its effective date, and a second float
  definition would make the same day read differently by which source answered (SDEV: Yahoo 22.55M against a
  6.36M free float).
- **Coverage spans join where they overlap.** Each recorded span is unbroken reading, so two that overlap
  leave no gap, and the feed's restarts do not make every past window "not read".

Schema: `architecture/schema/stock-read.md`, "Why it's moving".

## Amendment 2026-10-12 (3) -- the Catalyst column

The operator asked for the News column to become **Catalyst** on every table and to name what is moving each
stock that made the day's boards -- news when there is news, and otherwise the read's own cause (squeeze, split
squeeze, low-float momentum, thin, unexplained) -- with a hover that "explains everything" and nothing made up
(mockup v1 approved 2026-10-12). The read is the same rules read; three things are added:

- **A batch read.** `GET /api/why?symbols=...&board=...` answers each symbol's read in one request (the
  halt log is read once for all), so a 50-row board is one request; one symbol's failure is that symbol's.
- **A board's row at its own price.** With `board`, each symbol's row on that board is read at the price the
  row shows, and the L1 line's last trade is named beside it (`facts.last_trade`, `facts.priced_by`). The cell
  explains the row it sits in: GIXI's frozen Gappers row read $6.08 (+56%) while its last trade an hour later
  was $3.94 (+1.3%), and the Trader card's last-trade read called it "Not a big move" on the day it gapped on a
  robot-delivery release. The Trader card keeps the last trade (the XRPN rule above).
- **The ladder.** `likely.steps` lists the move and then every cause in the rules' order, each with whether it
  fits (`true` / `false` / `null` when a fact it needs is unknown) and why, with the numbers and the threshold
  ("Shorts 10% of float · 0.3 days to cover -- heavy is 20% of the float short, or 3+ days to cover with 10%+
  short"). It is built from the same checks and thresholds as the cause (`move_reason/explain.py`); a test runs
  every combination of the deciding facts and holds the first rung that fits to the cause.

The cell keeps the News column's marks for news and adds one mark per cause; a `possible` cause is hollow and
its word carries a "?". Until the read is in (and on an API without the batch route, or the sample desk) the
cell shows the News column's own mark, never a guess. Rules v5. The same day the news classifier learnt the
law-firm advert that read as NCPL's company news ("... Sued for Securities Law Violations - Contact the DJS
Law Group to Discuss Your Rights", catalyst rules v9).

Rejected: putting the read on every scanner row server-side (the read touches the halt log and the borrow
record per symbol; on the scanner push that is the socket loop's time, #797); sorting the column by cause (the
sort stays the newest headline, the column's old key); reading a frozen row at the last trade (the cell would
contradict the row it sits in).

## Amendment 2026-10-26 (4) -- rules that learn, a model never on the desk; the first: funds

The operator asked why BRZD (+76%) and BZQ (+50%) read "Unexplained" on 2026-10-26. They are inverse Brazil
funds, up because Lula won Brazil's runoff the day before; the read knows only company causes, so a fund falls
through every rung. A free local model (Qwen3.5-9B, llama.cpp on the desk's graphics card) was then tested as a
live explainer on 150 past "no news" movers and 70 live board rows (private study, F:\Nova\private\why-ai-test,
operator ask 2026-10-26). It named the cause whenever the free headlines held it, but 7 of the 44 causes it would
have shown were wrong (16%), it rated every answer 0.95 sure so no confidence cut removes them, and it added
0.3-0.5% slow desk frames at the open. The operator: "I don't want AI to make mistakes, so I prefer deterministic,
but rules can't be static; I need an agent with some level of comprehension."

Decision:

1. **The desk stays deterministic.** No model runs in the read or writes what the desk shows. "Rejected: an
   LLM explanation now" stands for the desk.
2. **An agent keeps the rules growing.** An agent (Claude Code, or a local model) reads the movers the read left
   `unexplained` or `thin_trading`, finds their causes, and proposes rules with the evidence. A rule reaches the
   desk only through a pull request the operator approves, and only after it passes a test written before it:
   - **A held-back test set.** The rule is written from cases the agent saw and must also pass labelled cases
     it never saw (later days, or a set drawn before the rule was written).
   - **A pass bar fixed before the test runs**, written in the pull request or this ADR, never adjusted after.
   - **Mislabels counted on their own.** A rule fails if it puts a plausible but wrong reason on a stock (a
     Brazilian name that moved on its own news read as "Brazil-wide sell-off"), even when its hit count is high.
3. **The first rule: a fund says so, its own name quoted.** A symbol Yahoo calls a fund (`quote_type` `ETF`,
   which Yahoo also gives ETNs) reads "A fund: it moves with what it tracks, not on company news", with the fund's
   name exactly as Yahoo gives it ("ProShares UltraShort MSCI Brazil Capped"). Nothing is read out of the name. It
   sits after company news and before the short squeeze; a fund with company news keeps news. Unknown while
   Yahoo's fundamentals are not read, and on a Sim replay (a replay never reads Yahoo). The first version read the
   side, the multiple and what the fund tracks from the name, against a pass bar fixed before it was written: (a)
   zero wrong directions where the tracked thing parses to a ticker with its own daily bar that day; (b) the
   parsed leverage within 25% of the fund's move over the ticker's on at least 95% of those; (c) a reviewer that
   did not write the rule reads 40 random parsed names and finds at least 95% right. It never passed (the record
   below), and the operator chose the quoted name (2026-10-26): "Fund's own name".
4. **Law-firm adverts and halt notices are never a cause** -- already the catalyst classifier's noise
   (`law_firm`, `halt_notice`); nothing changes.

Not decided here: funds on the small-cap boards at all. `scanner._is_common_stock` drops names with "ETF",
"Fund", "Trust" or "Index", so "MicroSectors -3x Short Brazil ETNs" and "ProShares UltraShort MSCI Brazil
Capped" pass it; whether to filter by security type is the operator's call. A same-country or same-theme group
rule ("Brazil-wide sell-off") waits for its mislabel count: Yahoo gives XP Inc., a Brazilian broker, the
country "Cayman Islands".

**The held-back record (2026-10-26), every run kept** (private study, F:\Nova\private\why-ai-test\fund_rule):

| Run | Window | Fund-days checked | (a) direction | (b) leverage | (c) 40 names | Then |
|---|---|---|---|---|---|---|
| 1 | 2026-06-17..09-21 | 1,523 | 0 wrong | 98.9% | 37/40 -- fail | legal tail; "Leveraged" with no number |
| 2 | 2026-09-22..10-16 | 765 | 0 wrong | 100% | 37/40 -- fail | a ticker that is a word ("ON", "BULL"); sponsor names |
| 3 | 2026-01-02..06-16 | 5,406 | 7 wrong -- fail | 99.8% | not run | "Short ... Option Income" read long (6); KLAC's 10-for-1 split (1, the data) |
| 4 | 2025-07-01..12-31 | 2,459 | 3 wrong -- fail | 98.6% | see the PR | parsed right; a payout moved the fund, not its stock |

Run 4's three (AVL -13% and PLTU -10% on 2025-12-10, SMUP -15% on 2025-12-24, each while its stock rose) are
parsed right: the fund fell for a reason its name cannot know, so "down 13%, so AVGO fell" would have been a wrong
claim. The bar was not changed; the claim was removed -- the cause says only what the fund is and which way it
moves with what it tracks. Each fix was committed before the next window was drawn, and no window was run twice.

After run 4 the reading was frozen once more and a fresh reviewer read 40 names no reviewer had seen: 30 of 40
right (Roundhill WeeklyPay funds run 1.2x with no number in the name; sponsor fragments such as "AG Silver" and
"Galaxy Ethereum"; a brand read as what the fund tracks, "IncomeMax"). Across four reviews 75-93% of names were read
fully right and every fix moved the misses elsewhere, while Yahoo's fund type and the quoted name were never wrong.
The rule that ships quotes the name and reads nothing out of it.

