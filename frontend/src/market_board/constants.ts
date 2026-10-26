/** The Market page's numbers and words (ADR 053). Periods and kinds mirror backend/constants_market_board.py. */
import type { Period, TempLabel, TopKind } from './types';

export const MARKET_SCHEMA_VERSION = 1;
export const MARKET_BOARD_PATH = '/api/market/board';
/** The page asks this often while it shows; the backend keeps each read on its own cadence. */
export const MARKET_POLL_MS = 5_000;
/** While a read has not answered yet, ask again sooner. */
export const MARKET_LOADING_POLL_MS = 2_000;
/** Answers the page keeps in memory (one per switch combination) to open on at once when it shows again. */
export const MARKET_KEPT_BOARDS = 12;

export const MARKET_PERIODS: readonly Period[] = ['1D', '7D', '30D'];
/** Movers retired (operator, 2026-10-14): its sector cards often held one stock. */
export const MARKET_TOP_KINDS: readonly TopKind[] = ['biggest', 'runners'];
export const PERIOD_LABEL: Record<Period, string> = { '1D': '1 D', '7D': '7 D', '30D': '30 D' };
export const TOP_KIND_LABEL: Record<TopKind, string> = {
  biggest: 'Biggest names',
  runners: 'Small-cap runners',
};

/** Persisted per-block switches (owner periods.ts). */
export const MARKET_PERIODS_STORAGE_KEY = 'nova.marketBoard.periods.v1';
export const MARKET_PERIODS_SCHEMA_VERSION = 1;

/** The sector board's bar runs from -scale to +scale percent: one scale per period. */
export const BAR_SCALE_PCT: Record<Period, number> = { '1D': 3, '7D': 8, '30D': 15 };
/** The theme colours of the small-cap climate, in the order themes are first seen; the rest are grey. */
export const THEME_COLORS = ['#30d158', '#64d2ff', '#bf5af2', '#ff9f0a', '#5e5ce6', '#ff375f', '#ffd60a'];
export const THEME_OTHER_COLOR = '#8e8e93';
/** The climate bar shows this many themes by name, then "Other". */
export const THEME_BAR_MAX = 5;
/** The runners chart's hover card lists this many themes, then "+ N more". */
export const RUNNERS_TIP_THEMES = 8;
export const RUNNERS_NOT_RECORDED = 'not recorded -- Nova holds no Gainers board, and Massive has not built this session';
/** A session Nova did not record, filled from the Massive day movers index (operator ask 2026-10-14). */
export const RUNNERS_SOURCE_MASSIVE = 'massive';
export const RUNNERS_FROM_MASSIVE =
  "from Massive's minute bars -- Nova did not record this session. Every listed stock, not the Gainers board's top 50, " +
  "so it can run higher; not in the card's counts or averages";

export const MARKET_TITLE = 'Market';
export const MARKET_OFF = 'The Market page is turned off on this desk (NOVA_MARKET_BOARD=0).';
export const MARKET_OLD_API = "This desk's backend has no Market page yet -- restart it after the update.";
export const MARKET_REPLAY_NOTE = "Today's live market (the Sim replay is not followed here)";
export const VERDICT_WORD: Record<'bullish' | 'mixed' | 'bearish', string> = {
  bullish: 'BULLISH',
  mixed: 'MIXED',
  bearish: 'BEARISH',
};
export const DAY_READ_RULE =
  'Six checks, each green, amber or red by a fixed rule. Bullish when green outnumbers red by 3 or more, ' +
  'bearish when red outnumbers green by 3 or more, mixed otherwise; no verdict until 3 checks have data. ' +
  'Futures: 3 of ES, NQ, RTY, YM up is green, 3 down is red. Breadth: NYSE advancing over declining at 1.5 ' +
  'or more is green, 1/1.5 or less red. VIX: down 3% or more green, up 3% red. Small caps: RTY minus ES +0.25 ' +
  'points or more green, -0.25 red. Runners: 20%+ runners at 1.25x their same-minute average green, 0.8x red. ' +
  'Gappers: 60% or more of 20%+ gappers holding their open green, 40% or less red. ' +
  'The small-caps line is the Small-cap climate card\'s temperature: a separate question, never one of the checks.';

/** The small-cap temperature's words and rules (ADR 053 amendment 2026-10-25; backend market_board/temperature.py). */
export const TEMP_WORD: Record<TempLabel, string> = {
  hot: 'HOT', warm: 'WARM', cold: 'COLD', good: 'GOOD', ok: 'OK', choppy: 'CHOPPY',
};
export const TEMP_RULE: Record<Period, string> = {
  '1D': 'Stocks with a prior close of $2-20 on Nova\'s Gainers board. Hot: 2 or more up 100%, and more money in the ' +
    'top 5 gainers than usual (the median of the sessions before, at this time of day). Cold: none up 100% and no ' +
    'more money than usual. Warm: the rest. Money is shares traded x last price.',
  '7D': 'The last 5 sessions. Cold: 3 or more cold days. Good: 2 or more hot days, and runners that peaked at +50% ' +
    'kept half their gain 45% of the time or more. Choppy: they kept it under 35% of the time. OK: the rest.',
  '30D': 'The last 21 sessions: hot days minus cold days, over the days with a label. +15% or more is hot, -15% or ' +
    'less cold, warm in between.',
};
