/** The daily loss limit's words (ADR 056): the Settings page, its hover tips and the desk's notices. */

export const LOSS_LIMIT_NAV_LABEL = 'Loss limits';
export const LOSS_LIMIT_API_PATH = '/api/loss-limit';
export const LOSS_LIMIT_POLL_MS = 3000;
/** A warning or trip older than this is not announced (the Settings page and the Orders table still say it). */
export const LOSS_LIMIT_NOTICE_MAX_AGE_SEC = 600;

export const LOSS_LIMIT_DAILY_LABEL = 'Daily loss limit';
export const LOSS_LIMIT_WARN_LABEL = 'Warn me';
export const LOSS_LIMIT_NO_NEW_BUYS_LABEL = 'No new buys';
export const LOSS_LIMIT_AUTO_SELL_LABEL = 'Auto sell';
export const LOSS_LIMIT_AUTO_SELL_NOTE = "sell what's held";

export const LOSS_LIMIT_DAILY_TIP =
  "Counts only trades opened today, yours and the bots': what was lost on the ones closed, what the open ones " +
  'are down right now, and commissions. Anything held before today never counts. It has to stay past the limit ' +
  'for 10 seconds. Starts over at 04:00 ET. Live, Paper and Sim are each counted on their own.';
export const LOSS_LIMIT_WARN_TIP = 'A voice line and a notice at 80% of the limit.';
export const LOSS_LIMIT_NO_NEW_BUYS_TIP =
  "At the limit, buys are refused until 04:00 ET, yours and the bots'. Selling, Flatten and KILL still work. " +
  'Raise the limit or uncheck this to buy again.';
export const LOSS_LIMIT_AUTO_SELL_TIP =
  "At the limit, Nova sells every position opened today, at market, yours and the bots'. Positions from " +
  'before today are never sold.';

export const LOSS_LIMIT_BUSY_READING = 'Reading the loss limit…';
export const LOSS_LIMIT_BUSY_SAVING = 'Saving the loss limit…';
export const LOSS_LIMIT_SAVE_FAILED = 'The loss limit was not saved';
export const LOSS_LIMIT_READ_FAILED = 'Nova could not read the loss limit';
export const LOSS_LIMIT_WHOLE_DOLLARS = 'Whole dollars, $10 to $1,000,000';
