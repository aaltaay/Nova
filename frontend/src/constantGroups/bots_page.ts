/**
 * The Bots page (approved mockup v4, ADR 027, ADR 042): its copy and tunables. The
 * bot's API constants stay in ./bot.ts; this group is what the page itself says.
 */
import type { DeskVenue } from './desk_venue';

export const BOTS_PAGE_TITLE = 'Bots';
export const BOTS_PAGE_SUB =
  'Your playbook, run by the bot: what it watches, what it may risk, what it proposed and did.';
export const BOTS_PAGE_LOADING = 'Loading the bot session…';
export const BOTS_PAGE_SAVING = 'Saving…';

/** The venue chip's second half: whose money the bot would be spending. */
export const BOTS_VENUE_NOTES: Record<DeskVenue, string> = {
  live: 'Live account — real money · Nova\'s bot does not trade here',
  paper: 'Nova Paper — fake money on the live feed',
  sim: 'Sim scratch account — rewinds with the playhead',
};
export const BOTS_VENUE_LABELS: Record<DeskVenue, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
export const BOTS_VENUE_UNKNOWN = 'Venue unknown — the desk status has not answered';
/** The venue a gate or a line names, as the header pills say it. */
export const BOTS_VENUE_NAMES: Record<string, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };

export const BOTS_KILL_TRIP_NOTE =
  'Cancels every working order on every venue and refuses every new order, from you or from Nova, a sell included, until you unfreeze. It sells nothing; the red KILL at the top is the one that sells.';
export const BOTS_KILL_RESET_LABEL = 'Unfreeze orders';
export const BOTS_KILL_TRIPPED_NOTE = 'Orders are frozen: every new order is refused on every venue until you unfreeze (Flatten and cancels still work)';
export const BOTS_KILL_SWEEP_HEAD = 'Freezing cancelled';
export const botsKillSweepCancelled = (n: number, ids: string): string =>
  `cancelled ${n} order${n === 1 ? '' : 's'}${ids ? ` (${ids})` : ''}`;
export const botsKillSweepFailed = (n: number, ids: string): string =>
  `could not cancel ${n}${ids ? ` (${ids})` : ''} — still working`;
export const BOTS_KILL_SWEEP_NOTHING = 'nothing was working';

/** Gate chip actions: the link text after the dash. */
export const BOTS_GATE_UNLOCK = 'unlock padlock';
export const BOTS_GATE_OPEN_L2 = (symbol: string): string => `open ${symbol} Level 2`;
export const BOTS_GATE_ADD_SYMBOL = 'add a stock';
export const BOTS_GATE_SETUPS = 'set a card to Strategy';
export const BOTS_GATE_RESET_KILL = 'unfreeze';

/* ---------- Strategies ---------- */
export const BOTS_STRATEGIES_TITLE = 'Strategies';
export const BOTS_STRATEGIES_SOURCE = 'from your course material';
export const BOTS_STRATEGIES_SUB =
  'every scanner runs at once · each strategy is Off, Eyes or On · Nova acts on those at On while the Bot is on';
export const BOTS_STRATEGIES_SUB_TIP =
  'Every setup with a scanner runs at the same time: each follows the HOD Momo names and today\'s hot list on one-minute bars, reads the tape at its trigger and scores every setup it arms on its own read-out.\n'
  + 'Each strategy is Off (silent, draws nothing on your charts), Eyes (draws its setups and alerts you near + GO) or On (everything Eyes does, and Nova may act on its GO triggers while the Bot is on, Paper and Sim only). Any number can be at each.\n'
  + 'While the Bot is off, a strategy at On alerts you like Eyes, and says so.';

/* ---------- A scanner for every setup (ADR 031) ---------- */
/** Rows a setup card's own scanner shows; "Open board" has the rest. */
export const BOTS_SCANNER_MAX_ROWS = 7;
export const BOTS_SCAN_FOOT = (shown: number, total: number): string =>
  total > shown ? `${shown} of ${total} · nearest the trigger first` : `${total} on the board · nearest the trigger first`;
