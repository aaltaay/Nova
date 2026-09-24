/** Setup scanner UI (ADR 022). The backend owns the rules (`backend/constants_setups.py`). */

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
  filtered: "The pattern armed, but the template's stock filter keeps this name out. The reason says which rule.",
};

/** What a setup's trigger is, where "the trigger" would say less: the alert card and the watch toasts. */
export const SETUP_TRIGGER_LEVEL_WORDS: Record<string, string> = { red_to_green: 'open', flat_top_breakout: 'high' };

export const SETUP_KIND_LABELS: Record<string, string> = {
  first_pullback: 'First pullback',
  second_pullback: 'Second pullback',
  bull_flag: 'Bull flag',
  second_bull_flag: 'Second bull flag',
  flat_top_breakout: 'Flat-top breakout',
  second_flat_top_breakout: 'Second flat-top',
  red_to_green: 'Red to green',
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
  red_to_green: { leg: 'Red', pullback: 'Red · held back', armed: 'Red', near: 'Near the open', triggered: 'Reclaimed' },
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
    leg: 'A new high of day on an impulse. The scanner waits for a base: two to six candles closing just under that high, none making a new one.',
    pullback: 'A base is there, but one rule holds it back (MACD under zero, a risk outside the band, or the time of day).',
    armed: 'A flat top: tight candles closing just under the high of day. The trigger is that high.',
    near: 'Price is a few cents under the high of day. The tape is read now.',
    triggered: 'The breakout held: a green candle closed over the high without trading back under it. The scoreboard follows it from here.',
    failed: 'The base broke: it ran too long, lost the 9 EMA, or price closed back under the high before a candle held it.',
  },
  red_to_green: {
    leg: 'Trading under the open. Red to green needs enough closes under the open before a move back through it counts as the reclaim.',
    pullback: 'Red, but not a try yet: MACD under zero, or the risk from the low is outside the band (a reclaim now would spend the day\'s one try).',
    armed: 'Red under the open with the rules met. The trigger is the open itself; the stop is the lowest low since the open. One try a day.',
    near: 'Price is a few cents under the open. The tape is read now: GO at the level is what makes a proposal.',
    triggered: 'Price traded back over the open: red to green. The scoreboard follows it from here. That was the day\'s one try.',
    failed: 'The reclaim window closed, or the try was spent.',
  },
};

/** A setup's flat-top hold after the break (detail.broke_at). */
export const SETUP_FT_BROKE_LABEL = 'Broke · wants a hold';
export const SETUP_FT_BROKE_TIP = (level: string, at: string, n: number): string =>
  `Broke the ${level} high at ${at} ET. Now the first of the next ${n} candles that holds over it (its low at or over ${level}) and closes green is the entry — at its close +1c, stop its low. A close back under ${level} fails the setup.`;

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
  'Grade: the Five Pillars when the setup armed. A = all five pass, B = four, C = three or fewer. An unknown pillar counts as not passing, never as failed.';
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
};

/** The funnel's words per setup: forming, armed, near, triggered, failed, proposed (ADR 031). */
export const SETUP_FUNNEL_WORDS: Record<string, { forming: string; armed: string; near: string; triggered: string }> = {
  first_pullback: { forming: 'forming', armed: 'armed', near: 'near', triggered: 'triggered' },
  bull_flag: { forming: 'poles', armed: 'flags', near: 'near', triggered: 'broke out' },
  flat_top_breakout: { forming: 'pushing HOD', armed: 'bases', near: 'near', triggered: 'held' },
  red_to_green: { forming: 'red', armed: 'armed', near: 'near', triggered: 'reclaimed' },
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
    red_to_green: 'Red to green', '?': 'Unknown',
  },
};

export const SETUPS_DAYS_LABELS: Record<number, string> = { 1: 'Today', 5: '5 days', 20: '20 days', 0: 'All' };
