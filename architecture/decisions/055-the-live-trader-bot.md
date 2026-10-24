# ADR 055 -- The Live Trader bot: a TraderTV host's bar, copied on Paper

**Status:** Accepted · **Date:** 2026-10-14
**Amends:** [[044-one-bots-page]] (a new section of cards; the Bot switch counts a host's key as a strategy On) · [[042-one-owner-for-novas-buys]] (a second bot kind beside the setup strategies) · [[037-who-trades-the-stock]] (its four Entry · Exit modes, per host) · [[020-three-venues-one-feed]] (Paper fills a quote with no Level 2 at IBKR's Level 1 bid and ask)
**Builds on:** [[007-centralized-trading-execution]] · [[018-desk-venue-vs-spend-arming]] · [[048-short-selling]]
**Decided by:** the operator, 2026-10-14 (about 22:00 ET): "How do we automate this? Let's say Neil goes ahead and ... purchases something. How do we make Nova do the same thing on paper for now? ... My expectation is to have a bot for that channel and a specific one to be a part of the bot's army when it's active. In our bots menu, bots are going to mirror their trade, and the bot needs to have configuration like allowance as well. We can call it live trader bot." Then "a watcher, like an independent worker that doesn't take any memory. It also needs to communicate with the rest of the system level to keep space for [it] and watch it." Then, mid-build: "Please keep it a single source of truth, not a new route of doing things or executing on trades." Money and risk were asked as multiple choice (below); mockup v1 approved "as drawn".

## Context

The TraderTV LIVE page (`followed-traders.md`) reads the operator's feed program: each host's bar -- side, ticker, average -- as the stream shows it, with no size, stop or target. Nothing in Nova acted on it: copying a trade was "a later, Paper-only bot, never Live; it is not built here". The page and the desk's toasts pull the feed; no backend code worked out "opened / added / closed".

"Live" in the name is the hosts' live show, not the Live venue. A bot never trades Live (AGENTS.md section 5), and this one trades Paper only.

## Decision

1. **One bot per host, on the Bots page.** A "Live Traders · TraderTV" section under Strategies holds one card per host the feed reads that day (any name, NEAL and SHAWN today). Each card has the host's **key** (on/off) and the stock's own **Entry You | Bot · Exit You | Bot** switch with ADR 037's four modes and words: bot enters · bot exits, bot enters · you exit, you approve · bot exits, you enter · you exit (watch only). A host's bot acts only while its key **and** the venue's Bot switch (ADR 044) are on; the Bot switch is the one master. ON counts a host key as a strategy On (`BOT_NO_SETUP_AT_STRATEGY` reads "no strategy or Live Trader key is On").

2. **The mirror's rules** (operator, 2026-10-14):
   - a position appears on the host's bar: one **step** in their direction;
   - their average moves (an add): one more step, up to the **adds** setting (0, 2, 4 or every). Average changes no more than `LT_ADD_MERGE_SEC` (4 s) apart are one add, acted on once they settle; one that comes back to where it started is not an add;
   - the position leaves the bar: sell or cover all of it;
   - also get flat when the host goes **off air** (another host's name tag on the bar for 60 s: the page's own sighting, `followed_traders.sightings`), when the **bar is hidden 10 minutes** (`status.bar_visible` false; also a feed that has not answered or read for 10 minutes), and at the **sell-all time**, 15:55 ET by default (five minutes before the close; 12:55 on an early close): never overnight;
   - a position already on the bar when the bot starts watching, when the host comes back on air, or that the feed first shows a minute or more after its entry, is **already open**; the setting decides take (one step) or skip.

