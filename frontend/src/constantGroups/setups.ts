/** Setup scanner UI (ADR 022). The backend owns the rules (`backend/constants_setups.py`). */
import {
  SHORT_FUNNEL_WORDS,
  SHORT_KIND_LABELS,
  SHORT_TRIGGER_LEVEL_WORDS,
  SHORT_TYPE_STATE_LABELS,
  SHORT_TYPE_STATE_TIPS,
} from './short_setups';

export const SETUPS_WS_PATH = '/ws/setups';
export const SETUPS_SCOREBOARD_PATH = '/api/setups/scoreboard';
/** One day's armed setups from setups.db (`?date=YYYY-MM-DD`). */
export const SETUPS_ROWS_PATH = '/api/setups/rows';
export const SETUPS_RECONNECT_MAX_MS = 30_000;
export const SETUPS_SCOREBOARD_POLL_MS = 30_000;
export const SETUPS_SCOREBOARD_DAYS = [1, 5, 20, 0] as const;   // 0 = all
export const SETUPS_SOUND_STORAGE_KEY = 'nova.setups.sound.v1';
export const SETUPS_PING_HZ = 1175;
export const SETUPS_PING_GAIN = 0.05;
export const SETUPS_PING_SEC = 0.22;
/** A staged ticket waits this long for the Trader tab's ticket to mount. */
export const SETUPS_STAGE_TICKET_DELAY_MS = 400;

export const SETUP_STATE_LABELS: Record<string, string> = {
  near: 'Near',
  armed: 'Armed',
  triggered: 'Triggered',
  pullback: 'Pulling back',
  leg: 'Leg up',
  failed: 'Failed',
  watching: 'Watching',
  filtered: 'Filtered',
};

export const SETUP_STATE_TITLES: Record<string, string> = {
  near: 'Price is within a few cents of the trigger: read the tape now.',
  armed: 'The pattern is in place. The trigger and stop are known; waiting for price to reach the trigger.',
  triggered: 'Price traded over the trigger. The scoreboard is now tracking what it did.',
  pullback: 'The pattern is there but one rule holds it back (MACD, risk size or time of day). The reason says which.',
  leg: 'Forming: the pattern has started (a leg, a pole, a push into the high, or red under the open) and has not armed yet.',
  failed: 'The pattern broke a rule before it triggered. The reason says which.',
  watching: 'Nothing to act on.',
  filtered: "The pattern armed, but the template's stock filter keeps this name out. The card follows the pattern, greyed: it never proposes and the bot never takes it. The reason says which rule.",
};

/** What a setup's trigger is, where "the trigger" would say less: the alert card and the watch toasts. */
export const SETUP_TRIGGER_LEVEL_WORDS: Record<string, string> = {
  red_to_green: 'open', flat_top_breakout: 'high', flat_top_5m: 'high', gap_and_go: 'pre-market high',
  ...SHORT_TRIGGER_LEVEL_WORDS,
};

export const SETUP_KIND_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  second_pullback: 'Second pullback',
  bull_flag: 'Bull flag',
  second_bull_flag: 'Second bull flag',
  flat_top_breakout: 'Flat-top breakout',
  second_flat_top_breakout: 'Second flat-top',
  flat_top_5m: '5-minute flat top',
  second_flat_top_5m: 'Second 5-minute flat top',
  red_to_green: 'Red to green',
  gap_and_go: 'Gap and Go',
  ...SHORT_KIND_LABELS,
};

/* ---------- Every setup's words (ADR 031) ----------
   One ladder of states for every setup -- forming (leg / pullback), armed, near,
   triggered or failed -- each said in the setup's own terms, and every chip
   explains itself on hover (ux/hoverTip.ts). setups/setupWords.ts puts the row's
   numbers into these. */

/** A state's chip text per setup, where it differs from SETUP_STATE_LABELS. */
export const SETUP_TYPE_STATE_LABELS: Record<string, Partial<Record<string, string>>> = {
  first_pullback: { leg: 'Leg up', pullback: 'Pullback · held back', triggered: 'Triggered' },
  bull_flag: { leg: 'Pole', pullback: 'Flag · held back', armed: 'Flag', triggered: 'Broke the flag' },
  flat_top_breakout: { leg: 'Pushing HOD', pullback: 'Base · held back', armed: 'Base', triggered: 'Held' },
  flat_top_5m: { leg: 'Pushing HOD', pullback: 'Base · held back', armed: '5m base', triggered: 'Held' },
  red_to_green: { leg: 'Red', pullback: 'Red · held back', armed: 'Red', near: 'Near the open', triggered: 'Reclaimed' },
  gap_and_go: { pullback: 'Open · held back', armed: 'Under the PMH', near: 'Near the PMH', triggered: 'Broke the PMH' },
  ...SHORT_TYPE_STATE_LABELS,
};

