/** Why it's moving (ADR 028). The backend owns the rules (`backend/move_reason/rules.py`, `constants_move_reason.py`). */

export const WHY_MOVING_PATH = '/api/why';
export const WHY_MOVING_POLL_MS = 60_000;
export const WHY_MOVING_TITLE = "Why it's moving";
export const WHY_MOVING_DEFAULT_EXPANDED = false;
export const WHY_MOVING_READING = 'Reading the move ...';
export const WHY_MOVING_RULES_NOTE =
  'A rules read of the facts below, not advice. Short interest is reported twice a month about two weeks late; borrow is IBKR\'s, every 15 minutes.';
export const WHY_MOVING_POSSIBLE_TITLE = 'A deciding fact is unknown (see the ? rows)';

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
};

/** A check's state as the row marks it. */
export const WHY_MOVING_STATE_MARKS: Record<string, string> = { yes: '●', no: '○', unknown: '?' };
export const WHY_MOVING_STATE_TITLES: Record<string, string> = {
  yes: 'Yes',
  no: 'No',
  unknown: 'Unknown -- no source holds this yet',
};
