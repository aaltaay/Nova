/** Why it's moving (ADR 028). The backend owns the rules (`backend/move_reason/rules.py`, `constants_move_reason.py`). */

export const WHY_MOVING_PATH = '/api/why';
export const WHY_MOVING_POLL_MS = 60_000;
/** On a Sim replay, read again once the playhead is this far (seconds of replay time) past the last read. */
export const WHY_MOVING_REPLAY_REFRESH_SEC = 60;
export const WHY_MOVING_TITLE = "Why it's moving";
export const WHY_MOVING_DEFAULT_EXPANDED = false;
export const WHY_MOVING_READING = 'Reading the move ...';
export const WHY_MOVING_RULES_NOTE =
  'A rules read of the facts below, not advice. Short interest is reported twice a month about two weeks late; borrow is IBKR\'s, every 15 minutes.';
export const WHY_MOVING_POSSIBLE_TITLE = 'A deciding fact is unknown (see the ? rows)';
/** A Sim replay's read: "Sim replay, read as of Oct 2 10:31 ET" then the suffix. */
export const WHY_MOVING_REPLAY_PREFIX = 'Sim replay, read as of';
export const WHY_MOVING_REPLAY_SUFFIX = '-- every fact is from then or before, never after.';

/** Likely causes (backend `MOVE_KIND_*`) by tone: a squeeze loud, news green, the rest quiet. */
export const WHY_MOVING_TONES: Record<string, string> = {
  news_pending: 'pending',
  news: 'news',
  short_squeeze: 'squeeze',
  split_squeeze: 'squeeze',
  low_float_momentum: 'momentum',
  routine_news: 'muted',
  thin_trading: 'muted',
  unexplained: 'muted',
  not_moving: 'muted',
  not_read: 'muted',
};

/** A check's state as the row marks it. */
export const WHY_MOVING_STATE_MARKS: Record<string, string> = { yes: '●', no: '○', unknown: '?' };
export const WHY_MOVING_STATE_TITLES: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
  unknown: 'Unknown -- no source holds this yet',
};

// -- The Catalyst column (was News): what is moving the stock, on every table (operator ask 2026-10-12) --------
export const CATALYST_COLUMN_LABEL = 'Catalyst';
export const CATALYST_COLUMN_TITLE =
  'Catalyst: what is moving it -- the news, or with no news the cause the rules read from the facts. Hover a cell for how.';
/** At most this many symbols per batch read (backend `MOVE_BATCH_MAX_SYMBOLS`). */
export const CATALYST_BATCH_MAX = 80;
/** Cells asking within this window share one batch request. */
export const CATALYST_BATCH_DEBOUNCE_MS = 60;
export const CATALYST_HOVER_OPEN_MS = 150;
/** The pointer may cross from the cell into the card in this long. */
export const CATALYST_HOVER_CLOSE_MS = 200;
export const CATALYST_HOVER_WIDTH_PX = 540;
export const CATALYST_HOVER_GAP_PX = 8;

/** The cell's word for each cause (news takes the catalyst class's word: CATALYST_CATEGORY_SHORT). */
export const CATALYST_CAUSE_WORDS: Record<string, string> = {
  news_pending: 'News due',
  short_squeeze: 'Squeeze',
  split_squeeze: 'Split squeeze',
  low_float_momentum: 'Low float',
  routine_news: 'Routine',
  thin_trading: 'Thin',
  unexplained: 'Unexplained',
  fund: 'Fund',
};
export const CATALYST_NEWS_WORD = 'News';
/** Company news the classifier could not place (the ring): "Headline", as the approved mockup words it. */
export const CATALYST_UNPLACED_CATEGORY = 'company_news';
export const CATALYST_UNPLACED_WORD = 'Headline';
export const CATALYST_READING = '…';
export const CATALYST_NONE = '—';
export const CATALYST_FAILED_PREFIX = 'Read failed';
export const CATALYST_DETAIL_NO_NEWS = 'no news';
export const CATALYST_DETAIL_NEWS_UNREAD = 'news not read yet';
export const CATALYST_DETAIL_NOTHING_TO_LEND = 'nothing to lend';
export const CATALYST_DETAIL_BORROW_TIGHT = 'borrow tight';
export const CATALYST_DETAIL_UNEXPLAINED = 'nothing on file explains it';
export const CATALYST_SQUEEZE_PIP_TITLE = 'The short-squeeze checks pass too';

// The hover card.
export const CATALYST_LADDER_TITLE = 'How Nova decided';
export const CATALYST_LADDER_NOTE = 'Each cause in this order; the first that fits is the call.';
export const CATALYST_ALSO_TRUE = 'Also true';
export const CATALYST_CHECKS_TITLE = 'The facts';
export const CATALYST_NEWS_TITLE = 'The news';
export const CATALYST_STEP_MARKS: Record<string, string> = { yes: '✓', no: '✗', unknown: '?' };
export const CATALYST_STEP_TITLES: Record<string, string> = {
  yes: 'Fits',
  no: 'Does not fit',
  unknown: 'Unknown -- a fact it needs is not on file',
};
/** "Read at $6.08 (+56.3%)" then how that price was chosen. */
export const CATALYST_PRICED_BY_WORDS: Record<string, string> = {
  board_row: 'this board row\'s price, as the board shows it',
  last_trade: 'the last trade',
  row: 'its board row (no trade on the line yet)',
  quote: 'the live quote (on no board)',
  replay: 'the Sim replay at the playhead',
};
export const CATALYST_BOARD_WORDS: Record<string, string> = {
  gappers: 'Gappers',
  gainers: 'Gainers',
  losers: 'Losers',
  afterhours: 'After Hours',
  large_cap: 'Large Cap',
};
