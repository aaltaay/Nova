# Practice account: fills, fees and buying power on Paper and Sim

How Nova's fake-money account (ADR 020) fills an order, what it charges, and
how much it lets you buy. Every number lives in `backend/constants_practice.py`
with the source named beside it; this page is the survey those numbers came
from and the reasons for each choice. Fill *rules* (which print or quote a
fill reads) stay in `architecture/practice-fills.md`; this page covers the
account around them.

## 1. What the simulators people use actually do

| Simulator | Fill | Fees | Buying power | Source |
|---|---|---|---|---|
| IBKR paper account | Market orders become marketable limits filled from the **top of book only** (no deep book); an order with no opposite quote is held until one appears; stops are always simulated; a partially executed exchange-directed market order has its remainder rejected. | Real IBKR commission schedule applied. | Real margin model (IBKR's own; intraday margin since 2026-06-04). Seeds USD 1M. | [Paper trading](https://www.ibkrguides.com/clientportal/aboutpapertradingaccounts.htm), [Simulated market orders](https://www.interactivebrokers.com/en/trading/simulated-market-orders.php), [Paper vs live](https://www.interactivebrokers.com/campus/trading-lessons/paper-trading-vs-live-trading-whats-the-difference/) |
| IBKR Pro, US stocks, **Fixed** | -- | USD 0.005/share, min USD 1.00/order, max 1.0 % of trade value; regulatory fees passed through on sells. | -- | [Commissions: stocks](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php) |
| SEC / FINRA (sells only) | -- | SEC §31: USD 20.60 per USD 1M of sale value (FY2026, from 2026-04-04). FINRA TAF: USD 0.000195/share sold, max USD 9.79/trade (2026). | -- | [SEC fee advisory](https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2), [FINRA TAF](https://www.finra.org/rules-guidance/guidance/trading-activity-fee) |
| Alpaca paper | Fills only when marketable against the current NBBO (buy limit ≥ ask, sell limit ≤ bid); order size is **not** checked against quoted size; random partial fill 10 % of the time; no slippage, queue or impact. | None. | Seeds USD 100k; Reg T 2x / PDT 4x like its live accounts. | [Alpaca paper trading](https://docs.alpaca.markets/us/docs/paper-trading) |
| TradingView paper | Broker emulator fills at the exact requested price; market / stop orders can add a **slippage in ticks**; historical bars fill on bar close. | Off by default; optional fixed per order or % of value. | Cash only, operator-set balance. | [Strategy properties](https://www.tradingview.com/support/solutions/43000628599-strategy-properties/), [Pine strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/) |
| backtrader broker | Next-bar open by default; `cheat-on-open` / `cheat-on-close` opt-ins; `set_slippage_perc` / `set_slippage_fixed`. | `setcommission(commission=, margin=, mult=)`: % of value when `margin` is falsy, fixed per contract otherwise; `CommInfoBase` for per-share schemes. | Cash checked at submit **and** at execution; margin via `margin=` per contract. | [Brokers and orders](https://backtrader.readthedocs.io/en/latest/user-guide/brokers/brokers.html), [Commission schemes](https://www.backtrader.com/docu/commission-schemes/commission-schemes/), [Slippage](https://www.backtrader.com/docu/slippage/slippage/) |
| backtesting.py | Market orders fill at next bar open, or this bar's close with `trade_on_close=True`; commission is folded into the fill price (long slightly higher, short slightly lower). | `commission=` as a fraction of value (or `(fixed, relative)` tuple). | `margin=` is one ratio for initial and maintenance alike (`0.5` = 2x). | [Backtest API](https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html) |
| QuantConnect Lean, IB model | `ImmediateFillModel` on the current quote/last; `NullSlippageModel`. | `InteractiveBrokersFeeModel`: USD 0.005/share, min USD 1, **max 0.5 %** (older than IBKR's current 1.0 %). | `SecurityMarginModel`: 2x leverage on US equities in a margin account; immediate settlement on margin. | [IB brokerage model](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/brokerages/supported-models/interactive-brokers), [Fee models](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/supported-models) |
| Regulation T / FINRA 4210 | -- | -- | USD 2,000 minimum equity to borrow; initial margin 50 % of purchase (2x overnight); maintenance 25 %. **Since 2026-06-04 intraday margin** replaces the pattern-day-trader rule: no USD 25,000 minimum, no day-trade count, no 4x day-trading buying power -- equity must cover the maintenance margin of what is held at any moment, so 25 % maintenance gives 4x. IBKR adopted it on 2026-06-04; other brokers may phase it in until 2027-10-20. | [FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10), [FINRA margin accounts](https://www.finra.org/rules-guidance/key-topics/margin-accounts), [Investor.gov](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/margin) |

What they agree on: a marketable order fills **now** at the quote or last print
without a queue; size is never checked against displayed liquidity; fees are a
per-share rate with a per-order floor and a %-of-value ceiling plus sell-side
regulatory pass-throughs; buying power is Reg T 2x with a 4x intraday tier
(the Alpaca and QuantConnect rows predate FINRA's 2026-06-04 intraday margin
rule, which dropped the USD 25k pattern-day-trader line behind that tier). Slippage, when it exists at all,
is an operator knob, not a model.

## 2. Nova's parameters and why

| Constant | Value | Why |
|---|---|---|
| `PRACTICE_STARTING_CASH` | 100 000 | The Sim ledger's existing seed (`SIM_STARTING_CASH`); Alpaca's default; readable against a retail live account. IBKR's 1M would flatter every bot. Operator-resettable. |
| `PRACTICE_COMMISSION_PER_SHARE` / `_MIN` / `_MAX_PCT` | 0.005 / 1.00 / 1 % | IBKR Pro **Fixed** as published today. Live Nova trades on IBKR, so Paper charges what Live would; Fixed rather than Tiered because it has no volume tiers or exchange rebates to fake. QuantConnect's 0.5 % cap is stale and is not used. |
| `PRACTICE_SEC_FEE_RATE` | 20.60 per 1M | FY2026 §31 rate, on **sell** value only, as IBKR passes it through. |
| `PRACTICE_FINRA_TAF_PER_SHARE` / `_MAX` | 0.000195 / 9.79 | 2026 TAF on shares **sold**, per-trade cap. Both regulatory fees are refreshed by editing the constant when the SEC/FINRA notice changes; no auto-lookup. |
| `PRACTICE_MARGIN_INTRADAY_MULT` | 4.0 | FINRA 4210 intraday margin (2026-06-04): equity covers 25 % maintenance on what is held, so 4x. Nova's bots are day traders, so this is the number they hit. Applied as `equity * 4` minus gross position value while `net_liquidation >= PRACTICE_MARGIN_MIN_EQUITY`. The retired USD 25,000 pattern-day-trader line (`PRACTICE_PDT_MIN_EQUITY`, 2x below it) is gone with the rule. |
| `PRACTICE_MARGIN_MIN_EQUITY` | 2 000 | FINRA 4210(b)(2): no credit below USD 2,000 of equity; IBKR keeps it for margin and short sales under the new rule. |
| `PRACTICE_CASH_MULT` | 1.0 | Under the minimum the account is a cash account: `equity * 1` minus gross position value is the cash on hand. |
| `PRACTICE_LIVE_FRESH_SEC` | 15 s | An L1 last older than this cannot price a Paper fill; the broker then uses a recent tape print or refuses `PRACTICE_NO_LIVE_PRINT`. IBKR and Alpaca *hold* an order with no opposite quote; Nova refuses and says why, because a held practice order looks like a working order. |
| `PRACTICE_DAY_ROLLOVER_HOUR_ET` | 04:00 ET | Day P&L / commissions_today / fills_today roll at the pre-market open Nova already uses as session start, the same boundary IBKR's daily figures use. |
| `PRACTICE_ACCOUNT_ID_PAPER` / `_SIM` | `NOVA-PAPER` / `NOVA-SIM` | The header always names an account id; these replace `DU…` / `U…` on the practice venues. |
| `PRACTICE_BUYING_POWER_CODE` | `PRACTICE_BUYING_POWER` | Buying power is **enforced** on both venues (backtrader checks at submit and at fill; Nova checks at admission and again when a resting order fills, refusing the fill if power ran out). A practice desk that lets a bot buy without limit teaches it nothing. |

Fee math, applied per fill: `commission = clamp(qty * 0.005, 1.00,
0.01 * qty * price)`; on a sell add `sell_value * SEC rate` and `min(qty *
TAF, 9.79)`. Commissions and fees reduce cash at the fill, appear on the row,
and sum into `commissions_today`. Realized P&L is net of them. Buying power
`= max(0, net_liquidation * mult - gross_position_value)`; an order is admitted
while `qty * reference_price <= buying_power` for opening trades; closing
trades are always admitted.

## 3. Time-in-force and no shorts (operator decisions, 2026-09-21)

**Time-in-force.** The practice venues honour the two TIFs the execution
command carries (#91): `DAY`, the default, and `GTC`. A `DAY` order expires
at the close of its session -- the desk's session window ends at
`SIM_SESSION_CLOSE_HOUR` (20:00 ET) on Paper; on Sim it is the replayed
session's close, whatever window the operator loaded -- as an `expired` ledger
event whose row reads `Expired` with `reason_code: PRACTICE_TIF_EXPIRED`. A
print after the close never fills a `DAY` order, even when the matcher sees it
in the same pass. The event is stamped at the close itself, so a Sim scrub
back before the close restores the order and a Paper pass after a restart
records when it really expired. A `DAY` order placed at or after the close
works the next session (IBKR's own rule). `GTC` carries no expiry and persists
across days and restarts. The Paper matcher (`practice/matcher.py`) and the
Sim feed tick (`sim/feed.py`) both expire due orders after matching prints;
the row and its `placed` event carry `tif` and `expires_ts`. Rules:
`practice/order_rules.py`.

**No shorts.** A SELL on a practice venue is only ever risk-reducing, exactly
as Invariant #7 keeps it on Live: a SELL for more than the held quantity, or
any order carrying `short_entry`, is an opening short and is refused
`PRACTICE_NO_SHORTS` ("Nova does not support short entries yet") -- at
admission in the execution door (`execution/practice_checks.py`) and again in
`PracticeBroker.place`, on every source. Nothing is inferred from side plus a
flat position beyond that arithmetic. The rule holds at the fill too
(`order_rules.fill_refusal`, QA R42): a resting SELL that would fill past what
is held when its print arrives -- another close filled first -- is cancelled
`PRACTICE_NO_SHORTS`, never filled, so two closes of the same shares can never
leave the account short.

## 4. Known gaps Nova keeps

Named so nobody reads a practice P&L as a live one:

- **No queue.** A resting limit fills on the first print through its price
  (`print_cross`), regardless of how many shares were ahead of it. Every
  surveyed simulator does the same.
- **No slippage model.** Market orders fill at the quote or last print as-is.
  TradingView and backtrader offer a knob; Nova does not invent a value for it
  -- the tape is the reference, and a made-up tick of slippage is inferred data
  (no-inferred-market-data rule). A `fill_estimated` flag says it anyway.
- **No partial fills and no size check.** Alpaca's random 10 % partial is a
  coin flip, not liquidity; Nova fills whole. Order size is not checked against
  displayed depth, so a 50k-share bot fill on a thin book is unrealistic and
  looks it.
- **No borrow, no short-locate cost, no margin interest, no overnight call.**
  The 4x intraday multiplier applies at any hour -- Reg T's 2x on positions
  held past the close is not charged -- and there is no end-of-day
  liquidation. The rule's 90-day freeze for unmet intraday deficits is not
  modelled either: buying power is enforced up front, so no deficit arises.
- **No exchange or clearing pass-throughs beyond SEC §31 and FINRA TAF.** IBKR
  Fixed folds the rest into the per-share rate; the two regulatory fees are
  the ones IBKR itemises on a Fixed statement.
- **Rates go stale by hand.** SEC and FINRA rates change yearly; the constant
  carries the effective date in its comment and is edited, never fetched.

## 5. The ledger as history

`GET /api/practice/history` (`practice/history.py`, schema in AGENTS.md §3)
replays the same events the account is derived from and never reads a live
mark: the equity series holds one point after every fill and rollover, each
held position marked at its own last fill price, so a quiet stretch is a flat
line and the last point can differ from the live-marked account figure. The
by-source split is read from the `source` / `bot_id` stamps on the fills.
Archived Paper ledgers (`practice-paper-<stamp>.json`, written by a reset)
are read read-only for their practice-day rows, flagged `archived`; a damaged
one is skipped with a warning the payload names. Ranges (`1D` .. `ALL`) start
at a practice-day boundary and count calendar days, so a weekend simply holds
no session; nothing is interpolated to fill it.
