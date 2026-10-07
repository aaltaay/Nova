/**
 * The five short setups' words on the desk (ADR 049): names, kinds, the ladder's states in each setup's own terms,
 * the tape gate's mirror, the five-year test and the short grade. The backend owns the rules
 * (`backend/setup_scanner/`, `backend/setup_templates/params_short.py`); these only say them, and the numbers in
 * them are the defaults the operator decided (a template may vary them). A short is drawn orange and always
 * carries the word SHORT: VWAP and the Paper chip are orange too, so the colour never speaks alone.
 */

/** Mirrors backend constants_bot.BOT_SHORT_SETUPS, in its order. */
export const SHORT_SETUP_IDS = ['backside_lower_high', 'bear_flag', 'failed_breakout', 'lost_vwap', 'ssr_bounce'] as const;
const SHORT_SET: ReadonlySet<string> = new Set(SHORT_SETUP_IDS);

/** A short setup sells borrowed shares at its entry and covers under it (ADR 049); every other setup is long. */
export function isShortSetup(setup: string | null | undefined): boolean {
  return setup != null && SHORT_SET.has(setup);
}

/** The side of a row, lane, proposal or episode: the wire's own word, else its setup's. */
export function setupSideOf(x: { side?: string | null; setup_type?: string | null } | null | undefined): 'long' | 'short' {
  if (x?.side === 'short' || x?.side === 'long') return x.side;
  return isShortSetup(x?.setup_type) ? 'short' : 'long';
}

/** The side tag beside a setup's name: green ▲ LONG, orange ▼ SHORT. */
export const SETUP_SIDE_TAG = { long: '▲ LONG', short: '▼ SHORT' } as const;
export const SETUP_SIDE_TAG_TIPS = {
  long: 'A long setup: it buys at its entry, with its stop under it, and sells over it. At On, while the Bot is on, '
    + 'Nova\'s bot buys its GO triggers on Paper and Sim.',
  short: 'A short setup: it sells borrowed shares at its entry, with a buy stop over it, and covers (buys them back) '
    + 'under it. At On, while the Bot is on, Nova\'s bot shorts its GO triggers on Paper and Sim: the buy stop goes in '
    + 'with the entry, and Nova covers what is left at 15:55.',
} as const;

/** The canvas's oranges (a chart cannot read the CSS tokens): the stroke, the lead's fill and a faded fill. */
export const SHORT_SETUP_COLORS = {
  stroke: '#f97316',
  fill: 'rgba(249, 115, 22, 0.14)',
  legFill: 'rgba(249, 115, 22, 0.08)',
  legStroke: 'rgba(249, 115, 22, 0.55)',
} as const;

export const SHORT_SETUP_LABELS: Record<string, string> = {
  backside_lower_high: 'Backside lower high',
  bear_flag: 'Bear flag',
  failed_breakout: 'Failed breakout',
  lost_vwap: 'Lost VWAP',
  ssr_bounce: 'SSR bounce short',
};

/** The name as a tag beside a symbol (the Symbols card, the inbox, the Setups board). */
export const SHORT_SETUP_TAGS: Record<string, string> = {
  backside_lower_high: 'Backside',
  bear_flag: 'Bear flag',
  failed_breakout: 'Failed breakout',
  lost_vwap: 'Lost VWAP',
  ssr_bounce: 'SSR bounce',
};

/** The chart legend's chip names. */
export const SHORT_SETUP_CHIPS: Record<string, string> = {
  backside_lower_high: '▼ Backside', bear_flag: '▼ Bear flag', failed_breakout: '▼ Failed BO', lost_vwap: '▼ Lost VWAP',
  ssr_bounce: '▼ SSR bounce',
};

/** One line on what each short setup trades. */
export const SHORT_SETUP_BLURBS: Record<string, string> = {
  backside_lower_high: 'A fade of 8%+ off the high of day, then a 1-3 candle bounce that stays under it — shorted 1c '
    + 'under the bounce, with a buy stop over it.',
  bear_flag: 'A pole of 3+ red candles down 5%+, then a 2-3 candle flag drifting up — shorted 1c under the flag, with '
    + 'a buy stop over it.',
  failed_breakout: 'A flat top tested 2+ times, a poke over it, then a close back under it within 2 candles — shorted '
    + '1c under that candle, with a buy stop over the poke.',
  lost_vwap: 'Over VWAP from the open, a close under it, then a retest that fails at VWAP — shorted 1c under the '
    + 'retest, with a buy stop over VWAP.',
  ssr_bounce: 'Under SSR and VWAP, a drop of 6%+ to the day\'s low, then a bounce: the short rests 1c under the level '
    + 'it runs into, so a buyer lifts it above the bid, as SSR requires.',
};