/** What each state means for each setup: the first paragraph of its hover. */
export const SETUP_TYPE_STATE_TIPS: Record<string, Partial<Record<string, string>>> = {
  first_pullback: {
    leg: 'A fresh high on a strong leg. The scanner now waits for the first pullback: one to three candles that hold the 9 EMA and give back less than half the leg.',
    pullback: 'A pullback is there, but one rule holds it back (MACD under zero, a risk outside the band, or the time of day). It arms as soon as the rule clears.',
    armed: 'The pullback is in place. The trigger is the last pullback candle\'s high; the stop is the pullback low. Waiting for price to come back up.',
    near: 'Price is a few cents under the trigger. The tape is read now: GO at the level is what makes a proposal.',
    triggered: 'Price traded over the trigger. The scoreboard follows it from here with the research exit rules — target first, stop first, or still open.',
    failed: 'The pullback broke a rule: a close under the 9 EMA, half the leg given back, or it ran too long.',
  },
  bull_flag: {
    leg: 'A pole: green candles in a row on rising volume. The scanner waits for the flag — two or three red candles on lighter volume that hold the 9 EMA and give back no more than half the pole.',
    pullback: 'A flag is there, but one rule holds it back (MACD under zero, a risk outside the band, or the time of day).',
    armed: 'The flag is in. The trigger is the last flag candle\'s high — the first candle to make a new high trades through it. The stop is the flag low.',
    near: 'Price is a few cents under the flag\'s high. The tape is read now: GO at the level is what makes a proposal.',
    triggered: 'Price broke over the flag. The scoreboard follows it from here — target first (the pole high or 2R), stop first, or still open.',
    failed: 'The flag broke a rule: too many red candles, too deep, heavy volume on the way down, a close under the 9 EMA, or the day\'s biggest candle was red.',
  },
  flat_top_breakout: {
    leg: 'A new high of day on an impulse, or a flat top still counting its touches: candles whose high comes back up to it (within 0.5% or a cent under it). From its second touch it is drawn forming; the third arms it.',
    pullback: 'A flat top is there, but one rule holds it back (MACD under zero, a risk outside the band, or the time of day).',
    armed: 'A flat top: the high of day tapped three times or more, the candles under it closing just below it on the 9 EMA. The trigger is that high.',
    near: 'Price is at the flat top. The tape is read now. Once a price trades over it, the first candle that holds it and closes green is the entry.',
    triggered: 'The breakout held: a candle held the flat top (a retest into the touch zone counts) and closed green over it. The scoreboard follows it from here.',
    failed: 'The base broke: it ran too long, lost the 9 EMA, or price closed back under the touch zone before a candle held it.',
  },
  flat_top_5m: {
    leg: 'On the 5-minute chart: a new high of day on an impulse, or a flat top still counting its touches (5-minute highs within 0.5% or a cent under it). From its second touch it is drawn forming; the third arms it.',
    pullback: 'A 5-minute flat top is there, but one rule holds it back (MACD under zero, or the time of day).',
    armed: 'A 5-minute flat top: the high of day tapped three times or more, the 5-minute candles under it closing just below it on their 9 EMA. The trigger is that high.',
    near: 'Price is at the flat top. The tape is read now. Once a price trades over it, the first 1-minute candle that holds it and closes green is the entry — the 1-minute pullback inside the 5-minute breakout candle.',
    triggered: 'The breakout held: a 1-minute candle held the flat top (a retest into the touch zone counts) and closed green over it. The stop is the pullback\'s low. The scoreboard follows it from here.',
    failed: 'The base broke on the 5-minute chart (it ran too long or lost the 9 EMA), or a 1-minute candle closed back under the touch zone before one held it.',
  },
  red_to_green: {
    leg: 'Trading under the open. Red to green needs enough closes under the open before a move back through it counts as the reclaim.',
    pullback: 'Red, but not a try yet: MACD under zero, or the risk from the low is outside the band (a reclaim now would spend the day\'s one try).',
    armed: 'Red under the open with the rules met. The trigger is the open itself; the stop is the lowest low since the open. One try a day.',
    near: 'Price is a few cents under the open. The tape is read now: GO at the level is what makes a proposal.',
    triggered: 'Price traded back over the open: red to green. The scoreboard follows it from here. That was the day\'s one try.',
    failed: 'The reclaim window closed, or the try was spent.',
  },
  gap_and_go: {
    watching: 'Before the open the scanner draws the pre-market high and the levels it would arm with. After the open it says why there is no try: a gap through the high, no break by the cutoff, or the day\'s try spent.',
    pullback: 'The stock opened under its pre-market high, but a template rule holds it back (MACD under zero). It arms when the rule clears.',
    armed: 'The stock opened under its pre-market high. The trigger is that high; the stop sits 20c or 4% under the entry, whichever is smaller. One try a day, until 10:00.',
    near: 'Price is a few cents under the pre-market high. The tape is read now: GO at the level is what makes a proposal.',
    triggered: 'Price traded over the pre-market high: Gap and Go. The scoreboard follows it from here. That was the day\'s one try.',
    failed: 'No break by the cutoff, a gap through the high at the open, or the try was spent.',
  },
  ...SHORT_TYPE_STATE_TIPS,
};

