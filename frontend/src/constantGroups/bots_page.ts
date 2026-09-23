/**
 * The Bots page (approved mockup v4, ADR 027): its copy and tunables. The bot's
 * API constants stay in ./bot.ts; this group is what the page itself says.
 */
import type { DeskVenue } from './desk_venue';

export const BOTS_PAGE_TITLE = 'Bots';
export const BOTS_PAGE_SUB =
  'Your playbook, run by the bot: what it watches, what it may risk, what it proposed and did.';
export const BOTS_PAGE_LOADING = 'Loading the bot session…';
export const BOTS_PAGE_SAVING = 'Saving…';

/** The venue chip's second half: whose money the bot would be spending. */
export const BOTS_VENUE_NOTES: Record<DeskVenue, string> = {
  live: 'Live account — real money, every gate below applies',
  paper: 'Nova Paper — fake money on the live feed',
  sim: 'Sim scratch account — rewinds with the playhead',
};
export const BOTS_VENUE_LABELS: Record<DeskVenue, string> = { live: 'Live', paper: 'Paper', sim: 'Sim' };
export const BOTS_VENUE_UNKNOWN = 'Venue unknown — the desk status has not answered';

/** An API older than ADR 027 reports no gates and no read-out: say so, never "every gate is open". */
export const BOTS_STALE_API =
  'This API is older than the Bots page: it reports no gates and no read-out. Restart the backend (gear → Reload backend) to see them.';
export const BOTS_HERO_NO_GATES = 'The gates are not reported by this API, so nothing here can say whether the bot may fire.';

/* ---------- Hero ---------- */
export const BOTS_GATES_TOTAL_LABEL = 'gates';
export const BOTS_ACTIVATE_WAITS_ON = 'Activate waits on';
export const BOTS_IN_CONTROL_LABEL = 'Bot is in control of order entry';
export const BOTS_ERROR_UNLOCK_FIRST =
  'Unlock the padlock first — choosing Strategy needs Activate, and Activate needs the desk armed';
export const BOTS_KILL_TRIP_LABEL = 'Stop all orders';
export const BOTS_KILL_TRIP_NOTE = '(kill switch)';
export const BOTS_KILL_RESET_LABEL = 'Reset kill switch';
export const BOTS_KILL_TRIPPED_NOTE = 'Kill switch tripped — every new order is refused';

/** Gate chip actions: the link text after the dash. */
export const BOTS_GATE_UNLOCK = 'unlock padlock';
export const BOTS_GATE_CONNECT = 'connect IB Gateway';
export const BOTS_GATE_OPEN_L2 = (symbol: string): string => `open ${symbol} Level 2`;
export const BOTS_GATE_READOUT_LINK = 'first pullback not proven yet';
export const BOTS_GATE_ADD_SYMBOL = 'add a symbol';
export const BOTS_GATE_RESET_KILL = 'reset it';
export const BOTS_GATE_MORE = (n: number): string => `+${n} more`;
export const BOTS_GATE_FIRE_TITLE = 'Checked on every order, not at Activate';
export const BOTS_GATE_ACTIVATE_TITLE = 'Activate at Strategy needs this gate';

/* ---------- Strategies ---------- */
export const BOTS_STRATEGIES_TITLE = 'Strategies';
export const BOTS_STRATEGIES_SOURCE = 'from your course material';
export const BOTS_STRATEGIES_SUB = 'one setup plays at a time · each has its own level';
export const BOTS_SETUP_PICK_TITLE = 'Play this setup';
export const BOTS_SETUP_LEVEL_TITLE = 'The bot level for the setup that plays';
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
  `Your catalogue is on this PC at ${BOTS_CATALOGUE_PATH}. A setup lands here with three things: a live scanner that finds it, a backtest on the five-year history, and a read-out it must pass before the bot may trade it. Until then it is listed without a level. Pick one from the catalogue and ask for it to be built.`;
export const BOTS_ADD_SETUP_COPY = 'Copy catalogue path';
export const BOTS_ADD_SETUP_CLOSE = 'Close';
export const BOTS_READOUT_GO_SO_FAR = 'GO so far';
export const BOTS_READOUT_VS = 'vs blind / wait';
export const BOTS_READOUT_UNREPORTED = 'Read-out not reported by this API — restart the backend to see it.';

