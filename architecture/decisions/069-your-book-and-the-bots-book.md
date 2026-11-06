# ADR 069 -- Your book and the bots' book, inside one account

**Status:** Accepted · **Date:** 2026-11-03 · **Built:** 2026-11-03 (#1267); the Reports tab's journal (decision 6) 2026-11-04, design mockup reports-v1 · **Amended:** 2026-11-04 (decision 9, every positions list shows both books; mockup positions-both-books v1)
**Amends:** [[063-a-loss-line-for-you-and-one-for-the-bots]] (decision 2's whose-trade rule becomes the books' rule, owned outside the loss limit; on Paper a fill no longer closes the other book's shares, except Nova's own closes and history from before this ADR) · [[020-three-venues-one-feed]] (Paper keeps each position per owner) · [[055-the-live-trader-bot]] (the Live Trader stays out of a stock you hold, not only off its other side) · [[042-one-owner-for-novas-buys]] (one budget above every bot's own sizing)
**Builds on:** [[007-centralized-trading-execution]] (the door holds the rules) · [[048-short-selling]] (one account is never long and short a stock) · [[068-claude-trades-paper-from-its-own-seat]] (decision 6, Claude's shares are only Claude's, now holds for every bot)
**Decided by:** the operator, 2026-11-03. The ask: "We're going to have bots with their own account, and we're going to have humans with their own account. Keep everything tied together, like the UI, the way it is." -- "I need a way to filter between bots only and human trades, and maybe do both." -- "When bots trade, I don't want it to go against my own trades. If I make money, bots lose money. I really want a separation." -- "Leave the sim alone." They chose among options put to them in three rounds before any code was written, and approved mockup v1 (`F:\Nova\design\bot-human-books\v1`, drawn from the Paper ledger's own figures). Two picks differ from the recommendation: the bots' budget is $25,000 (not $50,000), and the Account page opens on All (not You).

## Context

- **Live** is the operator's alone. A bot never trades Live (Invariant #7), and every Live fill counts as the operator's (ADR 063).
- **Paper** is one practice account, `NOVA-PAPER`. The operator trades it, and so does every bot: the strategy bot, Auto-entry, the localhost bot API, the Live Trader bot (ADR 055) and Claude's seat (ADR 068). The ledger (`practice/ledger.py`) keeps one position per stock. So:
  - The Account page's equity curve, Day P&L and calendar add everyone together. A day the operator made money and the bots lost reads as one smaller number.
  - Its by-source split (`practice/history._by_source`) groups fills by `(source, bot_id)`. The Live Trader's and Claude's closes go out as source `flatten`, so their P&L lands in an unowned `flatten` group, not under the bots. Each fill is also priced against the stock's one blended average cost, so where both traded a stock the split is wrong. Say you buy 100 at $10, a bot buys 100 at $12, and you sell your 100 at $11: you made $100 and the bot is down $100, but the split shows you at $0.
  - The operator's plain Sell or Flatten on a stock a bot holds sells the bot's shares. The operator's short entry is refused while a bot holds the stock long (ADR 048). The bots' positions use buying power the operator may want.
  - Each bot guards on its own. Claude's seat stays out of any stock Paper holds (ADR 068 decision 6). The strategy bot and the Live Trader refuse only the other side of a held position (`bot.first_pullback.admit.against_held`, `bot.live_trader.rules`).
- The daily loss limit already splits each Paper fill into the operator's and the bots' from the order's own stamps (`order_source`, `order_origin`, `bot_id`), but for today only (ADR 063, `loss_limit/count.py`). Applying that rule one day at a time to the whole Paper ledger (2026-11-03, read-only) matched 27 of its 29 days' calendar totals to the cent, and yours plus the bots' equalled the day's total every day. The other two days held a position overnight, which a today-only count skips by design; a replay of the whole event list covers them. The history can be split from stamps it already stores.

## Decision

1. **One account, two books.** Paper stays one account: one cash, one buying power, one net liquidation, one `practice-paper.json`. Inside it Nova keeps two books, **yours** and **the bots'**. Every share, fill and dollar of P&L belongs to exactly one of them, and the two add up to the account to the cent. The desk says "Your book" and "Bots' book"; the code and the wire say `owner` (`you` | `bots`), since "book" already names Level 2's.
   - **Whose an order is** follows ADR 063's rule, unchanged. An order is the bots' when its source is `bot`, it carries a `bot_id`, it is a bot's own close (origin `bot`, `bot_api`, `live_trader`, `claude`), or it is the Bots line's Auto sell (`loss_limit_bots`). Otherwise it is yours: the ticket, an approved plan, Nova's exit on your shares, your Flatten, the You line's Auto sell. Auto-entry's buys are the bots' (ADR 063). Nova's own closes belong to neither: KILL, all stop, the day cover, a margin call and the Account line's Auto sell close each holder's shares in proportion to what it holds (ADR 063).
   - **Which bot.** Inside the bots' book each share keeps the bot that holds it, by the order's origin: `bot` (the strategy bot), `auto_entry`, `bot_api`, `live_trader` or `claude`. A bots' order with no origin it can name reads as `bot`.
   - **Each its own cost.** Each holder has its own shares and average cost in each stock. A book's P&L is priced at its own cost, never a blended one.
   - **One owner for the rule.** The rule moves out of `loss_limit` into a new package, `backend/owners/`. The practice ledger, the Account history, the loss limit's count and the Reports journal all read it there.
2. **Bots stay out of yours.** No bot opens a position in a stock your book holds, or where you have any order working. That covers the strategy bot, Auto-entry, the bot API, the Live Trader and Claude alike. The skip is said wherever the bot reports (the audit stream, the toast, the Bots page): "Live Trader skipped PARA: you hold it."
   - A bot already in a stock when you trade it the same way keeps its trade. Its exits go on, and so do its adds the same way, within the bots' budget (the operator, 2026-11-03).
   - Two bots may hold the same stock the same way. Claude keeps its stricter rule and opens nothing where anyone holds shares or has an order (ADR 068 decision 6).
3. **Never the other way.** You may trade a stock the bots hold the same way (both long, or both short), and your shares stay in your book. An order that would leave one book long and the other short in the same stock is refused, for you and for every bot. One account, like one IBKR account, is never long and short a stock at once (ADR 048): "Buy SPCX refused: the Live Trader is short 51. One account can't be long and short the same stock."
4. **Your Sell and Flatten are yours.** These close only your book's shares: your plain Sell, your exit pair, and your Flatten (the ticket's, the quick bar's, `exit_pos`, `cancel_and_exit`). The door's `NO_POSITION`, `OVERSELL` and `OVERCOVER` checks and the Flatten size count your book, never the account. A Sell with nothing in your book is refused and says whose the shares are. A bot's close counts only its own shares.
   - **Auto-entry hands you its exit.** Auto-entry's shares stay in the bots' book (ADR 063), and your Sell and Flatten may close them too, after your own (the operator, 2026-11-03: Auto-entry buys for you and you sell by hand). No other bot's shares are yours to sell.
   - The bots' shares close by their own exits, Stop Claude, the Bots line's Auto sell, and a **Close** on a bots' row in the positions table (the operator, 2026-11-03). Close sells the bots' shares in that stock the way a bot's last-resort close does (`bot.flatten.place_close`), stamped as the bots' close (origin `close_bots`), so it counts in the bots' book. It asks once more before it sends ("Sell all 12?", or "Buy back all 12?" on a short), and first cancels the bots' working orders in that stock (decision 9).
   - KILL, all stop, the day cover and the Account line still close every share, yours and the bots'.
5. **The bots' budget.** All bots together may hold at most **$25,000** in open positions on Paper. That is shares at the mark plus working entries at their limit, the sum `bot.risk.open_plus_working_usd` already counts. An entry that would pass it is skipped and says why: "Live Trader skipped SOFI: the bots' $25,000 would be passed ($23,400 held + $2,500)."
   - It is one Paper setting, in whole dollars, default 25,000.
   - Each bot's own sizing stays beneath it: the sleeve (ADR 042), the Live Trader's per-host sizes (ADR 055) and Claude's limits (ADR 068).
   - Your buying power is the account's; the budget limits how much of it the bots can take.
6. **One switch on the Account page: All / You / Bots.** It filters the Overview: Account details, P&L by day, the equity curve, the calendar, Today by stock, and the positions, orders and fills tables.
   - **All** is the default and shows the split beside each total: a calendar day reads its total, then yours and the bots'.
   - **Bots** opens a pick of one bot by name, using the Bots page's names (Claude counts with the bots).
   - The positions, orders and fills tables gain a **Whose** column: You, or the bot's name. Account details shows both books' Day P&L and how much of the bots' budget is in use.
   - The Reports tab's journal stamps each trade's owner the same way and filters alike. Paper's round trips join it,
     one per holder at its own cost, built from the ledger off the order path; the tab follows the page's venue
     and its pick (`architecture/schema/journal.md`, "Your trades and the bots' on the Reports tab").
   - On Live the switch reads You and is disabled, with its reason: "Live: every trade is yours -- a bot never trades Live."
   - Design: mockup v1, approved 2026-11-03.
7. **The past is split too.** The history is re-derived from the ledger's events, so every past Paper day splits into yours and the bots' from the stamps each order already carries. An order with no stamp reads as yours. A fill from before this ADR that closed the other book's shares (you selling a bot's shares, or a bot's close over yours) is counted by ADR 063's rule: the shares it closed, and their P&L, belong to the book that held them. Archived Paper ledgers split the same way.
8. **Live and Sim.** On Live every fill stays yours, and nothing changes on Live or at IBKR. Sim is unchanged: no switch, no new refusal and no new figure ("Leave the sim alone"). Every rule above is Paper's.
9. **Every positions list shows both books** (amendment, the operator, 2026-11-04). With the Live Trader short SMCI and ORCL and nothing of theirs held, the header read Working 2 and Positions 0: "The positions right now are registering zero on the UI. There are two working, but why do I have zero positions right now? ... I think the positions should keep matching, no?" Day's P&L and Working already counted the bots; Positions counted only yours.
   - The header's Positions count and menu, the Trader's Positions tab (the same table on the Bots page, Stock view and Account › Trading), the dock's footer, the chart's position line, the Bots page's bottom line, the header search and the close-of-day reminder show the bots' shares beside yours, each row with its Whose chip. The Account page already did (decision 6). "No open positions" shows only when nobody holds anything.
   - Showing is all it does. Sell, Flatten, Cover, every hotkey and the ticket still size from your shares alone (decision 4). Every refusal of yours that found no shares, on a stock the bots hold that way, adds whose they are: Cover, Sell %, the exit and Flatten hotkeys, the ticket's Sell. "You hold no ORCL short: a cover buys a short back, and Nova never buys past flat. The 19 short is the bots' -- Close on their row buys it back."
   - Auto-entry's shares stay on your row: they are yours to sell (decision 4), so they are never listed twice, and the chip says Auto-entry when the row holds nothing else. Close on a bots' row counts them, as `close-bots` sells the whole bots' book.
   - A bots' row carries the bots' Close (decision 4). The chart draws the bots' line dashed, in the bots' colour, with the bot's name, size, average and open P&L; it opens no menu, so the chart's Flatten stays yours.
   - Close asks "Buy back all 19?" on a short (it said "Sell all 19?"), and cancels the bots' working orders in that stock before it sends, so their buy stops leave Working with the shares.
   - The close-of-day reminder names the bots' shares still held at 15:56, after the Live Trader's 15:55 sale and the day cover: one card per stock, on Paper, beside yours and never added to it, dismissed on its own.
   - Live and Sim are unchanged: every row there is the account's.
   - Design: mockup positions-both-books v1 (`F:\Nova\design\positions-both-books\v1`), drawn from the Paper account's own figures, approved 2026-11-04 ("Build it all").

## Data

There is no new ledger event and no new `practice-paper.json` version. The owner and the bot are read on replay from each order's `placed` stamps, so today's ledger and its archives read with the split; a `rollover` written since ADR 069 also stamps each holder's P&L at the boundary (`holders`). The confirmed shapes are in `architecture/schema/recording-and-replay.md` ("Your book and the bots' book"), with `execution.md`, `bot.md` and `loss-limit.md`:

- **`GET /api/practice/account?venue=paper`:**
  - Each `positions[]` row keeps the account's figures and adds `by_owner[]`, one `{owner, bot, qty, avg_cost, unrealized_pnl}` per holder.
  - The account adds `books: {you, bots}`, each `{day_pnl, realized_today, unrealized_pnl, fills_today, commissions_today}`. `books.bots` also adds `budget_usd`, `budget_used_usd` and `by_bot`.
  - Sim answers without these fields.
- **`GET /api/practice/history`** moves to `schema_version` 2:
  - Each `fills[]` row adds `owner` and `bot`.
  - Each `daily[]` row adds `you` and `bots`, each `{realized, commissions, fees, fills}`.
  - Each `equity[]` point adds each book's running P&L and its realized part (`you_pnl`, `bots_pnl`, `by_bot`, `you_realized`, `bots_realized`, `by_bot_realized`).
  - `by_owner[]` replaces `by_source[]`: `{owner, bot, realized, fills, commissions, fees}`, each priced at its holder's own cost.
- **Practice order rows** (working, closed, and Orders (Today)) add `owner` and `bot`.
- **`GET /api/ibkr/positions` on Paper** is your own shares (yours and Auto-entry's), with the account's in `account_qty`; every Sell, Flatten, cover and exit on the desk sizes from it, and a bot sizes its close from its own (`ibkr.account.long_qty(symbol, holder)`).
- **Refusals at the door on Paper**, each with its sentence (`owners.rules`, asked again by the practice broker at placement and at the fill):
  - `OWNERS_BOT_STAYS_OUT`: a bot's entry in your stock;
  - `OWNERS_OTHER_SIDE`: an order against another holder's side;
  - `OWNERS_BOTS_BUDGET`: a bot's entry past the budget;
  - `OWNERS_NOT_YOURS`: a close past its sender's own shares while someone else holds the stock the same way.
- **The bots' budget** is one Paper setting, in whole dollars, default 25,000: `owners-budget.json`, `GET` / `PUT /api/owners/budget`.
- **Close on a bots' row**: `POST /api/owners/close-bots` `{symbol}`.

## Scenarios

| Scenario | What happens |
|---|---|
| You hold PARA; a host the Live Trader copies calls PARA | The Live Trader skips it: "you hold it." |
| You have a buy resting on PARA; the strategy bot triggers there | Skipped: you have an order working. |
| The Live Trader holds SPCX long; you buy SPCX | Filled. Your shares are your book's; the account holds both. |
| ... then you Sell or Flatten SPCX | Sells your shares only; the bot's keep their own exits. |
| The Live Trader holds SPCX long, you hold none, and you press Sell | Refused: you hold no SPCX; the shares are the Live Trader's. |
| Auto-entry bought SPCX for you, and you press Sell | Sells Auto-entry's shares: it hands you its exit. |
| You press Close on the bots' SPCX row | The bots' SPCX shares sell; yours stay. |
| The Live Trader is short SPCX; you buy SPCX | Refused: one account can't be long and short the same stock. |
| The Live Trader is long SPCX; you short it | Refused for the same reason. |
| You join a stock a bot is in, then the bot's host adds | The bot adds the same way, within the bots' budget. |
| Two bots want TSLA long | Both may, inside the bots' book and the budget. |
| One bot holds TSLA long; another wants it short | Refused: never both sides. |
| Claude's seat and anyone else in one stock | Claude opens nothing there (ADR 068). |
| The bots hold close to $25,000 and a bot wants more | Skipped: the bots' budget would be passed; the skip says by how much. |
| A bot's stop or target fills | It closes that bot's shares only. |
| KILL, all stop, or the 15:55 day cover | Every share closes, each holder's into its own book. |
| The Bots line trips with Auto sell | Only the bots' shares opened today sell (ADR 063). |
| A past Paper day | Split from its stamps; a sale across books counts for the book that held the shares. |
| Desk on Live | Every fill is yours; the switch reads You, disabled with its reason. |
| Desk on Sim | Unchanged. |

## Consequences

- Every total on the Account page can be read as yours, the bots' or both. All still shows the account.
- The You and Bots loss lines (ADR 063) and the books are one rule with one owner, so they always agree.
- The Live Trader's copy record skips a host's call the operator already holds. On a busy day the budget skips entries too: the bots' busiest moment on Paper so far was close to $25,000. Each skip says why.
- The ticket no longer sells a bot's shares. Close on a bots' row, Stop Claude, the Bots line and KILL do.
- Live parity: decision 3 keeps the books true on one real account. Invariant #7 forbids bots on Live today, and this ADR does not change that. If bots were ever allowed there, the books would work at IBKR unchanged, each order carrying its owner in `orderRef`. Holding both sides at once would need a second IBKR account linked to the operator's login.
- Nothing is migrated: the stamps are already in the ledger.
- `auto_live` stays NO-GO; no venue or arming rule changes.