/** Where a short's research stands: its five-year test decides its On (ADR 049 section 12). */
export const SHORT_SETUP_RESEARCH: Record<string, { verdict: 'testing'; text: string; detail: string }> = Object
  .fromEntries(SHORT_SETUP_IDS.map(id => [id, {
    verdict: 'testing' as const,
    text: 'Never traded on bars before: its five-year test on the desk\'s minute files decides whether it may be On '
      + '(ADR 049). Its Test line says where that stands.',
    detail: 'its five-year test decides whether it may be On',
  }]));

export const SHORT_KIND_LABELS: Record<string, string> = {
  backside_lower_high: 'Backside lower high', second_backside_lower_high: 'Second backside lower high',
  bear_flag: 'Bear flag', second_bear_flag: 'Second bear flag',
  failed_breakout: 'Failed breakout', second_failed_breakout: 'Second failed breakout',
  lost_vwap: 'Lost VWAP',
  ssr_bounce: 'SSR bounce short', second_ssr_bounce: 'Second SSR bounce short',
};

/** What a short's trigger is, where "the trigger" would say less. */
export const SHORT_TRIGGER_LEVEL_WORDS: Record<string, string> = {
  backside_lower_high: 'bounce low', bear_flag: 'flag low', failed_breakout: 'breakdown', lost_vwap: 'retest low',
  ssr_bounce: 'level',
};

/** A state's chip text per short setup. */
export const SHORT_TYPE_STATE_LABELS: Record<string, Partial<Record<string, string>>> = {
  backside_lower_high: { leg: 'Fading', pullback: 'Bounce · held back', armed: 'Bounce', near: 'Near the break',
    triggered: 'Broke down' },
  bear_flag: { leg: 'Pole down', pullback: 'Flag · held back', armed: 'Flag', triggered: 'Broke the flag' },
  failed_breakout: { leg: 'Poked over', pullback: 'Failed · held back', armed: 'Failed back under', triggered: 'Broke down' },
  lost_vwap: { leg: 'Lost VWAP', armed: 'Failed at VWAP', triggered: 'Broke down' },
  ssr_bounce: { leg: 'Bouncing', armed: 'Resting', near: 'Near the level', triggered: 'Filled' },
};

const NEAR_SHORT = 'Price is a few cents over the trigger. The tape is read now: GO at the level (red prints at the '
  + 'bid, no buyer holding it) is what makes a proposal.';
const TRIGGERED_SHORT = 'Price traded under the trigger. The scoreboard follows it from here with the short\'s exits: '
  + 'its cover at 2R first, its buy stop first, or still open.';

/** What each state means for each short setup: the first paragraph of its hover. */
export const SHORT_TYPE_STATE_TIPS: Record<string, Partial<Record<string, string>>> = {
  backside_lower_high: {
    leg: 'A fresh fade: a new low 8% or more off the high of day. The scanner waits for the bounce: one to three '
      + 'candles that stay under the high of day, take back less than half the fade and close under the 9 EMA.',
    pullback: 'A bounce is there, but one rule holds it back (MACD over zero, a risk outside the band, or the time of '
      + 'day). It arms as soon as the rule clears.',
    armed: 'The bounce is in place: a lower high. The trigger is the last bounce candle\'s low; the buy stop sits 1c '
      + 'over the bounce. Waiting for price to come back down.',
    near: NEAR_SHORT,
    triggered: TRIGGERED_SHORT,
    failed: 'The bounce broke a rule: it reached the high of day, took back half the fade, closed over the 9 EMA, '
      + 'or ran past three candles.',
  },
  bear_flag: {
    leg: 'A pole: red candles in a row, down 5% or more. The scanner waits for the flag: two or three candles drifting '
      + 'up on lighter volume that stay under the 9 EMA and take back no more than half the pole.',
    pullback: 'A flag is there, but one rule holds it back (MACD over zero, a risk outside the band, or the time of day).',
    armed: 'The flag is in. The trigger is the last flag candle\'s low; the buy stop sits 1c over the flag.',
    near: NEAR_SHORT,
    triggered: TRIGGERED_SHORT,
    failed: 'The flag broke a rule: too many candles, too deep, heavy volume on the way up, a close over the 9 EMA, or '
      + 'the day\'s highest-volume candle was green.',
  },
  failed_breakout: {
    leg: 'A flat top (the high of day, tested twice or more) and a poke over it. The scanner waits for a close back '
      + 'under the flat top within two candles: the breakout failed.',
    pullback: 'The breakout failed, but one rule holds the short back (a risk outside the band, or the time of day).',
    armed: 'Failed back under the flat top. The trigger is that candle\'s low; the buy stop sits 1c over the poke. It '
      + 'must break down within three candles.',
    near: NEAR_SHORT,
    triggered: TRIGGERED_SHORT,
    failed: 'No breakdown within three candles, a close back over the flat top, or a new high over the poke.',
  },
  lost_vwap: {
    leg: 'Over VWAP from the open, then a close under it. The scanner waits for a retest that fails at VWAP.',
    armed: 'The retest failed at VWAP. The trigger is the retest\'s low; the buy stop sits over VWAP. One try a day.',
    near: NEAR_SHORT,
    triggered: TRIGGERED_SHORT,
    failed: 'A close back over VWAP, the window closed, or the day\'s one try was spent.',
  },
  ssr_bounce: {
    leg: 'Under SSR and under VWAP: a drop of 6% or more to the day\'s low, then two green candles off it. The scanner '
      + 'finds the level over the price (the break, a half or whole dollar, the last lower high, or VWAP) and arms '
      + 'when the bounce comes within 2% of it.',
    armed: 'The short rests 1c under the level, so a buyer pushing into it fills it above the bid, as SSR requires. Its '
      + 'buy stop is 2% over the entry (at least 5c). It is cancelled after 10 minutes, on a new low, or on a close '
      + 'over the level.',
    near: 'Price is a few cents under the resting short. A buyer lifting the offer into it fills it.',
    triggered: 'A buyer lifted the resting short: it filled at its entry. The scoreboard follows it from here.',
    failed: 'Cancelled: ten minutes without a fill, a new low first, or a candle closed over the level.',
  },
};

