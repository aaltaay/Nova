/**
 * The Trader ticket's short side (ADR 048, #778 step 3): the words a position-aware ticket says, the
 * SHORT CHECK box, and the colour a short wears. A short is orange and always carries the word SHORT
 * (VWAP and the Paper chip are orange too, so the colour alone never says it).
 */

export const SHORT_TICKET_LABEL_COVER = 'Cover';
export const SHORT_TICKET_LABEL_SHORT_MORE = 'Short more';
export const SHORT_TICKET_BUY_STOP_LABEL = 'Buy stop';
export const SHORT_TICKET_REQUIRED = 'Required';

export const SHORT_WHY_FLAT_SELL = (sym: string): string =>
  `You hold no ${sym} to sell. Selling shares you do not own is a short: use Short, which goes out with its buy stop.`;
export const SHORT_WHY_LONG = (sym: string): string =>
  `You're long ${sym}: Nova never flips. Sell what you hold first; a short opens only from flat.`;
export const SHORT_WHY_SHORT_SELL = (sym: string): string =>
  `You're short ${sym}: a sell would add to the short without its buy stop. Use Short more, which carries its own.`;
export const SHORT_WHY_TYPE =
  'A short goes out as a Limit with its buy stop: Market has no price for SSR, the margin or the cushion (ADR 048).';

export const SHORT_NOTE_OPEN = (qty: string, sym: string): string =>
  `A short sale: you sell ${qty} ${sym} you do not own, borrowed through IBKR, and buy them back to cover. Day only.`;
export const SHORT_NOTE_MORE = (held: string, sym: string): string =>
  `You are short ${held} ${sym}: this adds to it with its own buy stop. Day only: Nova covers what is left before the close.`;
export const SHORT_NOTE_COVER = (held: string): string =>
  `You are short ${held}. Cover buys them back, never past flat: Nova never flips a short into a long.`;

export const SHORT_STOP_NOTE_OVER = (risk: string): string => `over the limit · -$${risk} at the stop`;
export const SHORT_STOP_WHY_MISSING = 'Every short goes out with a buy stop over its limit: set the Buy stop.';
export const SHORT_STOP_WHY_UNDER = (limit: string): string =>
  `A buy stop protects a short from above: set it over the ${limit} limit.`;

export const SHORT_LEGS_NOTE = (target: string): string => `Bracket: cover target $${target} · stop: your Buy stop`;
export const SHORT_TICKET_FLATTEN_COVER = (shares: string): string => `Cover ${shares} (flatten)`;

export const SHORT_LIMIT_NOTE_SSR = 'SSR: priced at the ask, over the bid';
export const SHORT_LIMIT_NOTE_SSR_UNKNOWN = 'SSR not known yet: priced at the ask, over the bid';

export const SHORT_COST_LABEL = 'Short';
export const SHORT_MARGIN_LABEL = 'Margin';
export const SHORT_COST_NOTE =
  "A short's value at its limit. What it holds of the account is its margin requirement, from the short check " +
  "(IBKR's what-if for the stock, else the published rules), not buying power less the value.";

export const SHORT_CHECK_TITLE = 'Short check';
export const SHORT_CHECK_SUB = 'Nova checks each before it sends';
export const SHORT_CHECK_ALL_PASS = 'all pass';
export const SHORT_CHECK_LOADING = 'Asking Nova…';
export const SHORT_CHECK_UNAVAILABLE =
  'This backend has no short check (an API from before ADR 048): the door still checks every short when you send it.';
export const SHORT_CHECK_FAILED = (why: string): string =>
  `The short check could not be read (${why}): the door still checks every short when you send it.`;

/** The submit button's orange (a short) and green (a cover). */
export const SHORT_TICKET_COLOR = '#f97316';