/** A setup's flat-top hold after the break (detail.broke_at). */
export const SETUP_FT_BROKE_LABEL = 'Broke · wants a hold';
export const SETUP_FT_BROKE_TIP = (level: string, at: string, n: number, minutes = false): string =>
  `Broke the ${level} high at ${at} ET. Now the first of the next ${n} ${minutes ? '1-minute candles' : 'candles'} that holds over it (its low at or over ${level}) and closes green is the entry — at its close +1c, stop ${minutes ? 'the pullback\'s low' : 'its low'}. A close back under ${level} fails the setup.`;

/** The tape verdicts' hover heads (the reasons and numbers follow). */
export const TAPE_VERDICT_TIPS: Record<string, string> = {
  go: 'GO: green prints at the ask and nothing big holding the level. This is what the bot waits for — at Eyes it proposes, at Strategy the bot may buy.',
  wait: 'WAIT: not yet. A seller at the level that is not thinning, a burst of selling on the tape, or no green prints yet.',
  veto: 'VETO: no. The spread is too wide, a very big seller sits at the level, or a hidden seller is soaking up the buying.',
  blind: 'BLIND: Nova holds no Level 2 line for this symbol, so the tape cannot be read. Blind setups are still scored — they are the read-out\'s control group. Open its Level 2 in the Trader to read it.',
};
export const TAPE_UNREAD_TIP = 'The tape is read only once a setup is armed or near its trigger.';

/** The tape flow score's labels (ADR 034): one number, -1 sellers .. +1 buyers. */
export const TAPE_FLOW_LABEL_WORDS: Record<string, string> = {
  burst: 'a burst of buying',
  flush: 'a flush of selling',
  neutral: 'neither side winning',
  quiet: 'too little tape to say',
  blind: 'no tape and no book',
};
/** The four readings the flow score averages, in the order the tip lists them. */
export const TAPE_FLOW_READING_WORDS: [string, string][] = [
  ['imbalance', 'ask vs bid'], ['pace', 'pace'], ['drift', 'price move'], ['book', 'book'],
];

/** The grade's hover head: what A / B / C mean (the pillars follow). */
export const SETUP_GRADE_TIP =
  'Grade: the Five Pillars (price, up on the day, relative volume, float, news). A = all five pass, B = four, C = three or fewer: not a trade. An unknown pillar counts as not passing, never as failed.';
export const SETUP_PILLAR_WORDS: Record<string, string> = {
  price: 'Price',
  change_pct: 'Up on the day',
  rvol: 'Relative volume',
  float: 'Float',
  news: 'News (a real catalyst)',
};

/** The column hovers on a setup card's mini scanner and the Setups board. */
export const SETUP_COL_TIPS: Record<string, string> = {
  symbol: 'Right-click for the symbol menu; click to open it in the Trader.',
  state: 'Where the setup is on its ladder: forming, armed, near the trigger, triggered, or failed. Hover a chip for what it means here.',
  trigger: 'The price that starts the trade: over it, the setup triggers.',
  last: 'The last price the scanner saw.',
  to_go: 'How far the last price is under the trigger. After a trigger: how it went so far, in R.',
  tape: 'The Level 2 and time and sales read at the level: GO, WAIT, VETO, or BLIND (no Level 2 line held).',
  grade: 'The Five Pillars when it armed: A, B or C.',
  tf5: 'The 5-minute chart on this 1-minute setup: ✓ its last 5-minute candle closed over its 9 EMA and its MACD is up; ✗ otherwise. In trial T8: shown only, it never blocks a trade.',
};

