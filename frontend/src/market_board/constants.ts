/** The Market page's numbers and words (ADR 053). Periods and kinds mirror backend/constants_market_board.py. */
import type { Period, TopKind } from './types';

export const MARKET_SCHEMA_VERSION = 1;
export const MARKET_BOARD_PATH = '/api/market/board';
/** The page asks this often while it shows; the backend keeps each read on its own cadence. */
export const MARKET_POLL_MS = 5_000;
/** While a read has not answered yet, ask again sooner. */
export const MARKET_LOADING_POLL_MS = 2_000;
/** Answers the page keeps in memory (one per switch combination) to open on at once when it shows again. */
export const MARKET_KEPT_BOARDS = 12;

export const MARKET_PERIODS: readonly Period[] = ['1D', '7D', '30D'];
export const MARKET_TOP_KINDS: readonly TopKind[] = ['movers', 'biggest', 'runners'];
export const PERIOD_LABEL: Record<Period, string> = { '1D': '1 D', '7D': '7 D', '30D': '30 D' };
export const TOP_KIND_LABEL: Record<TopKind, string> = {
  movers: 'Movers',
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
export const RUNNERS_NOT_RECORDED = 'not recorded -- Nova holds no Gainers board for this session';

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
  'Gappers: 60% or more of 20%+ gappers holding their open green, 40% or less red.';
