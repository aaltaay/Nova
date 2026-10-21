/** Your order size limit's words (ADR 064): Settings > Loss limits, beside the daily loss limit. */

export const ORDER_SIZE_LIMIT_API_PATH = '/api/order-size-limit';

export const ORDER_SIZE_LIMIT_TITLE = 'Order size limit';
export const ORDER_SIZE_LIMIT_MAX_SHARES_LABEL = 'Max shares';
export const ORDER_SIZE_LIMIT_MAX_RISK_LABEL = 'Max risk at stop';
export const ORDER_SIZE_LIMIT_EMPTY_NOTE = 'empty box = no limit';
export const ORDER_SIZE_LIMIT_VENUE_NAMES = { paper: 'Paper', sim: 'Sim' } as const;

export const ORDER_SIZE_LIMIT_TIP =
  'Your own orders on Paper and Sim that buy or open a short: the ticket, hotkeys and Approve. Each order is ' +
  'checked on its own when it is sent; one over a limit is refused and says why. Selling what you hold, covering ' +
  'a short, cancels, Flatten and KILL always work. The bots keep their own limits, and Live keeps its own share cap.';
export const ORDER_SIZE_LIMIT_MAX_SHARES_TIP = 'The most shares one order may buy or short.';
export const ORDER_SIZE_LIMIT_MAX_RISK_TIP =
  'The most one order may lose at its stop: shares x the distance from the entry to the stop. 300 shares with a ' +
  '15-cent stop is $45. While this is set, an order with no stop is refused, because its risk is unknown.';

export const ORDER_SIZE_LIMIT_WHOLE_SHARES = 'Whole shares, 1 to 1,000,000, or empty for no limit';
export const ORDER_SIZE_LIMIT_WHOLE_DOLLARS = 'Whole dollars, $1 to $1,000,000, or empty for no limit';
export const ORDER_SIZE_LIMIT_UNREADABLE_NOTE = 'Paper and Sim refuse your new orders until a box here is saved.';
export const ORDER_SIZE_LIMIT_BUSY_READING = 'Reading the order size limit…';
export const ORDER_SIZE_LIMIT_BUSY_SAVING = 'Saving the order size limit…';
export const ORDER_SIZE_LIMIT_SAVE_FAILED = 'The order size limit was not saved';
export const ORDER_SIZE_LIMIT_READ_FAILED = 'Nova could not read the order size limit';