/** The funnel's words per setup: forming, armed, near, triggered, failed, proposed (ADR 031). */
export const SETUP_FUNNEL_WORDS: Record<string, { forming: string; armed: string; near: string; triggered: string }> = {
  first_pullback: { forming: 'forming', armed: 'armed', near: 'near', triggered: 'triggered' },
  bull_flag: { forming: 'poles', armed: 'flags', near: 'near', triggered: 'broke out' },
  flat_top_breakout: { forming: 'pushing HOD', armed: 'bases', near: 'near', triggered: 'held' },
  flat_top_5m: { forming: 'pushing HOD', armed: '5m bases', near: 'near', triggered: 'held' },
  red_to_green: { forming: 'red', armed: 'armed', near: 'near', triggered: 'reclaimed' },
  gap_and_go: { forming: 'held back', armed: 'under the PMH', near: 'near', triggered: 'broke out' },
  ...SHORT_FUNNEL_WORDS,
};
export const SETUP_FUNNEL_TIPS = {
  watching: 'Symbols this scanner follows right now: the HOD Momo names.',
  forming: 'Symbols forming the pattern right now (a leg, a pole, a push into the high, or red under the open), before it arms.',
  armed: 'Setups armed today: the pattern was in place with a trigger and a stop.',
  near: 'Armed setups that came within a few cents of the trigger today — the tape was read at each.',
  triggered: 'Armed setups that traded over the trigger today.',
  failed: 'Armed setups that broke a rule today before they triggered.',
  proposed: 'Setups that raised a proposal today (near + GO while this setup was at Eyes or above).',
  filtered: 'Setups the template\'s stock filter kept out today.',
} as const;

/** The card's status line: what the scanner is doing right now. */
export const SETUP_WINDOW_WORDS = {
  before: (start: string) => `opens ${start}`,
  open: (start: string, end: string) => `window ${start}–${end}`,
  after: (end: string) => `window closed ${end}`,
} as const;
export const SETUP_WINDOW_TIP =
  'The arming window: no setup arms before it opens, and none arms or triggers after it closes. The bot\'s own trade window can be narrower (its template\'s Bot entries).';
export const SETUP_STATUS_TIPS = {
  watching: 'The scanner follows these names on one-minute bars, on every template of this setup at once.',
  seeding: 'Symbols still loading today\'s one-minute bars: the scanner cannot judge them until they arrive.',
  disconnected: 'The setup scanner is not connected, so this card cannot show what it sees.',
  idle: 'Nothing is forming right now. Rows show up here as soon as a name starts the pattern.',
} as const;
export const SETUP_OPEN_BOARD = 'Open board ↗';
export const SETUP_OPEN_BOARD_TIP = 'Watchlist › Setups, filtered to this setup: every row with its levels, pillars and catalyst.';

/* ---------- The Setups board's filter (Watchlist › Setups) ---------- */
export const SETUPS_FILTER_ALL = 'All';
export const SETUPS_FILTER_TIP = (label: string, n: number): string =>
  `${label}: ${n} row${n === 1 ? '' : 's'} on the board now (forming, armed, near, triggered in the last 30 min, failed in the last 5).`;
export const SETUPS_NO_SCANNER_CHIP = (label: string, why: string): string => `${label}: ${why}`;

/** Why Stage ticket is locked (ux/whyTip.ts): the proposal carries no entry price. */
export const SETUPS_STAGE_NO_ENTRY_WHY = 'This proposal has no entry price -- there is nothing to stage';
/** Why Stage ticket is locked: no stop, so no risk a share to size from. */
export const SETUPS_STAGE_NO_STOP_WHY = 'This proposal has no stop, so no risk a share to size from -- there is nothing to stage';

/** Risk per trade is the venue sleeve's `caps.risk_usd` (ADR 042 draft): read from the bot session, saved
 * with `PATCH {caps: {venue, risk_usd}}`, re-read this often while a live Trader tab or an alert shows it.
 * It sizes the Trader plan's Stage and Approve and every proposal's Stage. */