export const BOTS_SCAN_FOOT_TIP =
  'This setup\'s names on the live board: near the trigger first, then armed, triggered in the last 30 minutes, forming, and failed in the last 5 minutes.';
export const BOTS_STATUS_WATCHING = (n: number): string => `Watching ${n} name${n === 1 ? '' : 's'}`;
export const BOTS_STATUS_SEEDING = (n: number): string => `${n} seeding bars`;
export const BOTS_STATUS_NOT_CONNECTED = 'Scanner not connected';
/** A recorded moment in Sim (backend eyes/playback.py): this setup's scanner was not running then. */
export const BOTS_STATUS_NOT_RECORDED = 'Not running at this moment';
export const BOTS_STATUS_NOT_RECORDED_TIP =
  'Nova\'s eyes have no record of this setup at the playhead: Nova was closed, its eyes were off, or this setup\'s '
  + 'scanner did not exist yet. Nothing is drawn rather than a guess.';
export const BOTS_FUNNEL_TODAY = 'Today';
export const BOTS_FUNNEL_TIP =
  'Today on this setup\'s scanner, in the order a setup moves: forming, armed, near the trigger, triggered — then how many failed and how many raised a proposal. The first four are a funnel; each step is a subset of the one before it.';
export const BOTS_READOUT_SHORT = 'Read-out';
export const BOTS_READOUT_GO_SHORT = 'go';
export const BOTS_NO_SCANNER_WHY_HEAD = 'Why it can\'t watch yet.';
export const BOTS_NO_SCANNER_UNBLOCK_HEAD = 'Unblocks when';
export const BOTS_TEMPLATE_RULES_TIP = (lines: string): string =>
  `The template in play, in the numbers the scanner runs:\n${lines}\nParameters opens every one of them.`;
export const BOTS_TAPE_GATE_HEAD = 'Tape gate';
export const BOTS_RESEARCH_BADGES: Record<string, string> = {
  failed: 'Bars alone: failed',
  not_tested: 'Not tested',
  testing: 'Testing',
};
/** Where the operator's catalogue lives on the desk PC (off the repo, ADR 027). */
export const BOTS_CATALOGUE_PATH = 'F:\\Nova\\private\\strategy-catalogue';
export const BOTS_ADD_SETUP_LABEL = 'Add a setup from your catalogue';
export const BOTS_ADD_SETUP_HINT =
  'The full list is on your desk PC (F:). Each one lands here with its rules, a backtest and a scanner.';
export const BOTS_ADD_SETUP_MESSAGE =
  `Your catalogue is on this PC at ${BOTS_CATALOGUE_PATH}. A setup lands here with three things: a live scanner that finds it, a backtest on the five-year history, and a read-out that measures it. Until then it is listed without a level. Pick one from the catalogue and ask for it to be built.`;
export const BOTS_ADD_SETUP_COPY = 'Copy catalogue path';
export const BOTS_ADD_SETUP_CLOSE = 'Close';
export const BOTS_READOUT_GO_SO_FAR = 'GO so far';
export const BOTS_READOUT_VS = 'vs blind / wait';
export const BOTS_READOUT_NEEDS = (minR: number): string => `needs > +${minR.toFixed(2)}R and above blind / wait`;

/* ---------- Templates (ADR 029): every setup's parameters and its variations ---------- */
export const BOTS_TEMPLATES_POLL_MS = 30_000;
export const BOTS_TEMPLATE_LABEL = 'Template';
export const BOTS_TEMPLATE_PARAMS = (n: number): string => `Parameters (${n})`;
export const BOTS_TEMPLATE_PICK_TITLE = 'The template in play for this setup: the one that proposes, the bot trades and draws its rows. Every template of the setup is watched and scored at once.';
export const BOTS_TEMPLATE_BUILTIN_WHY =
  'The default is the pre-registered rules and stays as it is -- use "New from this" to make a variation you can change';