3. **Money and risk** (multiple choice, recommendation marked; the operator's answers are the defaults, each a setting per host in the operator cache):
   - a step is **$500** (shares = $500 ÷ price, rounded down); a stock over $500 buys **1 share** while the allowance has room;
   - the **allowance** is **$2,500** a host: the most dollars its bot has in the market at once, counting working entries at their limits; a step that would go over is skipped ("allowance used: $x of $y");
   - it follows **2 adds**; it **takes** positions already open (one step, only within 1.5% of the price now);
   - it copies **both sides**: a short is ADR 048's bracket, a short limit with a buy stop **5%** over the entry, through the one short check (09:35-15:50, borrow, SSR, halt, margin), never while the account holds the stock long;
   - it copies **large caps only**: market cap of $10 billion or more (`constants_scanner.LARGE_CAP_MIN`, Yahoo's figure through `fundamentals`); a smaller or unknown one is a stated skip. **An ETF always passes** (Yahoo's `quoteType`, which `fundamentals` now reads; an ETF has no market cap) -- the operator, asked whether TQQQ, SPY and QQQ count: "I would like to trade ETFs. I feel like they are lower risk ... Keep it clean." A step's dollars are the same for an ETF; a leveraged one (TQQQ is 3x) moves its $500 like $1,500 of the index;
   - each stock needs only the bot's own **Level 1** line, never a Level 2 line (AGENTS.md section 5 notes the exception): IBKR gives 3 Level 2 lines in all, and the hosts hold more names than that.

4. **Never act on a doubtful read.** Each of these is a skip with its reason, on the card and on the bot's audit stream: the feed reading more than 30 s behind the stream (the page's own rule) or having read nothing for 30 s; a ticker the glued-ticker check (`followed_traders.tickers`) has not settled; the host's average more than 1.5% from the market (a misread); no fresh quote; an unknown market cap (a stock's; an ETF needs none). A wait (the quote line opening, the market cap or the ticker check being read) is not a skip until `LT_WAIT_SEC` (30 s) passes. Closes are never held for these: a close only ever reduces what the bot holds.