export const SLEEVE_SESSION_PATH = '/api/bot/session';
export const SLEEVE_POLL_MS = 15_000;
/** The desk's old local risk per trade (`{schema_version: 1, value}`): moved into the desk venue's sleeve
 * once, then deleted. Read and written only on a backend that keeps no risk in the sleeve. */
export const SLEEVE_RISK_LEGACY_KEY = 'nova.stockRead.riskUsd';
export const SLEEVE_RISK_DEFAULT_USD = 20;
export const SLEEVE_RISK_MAX_USD = 10_000;

/** One dismissed list for the alert card and the Bots inbox (ADR 042 draft): `sessionStorage`
 * `{schema_version: 1, ids: string[]}`, newest last. */
export const PROPOSAL_DISMISSED_KEY = 'nova.setups.dismissed';
export const PROPOSAL_DISMISSED_MAX = 200;

/** A proposal Nova itself will take (spec H): what its card says, and why its Stage is locked. */
export const PROPOSAL_TAKEN_LINE: Record<'bot' | 'auto_entry', string> = {
  bot: 'The bot is taking this — nothing to do.',
  auto_entry: 'Auto-entry is taking this — nothing to do.',
};
export const PROPOSAL_TAKEN_LOCK: Record<'bot' | 'auto_entry', string> = {
  bot: 'The bot is taking this trade: a buy of your own would double it.',
  auto_entry: 'Auto-entry is buying this for you: a buy of your own would double it.',
};
/** A proposal that is not a trade is still shown, and blocks every buy: Nova's and your Stage. */
export const PROPOSAL_NOT_A_TRADE_NOVA = 'Nova does not buy it either: not the bot, not Auto-entry, not Approve.';

/** What each level of a setup does under the Bots page's master level (ADR 042 draft). */
export const SETUPS_LEVEL_WORDS = 'Each setup has its own level, under the Bots page\'s master level. Off watches and '
  + 'scores in silence. Eyes proposes when a setup is near its trigger and the tape says go. Strategy also lets Nova '
  + 'buy its go triggers on Paper and Sim while the bot is Active: the bot on the stocks set to Bot, Auto-entry on the '
  + 'stocks set to Auto-entry. Everywhere else it proposes, as at Eyes. Nova never buys by itself on Live.';

export const TAPE_VERDICT_LABELS: Record<string, string> = {
  go: 'Tape: go',
  wait: 'Tape: wait',
  veto: 'Tape: no',
  blind: 'Tape: blind',
};

export const TAPE_VERDICT_TITLES: Record<string, string> = {
  go: 'Green on the tape and no seller holding the level. The bot would take this.',
  wait: 'Not yet: a seller at the level that is not thinning, a burst of red, or no green on the tape.',
  veto: 'No: spread too wide, a 100k+ seller at the level, or a hidden seller soaking up the buying.',
  blind: 'Nova holds no Level 2 line for this symbol. Open it in the Trader so the bot can read the tape.',
};

/* Catalyst labels (CATALYST_CATEGORY_LABELS / _SHORT / CATALYST_VERDICT_TITLES) live in constantGroups/catalysts.ts. */

/** Scoreboard splits, in the order they answer the question: does the tape
 * gate turn the bar shape into a winning trade? */
export const SETUPS_SPLIT_TITLES: Record<string, string> = {
  tape_at_trigger: 'Tape at the trigger',
  grade: 'Grade when armed',
  session: 'Session',
  kind: 'Setup',
};

export const SETUPS_SPLIT_KEY_LABELS: Record<string, Record<string, string>> = {
  tape_at_trigger: {
    go: 'Tape said go',
    wait: 'Tape said wait',
    veto: 'Tape said no',
    blind: 'No Level 2 line',
    none: 'Never triggered',
  },
  grade: { A: 'Grade A', B: 'Grade B', C: 'Grade C', '?': 'No grade' },
  session: { premarket: 'Premarket (before 9:30)', regular: 'Regular hours', unknown: 'Unknown' },
  kind: {
    first_pullback: 'First pullback', second_pullback: 'Second pullback', bull_flag: 'First flag',
    second_bull_flag: 'Second flag', flat_top_breakout: 'First flat top', second_flat_top_breakout: 'Second flat top',
    red_to_green: 'Red to green', ...SHORT_KIND_LABELS, '?': 'Unknown',
  },
};

export const SETUPS_DAYS_LABELS: Record<number, string> = { 1: 'Today', 5: '5 days', 20: '20 days', 0: 'All' };