/** The funnel's words per short setup: forming, armed, near, triggered. */
export const SHORT_FUNNEL_WORDS: Record<string, { forming: string; armed: string; near: string; triggered: string }> = {
  backside_lower_high: { forming: 'fading', armed: 'bounces', near: 'near', triggered: 'broke down' },
  bear_flag: { forming: 'poles', armed: 'flags', near: 'near', triggered: 'broke down' },
  failed_breakout: { forming: 'poked over', armed: 'failed back', near: 'near', triggered: 'broke down' },
  lost_vwap: { forming: 'lost VWAP', armed: 'failed retests', near: 'near', triggered: 'broke down' },
  ssr_bounce: { forming: 'bouncing', armed: 'resting', near: 'near', triggered: 'filled' },
};

/** The tape verdicts' hover heads for a short (the reasons and numbers follow). */
export const SHORT_TAPE_VERDICT_TIPS: Record<string, string> = {
  go: 'GO: red prints at the bid and no buyer holding the level. At Eyes it proposes the short; at On, while the Bot '
    + 'is on, Nova\'s bot shorts it on Paper and Sim.',
  wait: 'WAIT: not yet. A buyer at the level that is not thinning, a burst of buying on the tape, or no red prints yet.',
  veto: 'VETO: no. The spread is too wide, a very big buyer sits at the level, or a hidden buyer is soaking up the selling.',
  blind: 'BLIND: Nova holds no Level 2 line for this symbol, so the tape cannot be read. Open its Level 2 in the Trader '
    + 'to read it.',
};
export const SHORT_TAPE_VERDICT_TITLES: Record<string, string> = {
  go: 'Red on the tape and no buyer holding the level.',
  wait: 'Not yet: a buyer at the level that is not thinning, a burst of green, or no red on the tape.',
  veto: 'No: spread too wide, a 100k+ buyer at the level, or a hidden buyer soaking up the selling.',
  blind: 'Nova holds no Level 2 line for this symbol. Open it in the Trader so the tape can be read.',
};

/** The short grade's pillars (ADR 049 section 10), in the order the hover lists them. */
export const SHORT_PILLAR_WORDS: Record<string, string> = {
  run: 'Ran 30%+ today',
  fade: 'Faded 8%+ off the high',
  vwap: 'Under VWAP',
  bad_news: 'Dilution or bad news on file',
  borrow: 'Borrow at least 10x the order',
};
export const SHORT_GRADE_TIP = 'Grade: the short pillars (ran today, faded off the high, under VWAP, dilution or bad '
  + 'news, borrow). A = all five pass, B = four, C = three or fewer: not a trade. An unknown pillar counts as not '
  + 'passing, never as failed.';

/** The five-year test line on a short card (ADR 049 section 12). */
export const SHORT_TEST_LABEL = 'Test';
export const SHORT_TEST_STATE_WORDS: Record<string, string> = {
  queued: 'queued', running: 'running', passed: 'passed', failed: 'failed', error: 'error',
};
export const SHORT_TEST_TIP = 'The five-year test runs this setup\'s rules (its template in play) over five years of '
  + 'minute bars on the desk, with the scanner\'s own detector and exits, borrow assumed. It passes with at least 300 '
  + 'trades, still positive without its best year, a profit factor over 1 at twice the costs, a mostly positive '
  + 'neighbourhood and a permutation p of 0.05 or less. Until it passes on the rules in play, On stays locked: the '
  + 'setup stays at Eyes. Nobody writes a result by hand.';
export const SHORT_TEST_STALE_TIP = 'The result is for other rules: the template in play changed since, so it tests '
  + 'again.';

/** A short whose On is held at Eyes by its test (a result that failed, is missing or is for other rules). */
export const SHORT_SETUP_TEST_HELD_CHIP = 'On · held at Eyes until its test passes';