export const BOTS_TEMPLATE_SAVING_WHY = 'Saving the last change -- wait for Nova to answer';
export const BOTS_TEMPLATE_NOTHING_CHANGED_WHY = 'Nothing changed yet -- edit a value first';
export const BOTS_TEMPLATE_UNFIXED_WHY = 'A value is out of range -- fix the field marked in red first';
export const BOTS_TEMPLATE_IN_PLAY_WHY = 'Already in play';
export const BOTS_TEMPLATE_LIMIT_WHY = (n: number): string =>
  `A setup keeps at most ${n} templates, the default included -- delete one first`;
export const BOTS_TEMPLATE_NO_PARAMS =
  'No parameters yet: this setup has never been tested. They are set when its one-second test (S5) is built.';
export const BOTS_TEMPLATE_NO_PARAMS_WHY = 'No parameters yet -- this setup has never been tested';
export const BOTS_TEMPLATE_UNREAD_WHY = (err: string | null): string =>
  `The templates did not load${err ? ` -- ${err}` : ''}`;
export const BOTS_TEMPLATE_LOADING_WHY = 'Loading the templates -- wait for Nova to answer';
export const BOTS_TEMPLATE_DELETE_CONFIRM = (name: string): string =>
  `Delete "${name}"? The setups it scored stay on record; the scanner stops watching its rules.`;
export const BOTS_TEMPLATE_EVIDENCE_RESET = (name: string, rev: number, scored: number, keys: string): string =>
  `Saving new scanner rules on "${name}" (${keys}) starts its evidence over: its read-out restarts at 0 of 50, because the setups `
  + `so far were found by the old rules. The ${scored} go setup${scored === 1 ? '' : 's'} it has now stay on record under revision ${rev}.`;
export const BOTS_TEMPLATE_BOT_ONLY_NOTE =
  'Only bot parameters changed: the read-out keeps counting, because they do not change what the scanner finds.';
export const BOTS_TEMPLATE_BOT_WINDOW = (start: string, end: string, clipped: boolean): string =>
  `Bot window ${start}–${end}${clipped ? ' (clipped to the arming window: the bot never buys outside where the setup can arm)' : ''}`;
export const BOTS_PARAM_FILTER_OFF_WHY = 'Off -- tick the box beside it to use this filter';

/* ---------- Why a Bots page control is locked (ux/whyTip.ts) ---------- */
export const BOTS_BUSY_WHY = 'Saving the last change to the bot -- wait for Nova to answer';
export const BOTS_SESSION_LOADING_WHY = 'The bot session has not loaded yet';
export const BOTS_KEY_EMPTY_WHY = 'Paste the API key first';
export const BOTS_KILL_BUSY_WHY = 'The kill switch is answering the last press -- wait for Nova';
export const BOTS_KILL_UNREAD_WHY = (err: string | null): string =>
  `The kill switch state has not loaded${err ? ` -- ${err}` : ''}`;
export const BOTS_SETUP_NO_LEVELS_WHY =
  'This API keeps one level for every setup -- restart the backend to give each setup its own';
export const BOTS_NOT_TRADING_NOW = 'Not trading now';
/** Anchor of the Strategies card, for the "set a card to Strategy" gate link. */
export const BOTS_STRATEGIES_ANCHOR = 'bots-strategies-card';

export const BOTS_STOCK_MODES_POLL_MS = 5_000;

/* ---------- Risk sleeve (ADR 042 E): one per venue ---------- */
export const BOTS_RISK_TITLE = 'Risk sleeve';
export const BOTS_RISK_SUB = 'every Nova buy on the venue shown';
export const BOTS_RISK_TIP =
  'One sleeve per venue sizes and caps every automatic Nova buy there — the bot and Auto-entry — and sets the risk your Stage sizes by. Each venue keeps its own; the tab shows which one you are editing.';