/* ---------- Symbols ---------- */
export const BOTS_SYMBOLS_TITLE = 'Symbols';
export const BOTS_SYMBOLS_SUB = 'empty list = bot does nothing';
export const BOTS_SYMBOLS_EMPTY = 'No symbols yet. The bot only ever looks at the symbols listed here.';
export const BOTS_SYMBOLS_PLACEHOLDER = 'Add ticker… (or right-click a scanner row, trader tab or chart)';
export const BOTS_SYMBOLS_CAP = (cap: number): string => `The list holds at most ${cap} symbols.`;
export const BOTS_L2_HELD = 'Held';
export const BOTS_L2_HELD_VIA: Record<'trader' | 'record', string> = { trader: 'Trader', record: 'Record' };
export const BOTS_L2_HELD_TITLE = 'Nova holds this symbol\'s depth line: the bot can read its tape';
export const BOTS_L2_OPEN = 'Not held · Open L2';
export const BOTS_L2_OPEN_TITLE = 'Open its Level 2 in a pinned Trader tab so the bot can read the tape';
export const BOTS_LAST_TITLE = 'Last print from the setup scanner, else the scanner row';
export const BOTS_CHG_TITLE = 'Change against the prior close; blank when no board carries the symbol';

/* ---------- Risk sleeve ---------- */
export const BOTS_RISK_TITLE = 'Risk sleeve';
export const BOTS_RISK_SUB = 'per bot order';
export const BOTS_SLIDER_COMMIT_MS = 400;
export const BOTS_EH_LABEL = 'Extended hours';
export const BOTS_EH_ON = 'On · 07:00';
export const BOTS_EH_OFF = 'Off';
export const BOTS_EH_HINT = 'Needed for pre-market setups';
export const BOTS_BREAKERS_TITLE = 'Loss breakers';
export const BOTS_BREAKERS_LOCKED = 'locked';
export const BOTS_BREAKER_TODAY = 'today';
export const BOTS_BREAKER_TODAY_UNKNOWN = 'today unknown';
export const BOTS_BOT_PNL_POLL_MS = 5_000;
export const BOTS_ADVISE_TITLE = 'Advise budget (never places)';

/* ---------- Proposals ---------- */
export const BOTS_PROPOSALS_TITLE = 'Proposals';
export const BOTS_PROPOSALS_SUB = 'nothing here places · you press Place';
export const BOTS_PROPOSALS_EMPTY =
  'No open proposals. The scanner raises one when a first pullback is near its trigger and the tape says go.';
export const BOTS_PROPOSALS_FOOT = 'Proposals pop up on every tab; this is where they are kept.';
export const BOTS_PROPOSAL_UNDER = 'under the trigger';
export const BOTS_PROPOSAL_AT = 'at the trigger';
export const BOTS_PROPOSAL_STAGE = 'Stage ticket';
export const BOTS_PROPOSAL_DISMISS = 'Dismiss';
export const BOTS_PROPOSAL_CLOSED_KEEP_SEC = 30 * 60;
export const BOTS_PROPOSAL_CLOSED_MAX = 4;
export const BOTS_DISMISSED_STORAGE_KEY = 'nova.bots.dismissedProposals.v1';
/** Why a proposal left the open list (backend setup_scanner PROPOSAL_CLOSE_REASONS). */
export const BOTS_PROPOSAL_CLOSED_LABELS: Record<string, string> = {
  rearmed: 'withdrawn',
  disarmed: 'withdrawn',
  failed: 'withdrawn',
  triggered: 'triggered',
};

/* ---------- Activity ---------- */
export const BOTS_ACTIVITY_TITLE = 'Activity';
export const BOTS_ACTIVITY_EMPTY = 'Nothing yet today.';
export const BOTS_ACTIVITY_LIMIT = 30;
export const BOTS_SETUP_ROWS_POLL_MS = 15_000;

/* ---------- Today ---------- */
export const BOTS_TODAY_TITLE = 'Today';
export const BOTS_TODAY_BOT_ONLY = 'bot only';
export const BOTS_TODAY_SCOREBOARD_DAYS = 5;
export const BOTS_TODAY_PNL_LIVE_TITLE =
  'Live keeps no practice ledger here: the bot\'s own fills show on the Account page';
export const BOTS_TODAY_SCOREBOARD_TITLE = 'First pullback scoreboard';
export const BOTS_TODAY_SCORES_NOTE = 'Scores, not fills — the research exit rules on every armed setup.';

/* ---------- Status bar ---------- */
export const BOTS_STATUS_NO_SYMBOL = 'No symbol selected';
export const BOTS_STATUS_FLAT = 'flat';
export const BOTS_STATUS_ORDER_KINDS = 'Order kinds the bot may send:';

/* ---------- Header pill ---------- */
export const BOTS_PILL_LABEL = 'Bot';
export const BOTS_PILL_TITLE = 'Open the Bots page';
