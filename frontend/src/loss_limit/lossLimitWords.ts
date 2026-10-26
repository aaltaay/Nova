/** The daily loss limit's words (ADR 056, ADR 061): the Settings page, its hover tips and the desk's notices. */

export const LOSS_LIMIT_NAV_LABEL = 'Loss limits';
export const LOSS_LIMIT_API_PATH = '/api/loss-limit';
export const LOSS_LIMIT_POLL_MS = 3000;
/** A warning or trip older than this is not announced (the Settings page and the Orders table still say it). */
export const LOSS_LIMIT_NOTICE_MAX_AGE_SEC = 600;
/** A trip whose Auto sell is still selling waits this long for the answer before it is said without it. */
export const LOSS_LIMIT_SELL_WAIT_SEC = 30;

export const LOSS_LIMIT_DAILY_LABEL = 'Daily loss limit';
export const LOSS_LIMIT_YOU_LABEL = 'Your trades';
export const LOSS_LIMIT_BOTS_LABEL = "Bots' trades";
/** A You or Bots box left empty: that side has no line of its own. */
export const LOSS_LIMIT_OFF_PLACEHOLDER = 'off';
export const LOSS_LIMIT_WARN_LABEL = 'Warn me';
export const LOSS_LIMIT_NO_NEW_BUYS_LABEL = 'No new buys';
export const LOSS_LIMIT_AUTO_SELL_LABEL = 'Auto sell';
export const LOSS_LIMIT_AUTO_SELL_NOTE = "sell what's held";

export const LOSS_LIMIT_DAILY_TIP =
  "The whole account. Counts only trades opened today, yours and the bots': what was lost on the ones closed, " +
  'what the open ones are down right now, and commissions. Anything held before today never counts. It has to ' +
  'stay past the limit for 10 seconds. Starts over at 04:00 ET. Live, Paper and Sim are each counted on their own.';
export const LOSS_LIMIT_YOU_TIP =
  'Only the trades you opened today, counted the same way. At this line, No new buys stops only your buys and ' +
  'Auto sell sells only your shares: the bots keep trading. A trade counts for whoever opened it. Empty: no line ' +
  'of your own.';
export const LOSS_LIMIT_BOTS_TIP =
  'Only the trades a bot opened today (the strategy bots, Auto-entry and the Live Trader bot). At this line, No ' +
  "new buys stops only the bots' entries and Auto sell sells only their shares: you keep trading, and a bot's own " +
  'exits always work. A trade counts for whoever opened it. Empty: no line for the bots.';
export const LOSS_LIMIT_WARN_TIP = 'A voice line and a notice at 80% of each line.';
export const LOSS_LIMIT_NO_NEW_BUYS_TIP =
  "At a line, new buys are refused until 04:00 ET: the daily loss limit stops yours and the bots', your trades' " +
  "line only yours, the bots' line only the bots'. Selling, Flatten and KILL still work. Raise the limit or " +
  'uncheck this to buy again.';
export const LOSS_LIMIT_AUTO_SELL_TIP =
  'At a line, Nova sells what that line opened today, at market: the daily loss limit every position, your ' +
  "trades' line your shares, the bots' line theirs. Positions from before today are never sold.";

export const LOSS_LIMIT_BUSY_READING = 'Reading the loss limit…';
export const LOSS_LIMIT_BUSY_SAVING = 'Saving the loss limit…';
export const LOSS_LIMIT_SAVE_FAILED = 'The loss limit was not saved';
export const LOSS_LIMIT_READ_FAILED = 'Nova could not read the loss limit';
export const LOSS_LIMIT_WHOLE_DOLLARS = 'Whole dollars, $10 to $1,000,000';
export const LOSS_LIMIT_WHOLE_DOLLARS_OR_OFF = 'Whole dollars, $10 to $1,000,000, or empty for no line';