export const BOTS_RISK_LIVE_NOTE = 'Nova buys nothing by itself on Live: these numbers size your own Stage there and bind no bot.';
export const BOTS_SLIDER_COMMIT_MS = 400;
export const BOTS_RISK_LABEL = 'Risk per trade';
export const BOTS_RISK_SLIDER_TIP =
  'Sizes every Nova buy and your Stage: shares = risk ÷ risk per share, capped by max shares and the budget.';
export const BOTS_ENTRIES_LABEL = 'Nova entries a day';
export const BOTS_ENTRIES_SLIDER_TIP =
  'One count for the bot and Auto-entry on this venue. A missed entry gives the day back; Approve is yours and never capped.';
export const BOTS_SHARES_LABEL = 'Max shares';
export const BOTS_SHARES_TIP = 'The most shares one Nova buy may be, whatever the risk would buy.';
export const BOTS_BUDGET_LABEL = 'Buying-power budget';
export const BOTS_BUDGET_TIP = 'The most one Nova buy may spend (shares × entry).';
export const BOTS_TTL_LABEL = 'Entry time-to-live';
export const BOTS_TTL_TIP = 'An unfilled Nova entry — the bot, Auto-entry or Approve — is cancelled after this, and a missed entry gives the day back.';
export const BOTS_EH_LABEL = 'Extended hours';
export const BOTS_EH_ON = 'On · 07:00';
export const BOTS_EH_OFF = 'Off';
export const BOTS_EH_HINT = 'Off: the bot and Auto-entry skip triggers outside 09:30–16:00 ET, and say so';
export const BOTS_KINDS_LABEL = 'Order kinds (the localhost bot API)';
export const BOTS_KINDS_TIP =
  'What an external bot on the localhost bot API may send on Paper and Sim. Nova\'s own bot and Auto-entry use their own entry and bracket. The API refuses Live.';
export const BOTS_BREAKERS_TITLE = 'Loss breakers';
/** ADR 032: the breakers are the operator's, per venue. */
export const BOTS_BREAKERS_VENUE = (venue: string): string => `${venue} · drag to move`;
export const BOTS_BREAKERS_DEFAULTS = 'defaults';
export const BOTS_BREAKERS_CUSTOM = 'yours';
export const BOTS_BREAKERS_OLD_API =
  'This API keeps the breakers fixed at −$50 / −$200 -- restart the backend to move them';
export const BOTS_BREAKERS_RESET = 'Reset to −$50 / −$200';
export const BOTS_BREAKERS_SAVING = 'Saving…';
export const BOTS_BREAKER_TODAY = 'today';
export const BOTS_BREAKER_TODAY_UNKNOWN = 'today unknown';
export const BOTS_BOT_PNL_POLL_MS = 5_000;
export const botsSoftFired = (when: string, pnl: string, until: string): string =>
  `Bot trip fired${when ? ` at ${when}` : ''}${pnl ? ` at ${pnl}` : ''}: the bot is off on this venue${until ? ` until ${until}` : ' until 04:00 ET'}; turning it back on asks you first.`;
export const botsDayLocked = (venue: string, when: string, pnl: string, until: string): string =>
  `All-stop fired${when ? ` at ${when}` : ''}${pnl ? ` at ${pnl}` : ''}: bot and manual buys on ${venue} are locked${until ? ` until ${until}` : ' until 04:00 ET'}. Flatten and cancel still work.`;

/* ---------- Proposals ---------- */
export const BOTS_PROPOSALS_TITLE = 'Proposals';
export const BOTS_PROPOSALS_SUB = 'Stage fills your ticket · you press Place';
export const BOTS_PROPOSALS_EMPTY =
  'No open proposals. A setup at Eyes or above raises one when it is near its trigger and the tape says go.';
