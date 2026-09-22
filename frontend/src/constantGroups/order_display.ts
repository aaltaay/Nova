/**
 * Order-table display tunables (QA batch: orders / account / safety, 2026-09-22).
 */

/**
 * Above this a price cell shows "—". IB leaves an unused lmtPrice / auxPrice at
 * UNSET_DOUBLE (1.7976931348623157e308) until the first openOrder -- forever if
 * the order is rejected first -- and it rendered as a 400-character dollar
 * figure (C28). No listed US equity trades within orders of magnitude of this.
 */
export const ORDER_PRICE_PLAUSIBLE_MAX = 1e9;

/**
 * Session cell for a practice order (C30): the practice broker has no session
 * gate -- a resting order fills on any live print -- so neither "Regular" nor
 * "Extended hours" is true of it.
 */
export const ORDER_SESSION_PRACTICE = 'Any session';
export const ORDER_SESSION_PRACTICE_TITLE =
  "Practice orders work in every session: Nova's practice broker has no session gate, whatever the ticket's Extended hours box said.";
