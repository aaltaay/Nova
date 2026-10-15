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
   - it copies **large caps only**: market cap of $10 billion or more (`constants_scanner.LARGE_CAP_MIN`, Yahoo's figure through `fundamentals`); a smaller or unknown one is a stated skip;
   - each stock needs only the bot's own **Level 1** line, never a Level 2 line (AGENTS.md section 5 notes the exception): IBKR gives 3 Level 2 lines in all, and the hosts hold more names than that.

4. **Never act on a doubtful read.** Each of these is a skip with its reason, on the card and on the bot's audit stream: the feed reading more than 30 s behind the stream (the page's own rule) or having read nothing for 30 s; a ticker the glued-ticker check (`followed_traders.tickers`) has not settled; the host's average more than 1.5% from the market (a misread); no fresh quote; an unknown market cap. A wait (the quote line opening, the market cap or the ticker check being read) is not a skip until `LT_WAIT_SEC` (30 s) passes. Closes are never held for these: a close only ever reduces what the bot holds.

5. **One source of truth: no new way to trade.**
   - Every order enters the execution door (ADR 007) with `origin: "live_trader"` and `setup: "live_trader:<HOST>"`, so the Orders table's Sent by, the Activity list and the fills read apart from the operator's own. An entry is source `bot` (a long: a limit at the ask plus 2 cents; a short: the bracket above) and passes every gate a bot order meets -- the padlock the Bot switch unlocks, Freeze all orders, the day lock, buying power, the short check. Unfilled after the venue sleeve's `working_ttl_sec`, it is cancelled.
   - A close is the protective flatten (source `flatten`, `bot.flatten`'s market ticket on a practice venue), so it goes out with the padlock locked and under Freeze all orders, like every flatten. It names Paper as its venue (`target_venue`): Nova's closes may already name the venue that holds the position (ADR 048's day cover and margin call), and `live_trader` joins them on Paper and Sim only -- never Live. A short's buy stops are cancelled first (source `cancel_working`, the same way).
   - The bot holds a Level 1 line on every stock it holds or is entering through the line manager (`ibkr.ticks`, owner `live_trader`), so the scanner plans around it and the line is there for its own quote, Paper's fills and the misread check.
   - Approvals ("you approve · bot exits") raise a toast in every desk window through the bot's notices (`bot/BotNotices.tsx`) and a line on the card -- Approve or Skip, `LT_ASK_SEC` (60 s) -- and an approved step meets every rule again before it is sent.
   - The host's key off, or the operator turning the Bot switch off, while the bot holds positions asks first on the desk and then sells them. A restart, a locked padlock, a venue change or a trip stops new entries only; positions keep following the host's closes.

6. **The watcher** (`backend/bot/live_trader/`): a background task started with the backend, idle while no host key is on and it holds nothing. About every 2 s it asks the feed for the desk's day (`followed_traders.feed.fetch_day`), applies the page's sightings and closes on leaving and the ticker check, and compares the answer with the last one by trade id (a new id opened, a new average added, open to closed closed) -- the comparison and every rule above are one pure function (`decide.py`) with no clock or I/O of its own. It keeps the last answer's open positions per host in memory (a few KB) and its own holdings in the operator cache, read back after a restart. Each step is a `live_trader` line on the bot's audit stream; its heartbeat ("on air · read 2 s ago") and every skip are on `GET /api/bot/live-traders`, which the Bots page polls.

7. **Paper fills at the quote with no Level 2.** A Paper order on a stock with no Level 2 line filled marketable at the last print, because Paper's bid and ask came only from a depth book. Paper's market now takes IBKR's Level 1 bid and ask when the stock has no book side and its Level 1 line is fresh (`practice.reference.LiveReference`): a buy pays the ask and a sell gets the bid, as on Live. Every Paper order, the operator's own included (operator's choice, 2026-10-14).

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