export const BOTS_PROPOSALS_FOOT = 'Proposals pop up on every tab; this is where they are kept.';
export const BOTS_PROPOSAL_UNDER = 'under the trigger';
export const BOTS_PROPOSAL_AT = 'at the trigger';
export const BOTS_PROPOSAL_STAGE = 'Stage ticket';
export const BOTS_PROPOSAL_DISMISS = 'Dismiss';
export const BOTS_PROPOSAL_CLOSED_KEEP_SEC = 30 * 60;
export const BOTS_PROPOSAL_CLOSED_MAX = 4;
export const BOTS_PROPOSAL_TAKEN: Record<string, string> = {
  bot: 'The bot is taking this — nothing to do',
  auto_entry: 'Auto-entry is taking this — nothing to do',
};
export const BOTS_PROPOSAL_TAKEN_WHY: Record<string, string> = {
  bot: 'Nova\'s bot is taking this trigger -- staging your own ticket would buy it twice',
  auto_entry: 'Auto-entry is taking this trigger -- staging your own ticket would buy it twice',
};
export const botsNotATrade = (reasons: string): string => `Not a trade: ${reasons}`;
export const botsNotATradeWhy = (reasons: string): string => `Not a trade -- ${reasons}`;
/** Why a proposal left the open list (backend setup_scanner PROPOSAL_CLOSE_REASONS). */
export const BOTS_PROPOSAL_CLOSED_LABELS: Record<string, string> = {
  rearmed: 'withdrawn',
  disarmed: 'withdrawn',
  failed: 'withdrawn',
  triggered: 'triggered',
  template: 'withdrawn',
  edited: 'withdrawn',
  deleted: 'withdrawn',
};

/* ---------- Activity ---------- */
export const BOTS_ACTIVITY_TITLE = 'Activity';
export const BOTS_ACTIVITY_EMPTY = 'Nothing yet today.';
export const BOTS_ACTIVITY_LIMIT = 30;
export const BOTS_SETUP_ROWS_POLL_MS = 15_000;

/* ---------- Today ---------- */
export const BOTS_TODAY_TITLE = 'Today';
export const BOTS_TODAY_SCOREBOARD_DAYS = 5;
export const BOTS_TODAY_PNL_LIVE_TITLE =
  'Live keeps no practice ledger here, and Nova\'s bot does not trade Live: your own fills show on the Account page';
export const BOTS_TODAY_SCOREBOARD_TITLE = (setup: string): string => `${setup} scoreboard`;
export const BOTS_TODAY_SETUP_PICK = 'Setup the counts and the scoreboard read';
export const BOTS_TODAY_SCORES_NOTE = 'Scores, not fills — the research exit rules on every armed setup of the template in play.';
export const botsTodayArmedTip = (setup: string): string =>
  `${setup} setups the scanner armed today (its template in play): the pattern was in place with a trigger and a stop. Scores, not trades.`;
export const botsTodayTriggeredTip = (setup: string): string =>
  `${setup} setups that traded over the trigger today. Each is scored on the scoreboard; the bot bought only those it took.`;
export const BOTS_TODAY_PROPOSED_TIP = 'Proposals every setup at Eyes or Strategy raised today (near + GO), from the bot audit stream.';
export const BOTS_TODAY_ENTRIES_TIP =
  'Nova\'s automatic buys today on this venue: the bot and Auto-entry, one count, against the sleeve\'s cap.';
export const BOTS_TODAY_PNL_TIP =
  'The bot\'s own fills today in this venue\'s practice ledger (source bot), net of fees and commission. Auto-entry and your own trades are not in it.';

/* ---------- Status bar ---------- */
export const BOTS_STATUS_NO_SYMBOL = 'No symbol selected';
export const BOTS_STATUS_FLAT = 'flat';
export const BOTS_STATUS_ORDER_KINDS = 'Order kinds (the localhost bot API):';

/* ---------- Header pill and the Trader rail card ---------- */
export const BOTS_PILL_LABEL = 'Bot';
export const BOTS_PILL_TITLE = 'Open the Bots page';
export const botsStrategiesOn = (n: number): string => (n === 1 ? '1 strategy On' : `${n} strategies On`);
