# ADR 042 -- One owner for Nova's buys: a level per setup under a master ceiling, one Activate, one sleeve, and no silent blocks

**Status:** Accepted · **Date:** 2026-09-30
**Amends:** [[027-bot-playbook-readout-gate]] (one setup plays; the read-out gates Live) · [[030-first-pullback-bot-on-paper]] (the bot's trade, its watched stop, Live waits on the read-out) · [[031-a-scanner-for-every-setup]] (the chosen setup; only it reaches Strategy) · [[032-loss-breakers-per-venue]] (the day lock is one for the desk; locks lift at midnight) · [[037-who-trades-the-stock]] (Auto-entry's own rules and risk; the bot list outside the switch; trades in memory) · [[029-setup-templates-eyes-journal]] (the bot's entry rules inside every template)
**Decided by:** the operator, 2026-09-30:
- On the Bots page: "why is it a radio button? We are already choosing if it's off, eyes only, or strategy independently in each strategy, so why do we have this radio button that says 'bot trade this'?"
- "do you see other stupid mistakes like this one? run deep dive plz first". A read-only audit of the bot, Who trades, the desk's locks and the setups found about 30.
- "Please go ahead and fix these problems, all of them, everything you found, including the radio button and all of the suggestions you made. As far as safety, of course, safety is very important, and I don't want just silent blockers. If you're about to make a decision regarding blocking a bot from running, of course, make everything visible. We don't want anything invisible to the user."

The answers taken with that: one Nova automatic buy a day in total per venue; the top Off / Eyes / Strategy dial stays as a master ceiling; when two setups trigger on one stock the first wins; one sleeve sizes every Nova buy (risk per trade ÷ risk per share, capped by the sleeve); NOT A TRADE blocks every Nova buy; Auto-entry follows the bot's rules and only hands the exit over; the localhost bot API refuses Live until the operator decides it separately. The rest are the agent's calls under the operator's standing grant for routine calls, each with the operator's veto.

## Context

Nova grew two automatic buyers one ADR at a time. ADR 027 gave the bot one level and one setup. ADR 031 added a scanner and an Off / Eyes switch per setup but kept Strategy for "the chosen setup" (a radio), because the bot's loop, the Live read-out gate and the one-trade-a-day count were written for one setup. ADR 037 added Auto-entry (Nova buys, you sell) beside the bot, with its own risk, its own daily count, its own entry timeout, and no setup level at all. The pieces each made sense; together they did not:

- **Two owners of one decision.** The radio and the card switch both said which setup the bot trades. About eight "add to bot allowlist" buttons wrote the bot's list without the Who-trades switch, so one stock could be on the bot's list and in Auto-entry at once, and both could buy the same trigger.
- **Rules the screen did not say.** A setup at Off still fed Auto-entry. The plan said NOT A TRADE while the bot and Auto-entry took the trade. "Read-out to unlock Strategy on Live" unlocked nothing for Nova's bot (it never trades Live) and opened the localhost bot API on Live instead.
- **Locks that outlived their reason or never applied.** Activate survived a restart and a locked padlock (only an open page stopped the bot). The day lock and the bot trip lifted at midnight while the practice day's P&L rolled at 04:00, so yesterday's loss tripped them again. The kill switch said "every working order" and swept the current venue only, and nothing at all with the Gateway down.
- **Numbers that disagreed.** Four sizes for one trigger, two daily counts (one in memory), two entry timeouts, three windows per setup never checked against each other, a Depth lines gate that could not pass with more than three stocks.

## Decision

1. **A level per setup under a master ceiling; the chosen setup is gone.** The session's `level` (per venue, ADR 032 amendment) is the most any setup may do on this venue; `setup_levels` holds Off / Eyes / Strategy for every setup with a scanner; a setup's effective level is the lower of the two. At Strategy the bot may trade that setup's go triggers while it is Active; until then the setup proposes like Eyes. `PATCH {setup}` is refused `BOT_SETUP_RETIRED`. The session file moves to schema 5 (the old chosen setup keeps its old level).
2. **One Activate, never carried.** One control, offered only when it would be accepted; refused with a stated code on Live, on a replay desk, below Strategy, with no setup at Strategy, with the padlock locked, or after a bot trip unless the operator re-enables in words. The backend clears it on every start, when the padlock is locked, on a venue change, and when nothing is left at Strategy, and says why (`deactivated`).
3. **Every gate is drawn with its reason** (`venue`, `level`, `setups`, `padlock`, `allowlist`, `depth_lines` (one held stock is enough), `bot_trip`, `day_lock`, `kill_switch`, `window` per setup, `daily_cap`, `extended_hours`, `commissions`). The `readout` gate goes: on Live the `venue` gate refuses.
4. **One sleeve per venue** sizes every Nova automatic buy: `risk_usd` (risk per trade, which the Trader's plan also reads and edits), `max_shares`, `bp_budget_usd`, `working_ttl_sec` (the one entry timeout for the bot, Auto-entry and Approve), `extended_hours` (now binding), `entries_per_day` (one persisted count for the bot and Auto-entry; Approve is counted, not capped), `api_kinds`.
5. **One owner for which stocks.** The bot's list is written only through the Who-trades rules, per venue (Live's is empty); a stock has one mode at a time. Auto-entry is the bot's rules with the exit handed to the operator: a setup at Strategy, the first of the day, its window, the shared cap, the sleeve, only while Active. Take over always leaves Buy on the operator. Nova's trades are persisted and managed after a restart; leaving a venue cancels Nova's working entries there first and says so.
6. **NOT A TRADE is one rule** (`setup_scanner/trade_verdict.py`), read by the plan, the bot, Auto-entry, Approve and proposals. A proposal the bot or Auto-entry will take says so and cannot be staged.
7. **Nova's bot plays every setup at Strategy**: the first go trigger wins, one trade at a time. Its entry is a practice bracket, so its stop and target rest at the broker (Paper's matcher runs whatever the desk shows); the time stop and the flush exit stay the runner's. Every order carries its real setup.
8. **Stops say what they do.** The day lock and the bot trip lift at 04:00 ET; the day lock belongs to a venue (#658 option b: Live's lock follows Live and is not escaped by switching); a replay desk trips nothing; the kill switch cancels on every venue that has orders and states any it could not reach.
9. **The localhost bot API refuses Live** (`BOT_LIVE_NOT_BUILT`) until the operator decides it on its own. Read-outs stay as evidence with their pre-registered rules and say plainly that passing one unlocks nothing yet.
10. **Templates hold the scanner's rules; the bot's rules do not restart a read-out.** Bot parameters are left out of a template's revision; the bot window must sit inside the arming window; auto-record keeps setups first through every arming window.

## Consequences

- The Bots page has no radio; each card's switch is the whole decision, under the hero's ceiling. The header names the level and how many setups are at Strategy.
- After a restart nothing automatic buys until the operator presses Activate.
- Auto-entry sizes like the bot, so on the default sleeve (1 share, $50) it buys far less than its old risk-sized orders did; the sleeve's sliders are the way to change that.
- With NOT A TRADE binding and most arms graded C, Nova's bot will skip most triggers; each skip is on the timeline and on that stock's Trader tab.
- Left for the operator: whether a bot ever trades Live.

## Amendment — venue defaults and confirmed snapshots (2026-10-06, #657/#658)

The operator accepted the grouped implementation plan with `1 go`, asking us
to verify that the backlog is current and hold any unresolved operator call.
Current master and all issue comments confirm #661 already repaired account
snapshots and Who trades; #665 already separated risk, locks, caps and the bot
list. Only stock-order defaults and the stale bot snapshot remain in this batch.
The accepted plan separates defaults by venue, consistent with the existing
sleeves. A bot trading Live remains an unresolved, held decision outside it.

- **Stock defaults belong to Live, Paper or Sim.** Settings, mounted tickets,
  staging helpers and submission read the explicit backend-confirmed desk venue,
  never a Gateway-mode fallback. Unknown venue uses factory values and cannot
  persist settings. The deliberately shared place-confirmation preference stays
  shared. Venue switches invalidate prepared submission and reseed open tickets;
  ordinary preference changes update the relevant values without erasing edits
  to unrelated prices. Stage uses the same confirmed venue and generation;
  an unknown venue disables Stage with its reason, a changed generation cancels
  delayed replay, and a refused stage never dismisses its proposal.
- **Storage owner and migration.** `settings/tradeDefaultsPrefs` owns
  `nova.trade.defaults.v2.<venue>` with `{schema_version:2, venue, prefs}` (the
  existing preference fields). A schema-1 receipt at
  `nova.trade.defaults.migration.v1` binds legacy `nova.trade.defaults.v1` to the
  first confirmed venue only. Verify the receipt and destination before removing
  the legacy source; preserve it on failure, let existing destination values win,
  and never clone old practice choices to all venues. Other venues retain the
  factory DAY/optional-legs-off defaults. Refuse unknown versions and mismatched
  venue ownership on both reads and writes; editing factory fallback values must
  preserve an unsupported existing record and show the save refusal. Same-window
  notifications and storage events keep readers current. Venue/version changes
  invalidate consumer snapshots; storage failure is visible to the editor.
- **One confirmed venue source.** The IBKR feature exports a stable nullable
  venue/generation snapshot, subscription and hook through its public barrel.
  `confirmedDeskVenueStore` owns the `confirmed-venue` desk-shared-poll channel
  (`nova.desk.poll.snap.confirmed-venue` / `nova-desk-poll-confirmed-venue`) with
  `{schema_version:1, venue, generation, revision}`. This is synchronization
  metadata, never cached proof of a backend venue. Fresh explicit status or a
  successful desk-venue response supplies authority. Existing shared-snapshot
  expiry applies; transition/schema changes invalidate it. Every transition,
  including Paper → Live → Paper, gets a new token. A late status GET or
  desk-venue POST reply cannot undo a newer confirmed transition from another
  window. Track confirmed transitions while the POST is pending. A first
  confirmation of its requested venue may precede the reply and must retain its
  required Gateway launch, without republishing an older generation. A competing
  transition or ABA invalidates the pending acknowledgment. Refresh authoritative
  status afterward, including when a concurrent transition invalidates the reply.
  A stale reply's `left` entries are historical cancellation facts, not current
  venue authority. Show those notices on the unchanged real route even when the
  venue fence rejects its acknowledgment; never restore stale venue state or
  launch its Gateway action. The sample-route fence still rejects real replies
  after a sample visit.
- **Bot state follows that source.** Clear old state and request an immediate
  refresh on a confirmed transition; queue it if an old read is busy. Stamp
  snapshots with venue and generation, validate `session.level_venue`, and reject
  old HTTP, mutation and shared responses (including unstamped legacy shares).
  Keep one shared bot polling leader. Sample data neither migrates real settings
  nor publishes real venue changes.

Regression evidence must include mounted same-symbol ticket/Settings switches,
one-time/failed migration, cross-window changes, late GET/write/share replies,
ABA transitions, queued refresh, sample isolation and explicit Live on the legacy
Paper Gateway. Existing account, Who-trades, confirmation and protective-leg
checks remain neighbors. This amendment changes frontend ownership, not backend
spending gates or the held Live-bot decision.