5. **One source of truth: no new way to trade.**
   - Every order enters the execution door (ADR 007) with `origin: "live_trader"` and `setup: "live_trader:<HOST>"`, so the Orders table's Sent by, the Activity list and the fills read apart from the operator's own. An entry is source `bot` (a long: a limit at the ask plus 2 cents; a short: the bracket above) and passes every gate a bot order meets -- the padlock the Bot switch unlocks, Freeze all orders, the day lock, buying power, the short check. Unfilled after the venue sleeve's `working_ttl_sec`, it is cancelled.
   - A close is the protective flatten (source `flatten`, `bot.flatten`'s market ticket on a practice venue), so it goes out with the padlock locked and under Freeze all orders, like every flatten. It names Paper as its venue (`target_venue`): Nova's closes may already name the venue that holds the position (ADR 048's day cover and margin call), and `live_trader` joins them on Paper and Sim only -- never Live. A short's buy stops are cancelled first (source `cancel_working`, the same way).
   - The bot holds a Level 1 line on every stock it holds or is entering through the line manager (`ibkr.ticks`, owner `live_trader`), so the scanner plans around it and the line is there for its own quote, Paper's fills and the misread check.
   - Approvals ("you approve · bot exits") raise a toast in every desk window through the bot's notices (`bot/BotNotices.tsx`) and a line on the card -- Approve or Skip, `LT_ASK_SEC` (60 s) -- and an approved step meets every rule again before it is sent.
   - The host's key off, or the operator turning the Bot switch off, while the bot holds positions asks first on the desk and then sells them. A restart, a locked padlock, a venue change or a trip stops new entries only; positions keep following the host's closes.

6. **The watcher** (`backend/bot/live_trader/`): a background task started with the backend, idle while no host key is on and it holds nothing; idle, it asks the feed only for the day's host names (every 15 s), so each host's card and key show before any key is on. About every 2 s it asks the feed for the desk's day (`followed_traders.feed.fetch_day`), applies the page's sightings and closes on leaving and the ticker check, and compares the answer with the last one by trade id (a new id opened, a new average added, open to closed closed) -- the comparison and every rule above are one pure function (`decide.py`) with no clock or I/O of its own. It keeps the last answer's open positions per host in memory (a few KB) and its own holdings in the operator cache, read back after a restart. Each step is a `live_trader` line on the bot's audit stream; its heartbeat ("on air · read 2 s ago") and every skip are on `GET /api/bot/live-traders`, which the Bots page polls.

7. **Paper fills at the quote with no Level 2.** A Paper order on a stock with no Level 2 line filled marketable at the last print, because Paper's bid and ask came only from a depth book. Paper's market now takes IBKR's Level 1 bid and ask when the stock has no book side and its Level 1 line is fresh (`practice.reference.LiveReference`): a buy pays the ask and a sell gets the bid, as on Live. Every Paper order, the operator's own included (operator's choice, 2026-10-14).

## Amendment 2026-10-15: the panel lives on the TraderTV LIVE page

Operator ask, 2026-10-15: "I want this to be moved inside Trader TV Live. At the very top, before we start populating Neil, he is on air. I want to see those." The "Live Traders · TraderTV" panel (the hosts' cards, their keys, Entry/Exit switches, asks and the blocker line) moves off the Bots page to the very top of the TraderTV LIVE page, above the hosts' rows, while that page shows today (a past day or a trade's proof shows no panel: the panel is the bot now). Decision 1's "on the Bots page" is replaced; everything else in it stands -- the venue's Bot switch, on the Bots page, is still the one master, and ON still counts a host key as a strategy On. The component stays owned by `frontend/src/bot/` and reaches the page through the bot barrel, loaded on demand (ADR 005). ADR 044 has the matching amendment.

## Amendment 2026-10-15: bad reads never buy

The operator, 2026-10-14 ~23:15 ET: "if the script reads like something extremely abnormal. It can flag it as a
mistake and wait for the next crop ... I don't want it to try to buy more or try to average more." The feed's
reader was found tonight to make five kinds of misread on the recorded shows: a ticker glued to its price, a
scrolling row whose edge cuts a ticker or leaves the row unread for minutes, an on-screen clock read impossibly,
an average that flickers while an add fills in pieces, and -- at a hand-over -- the previous host's rows under the
next host's name tag for up to minutes. The 1.5% rule, the ticker check and the add merge already met the first,
the cut ticker and the flicker. Added (`bot.md`, "Bad reads"):

- a row whose side, stock and average to the cent belong to another host's row nearby in time, or to the feed's
  previous day, is never opened by either host's bot (`LT_OTHER_HOST`);
- a side whose recent reads carried unreadable text opens and adds nothing (`LT_ROW_UNREAD`);
- an add whose new average is not between the old average and the market is a misread (`LT_ADD_IMPLAUSIBLE`);
- a read without a stream clock opens nothing (`LT_NO_CLOCK`); the feed's parser drops an impossible clock
  instead of refusing the whole read log, and an answer the bot cannot fold is a feed that is not answering.

A held position keeps its exits through any of these: the host's close as the feed confirmed it, off air,
10 minutes without a read, the sell-all time. Whether bad reads while holding should sell at once instead is the
operator's to answer; until then the bot holds (the recommendation put to them).

Two review findings land with it: a short whose shares leave it some other way has the rest covered, and the
buy stops of every position that holds nothing any more stay on a persisted list until Paper shows each one
cancelled -- a refused cancel is tried again, across a restart -- so a stale stop never buys past flat or covers
a later short; and a book that cannot be written stops every new step until a write succeeds, so a restart can
never take a position the bot already bought again.

## Amendment 2026-10-15: the bar's own moves

Two behaviours of the bar seen on recorded shows look like trades and are not. Both change the exit path, so the
operator was asked first (multiple choice, recommendation marked): when a host's whole bar goes blank at once and
the same positions come back about a minute later at their very averages (a display refresh), hold the sells up to
~90 s to see whether they come back, or sell at once as before? The operator chose **hold up to 90 s** (the
recommendation). Built (`bot.md`, "The bar's own moves"; `bot/live_trader/decide_bar.py`):

- **A blank bar.** Every open position of a host (two or more) closing in the feed within one second while their
  bar reads empty on both sides holds those closes up to 90 s. A position back at its very average (side, stock,
  average to the cent) is the same position: re-keyed, no sell, no rebuy. One not back is sold when the bar returns;
  a bar still empty at the limit is sold whole. Off air, the 10-minute rule, the sell-all time, the key and the Bot
  switch still sell at once. Before this the bot sold every position and bought each back a minute later, a round
  trip per position for nothing.
- **After a break.** When a host comes back on air, the previous host's rows can sit under the returning host's
  name tag for minutes until every slot switches in one second. The "another host's row" rule above catches them
  only when the live feed saw those rows under the other host's tag nearby in time. The rows the bar shows just
  after the return are now not taken until all of them have closed (the switch) or 8 minutes pass, and rows that
  fill an empty bar together in one second are already open, not new entries. This only delays or relabels a take,
  never a close; a host's real position on the bar at the return is taken up to 8 minutes late.

Rejected: telling a refresh from a real flatten-all by the screen (the bar's animation over the name tag) -- the
feed reports no such signal, and the 90 s hold bounds the cost of a real one; holding every close that follows a
blank until the next read of the averages without a limit -- a bar that never returns would hold forever.

## Rejected

- A per-host copy of the order path, its own risk checks or its own kill switch: the operator asked for one source of truth, and every gate already exists at the door.
- Requiring a Level 2 line like the setup bots: with 3 lines in all and the operator's Trader tabs holding them, the bot would skip most positions (operator's choice).
- Trading Sim: the show is live and a Sim replay is one past stock; the Sim scratch account unwinds when the playhead is scrubbed back. Paper only, stated on the card.
- Pushing the heartbeat through the audit socket: the Bots page polls over HTTP, and a line every 2 s would bury the Activity list. The heartbeat lives in the view; steps and skips are audit lines, each skip once per trade.
- Selling on every deactivation: a restart or a locked padlock is not the operator turning the bot off, and selling blind on a restart would trade on no read at all.

## Consequences

- The operator turns a host's key on and the Bot switch on, on Paper, and the host's trades are copied within a pass or two of the feed's read, with every skip said on the card.
- What the bot holds is the bot's: its fills carry its origin and setup, and its closes sell its own shares only, never the operator's, and never more than the account holds.
- A feed misread costs at most a step: the 1.5% rule, the ticker check and the large-cap rule stand before every step.
- Nothing here touches Live: the bot opens on Paper only, its closes name Paper, and the door refuses a `live_trader` close on Live.

## Amendment 2026-10-15: LiveTrader Bots, its own key, and off places no order

Operator decisions, 2026-10-15 (ADR 044's amendment of the same date): the Live Traders panel leaves the TraderTV LIVE page for its own tab, **Bots > LiveTrader Bots**, with a **LiveTrader Bots key** at its top; the Bot switch moves to the header beside the padlock. A host's bot buys only while the Bot switch, the LiveTrader Bots key and its own key are all on, and a blocker says which is off (`LT_BOT_OFF`, `LT_FAMILY_OFF`), on the page that holds the family's key -- the family no longer needs a switch on another page.

Decision 5's last bullet is replaced: **off places no order** (operator: "Bots can not place order or sell orders! that's it", then "No orders at all" when asked whether held positions should still exit, with the overnight risk said). The host's key, the LiveTrader Bots key or the Bot switch turning off sells nothing and asks nothing, and while any is off the host's bot sends nothing: no step, no add, no close for the host's exit, off air, the 10-minute hidden rule, the sell-all time or a day rollover. Each close it would have sent is said once and sent when the keys are back on if its reason still stands (past the sell-all time: at once). A short's buy stop still rests at the broker and still fills. Each add made while a key is off is a skip (`LT_KEY_OFF` for the host's key, the blocker's code otherwise), so turning a key back on never buys an add made while it was off. The bot still cancels its own entries at their time to live and the stops of positions that hold nothing; and when the operator covers part of a bot short by hand, it still covers the rest, so a stop sized for the old shares can never buy past flat. Decision 5's "A restart, a locked padlock, a venue change ... stops new entries only" now reads: each turns the Bot switch off, so the bot places no order until it is on again. The audit's `key_off` and `bot_off` change kinds are retired (older lines keep them).

Accepted risk, said to the operator before the choice: with a key off, a position the bot holds is not sold when the host exits or at 15:55, so it can be held overnight until the operator sells it or turns the keys back on.

Rejected: keeping the sell-on-off for this bot alone, and off stopping new buys only while exits run (the operator chose one meaning for off at every level: no orders at all).

## Amendment 2026-10-15 (afternoon): each host's bot in the host's card

Operator, 2026-10-15 (ADR 044's amendment of the same afternoon): the TraderTV hosts' page is Bots > LiveTrader Bots, and each host's bot sits in the middle of that host's card in two lines -- its key, Entry, Exit and rules; its allowance, today and skips, the reasons on hover -- with an ask taking the second line. A copy the bot holds is a BOT chip on the host's open row it copies. The LiveTrader Bots key and the one line naming what stops every host's bot are in the page's head. The rules, the keys and the wire (`GET /api/bot/live-traders`) are unchanged; only where the desk draws them moved (`bot.md`, "The Live Trader bot").

## Amendment 2026-10-22: their size, in $500 lots -- and the bots' fees priced as a commission-free broker

Operator, 2026-10-22, after "how come they made money and I lost money today?": the hosts' card read a gain at
$1,000 a trade while the bots lost on Paper. The two count different trades (their score has no fees, counts
stocks the bot may not copy and leaves out the trades the feed saw no single exit for), and on the trades both count
the bot kept up -- but its copies did not grow and shrink as the hosts' positions do. SHAWN scales in and out in many
small pieces (13 to 31 average changes on one position); the bot copied two adds of a full step and sold half, once,
so its average sat far from his and his profit-taking was its loss (SPCX, 2026-10-21: half sold at a $51.77 loss).
The operator asked to "tighten the rules a little bit to fully mirror their trades", and chose from four rules put
as multiple choice, recommendation marked: today's, a full step at every add, their size on every change, and
**their size in $500 lots** (the pick).

- **Their size** (`bot/live_trader/sizing.py`). The bar shows no shares, but a buy pulls the average toward the price
  it paid and a sale their platform folds into the average pushes it away: from `A` to `A'` with the market at `P`,
  they added or sold `|A - A'| / |A' - P|` of what they held. The bot keeps a target -- the shares it would hold had it
  copied every change exactly -- and each add buys, each partial sale sells, the whole shares between the target and
  what it holds, once they are worth the host's lot (`lot_usd`, $500; 0 sends every change), so tiny changes do not
  each pay an order. One change at most doubles the copy; the allowance cuts an add to its room; an add skipped for
  any reason never grows the target. Decision 2's "one more step, up to the adds setting" now reads "the add's share
  of the copy, up to `adds` orders" (default every add). The first step and an already-open take stay one step.
- **A partial sale sells their share, every time** -- never all of it (the host still holds the rest). The amendment
  of 2026-10-15 ("Sell half, once") is replaced. A short covers whole steps, newest first, never its first, each
  step's buy stop cancelled first and exactly its shares covered: Paper cannot shrink a stop, so every share kept
  keeps its own; shares whose stops were cancelled and whose cover has not filled are covered on the next passes,
  whatever the keys, as a short whose stop no longer matches already is.
- **Fees.** Nearly every order of the bots' is small enough that IBKR Fixed charges its $1.00 minimum; a
  commission-free broker charges none. The operator: IBKR is never replaced -- its data and Level 2 are why Nova is on it -- and
  a commission-free broker for the bots' Live orders is only a plan ("Don't switch. This is just a plan"); but
  Paper prices the LiveTrader bots' orders as that plan would from now on, so a Paper test reads as Live will:
  no commission, the same SEC, TAF and CAT pass-through (`constants_practice.PRACTICE_COMMISSION_FREE_ORIGINS`,
  `architecture/practice-account.md`). The operator's own orders, and every other bot's, stay on IBKR Fixed. IBKR Lite
  is no option (no API trading). Choosing the broker, and AGENTS.md rule 7's change before any order reaches it,
  are later decisions of the operator's.

Rejected: a full step at every add (it piles a whole step onto each of a scaler's small adds); sizing
the first step from the host's (the feed shows no shares); shrinking a short's stop in place (Paper has no quantity
change, and a stop larger than the shares left could buy past flat); pricing the bots at IBKR Tiered (the plan is
commission-free, and Tiered costs the operator's own orders of many cheap shares more).
