/**
 * The real-time view and the order gate (ADR 045). Owner: `frontend/src/market_view/`.
 *
 * 2026-10-05 08:30 ET: the Level 2 on screen was 3-7 s behind Nova's book and the operator sold at
 * a bid that no longer existed. While a view lags, orders priced from it are locked here and
 * refused by the backend (`backend/constants_market_view.py`, whose numbers these mirror).
 */

/** The backend says "still current" (`beat`) every 250 ms; this long without a word locks orders. */
export const VIEW_SILENT_LOCK_MS = 750;
/** A frame that took longer than this from the backend's `sent` to arrival locks orders. */
export const VIEW_TRANSIT_LOCK_MS = 500;
/** A newer book received (or announced by a beat) and not drawn for this long locks orders. */
export const VIEW_UNDRAWN_LOCK_MS = 500;
/** How often a mounted lock reader re-judges the views (a lock clears or sets within this). */
export const VIEW_LOCK_TICK_MS = 200;

export const VIEW_LOCK_TAIL = 'Orders are locked until it catches up. Flatten and cancels still work.';
export const TICKET_VIEW_LOCKED_LABEL = 'Market view behind · locked';

/**
 * A Level 2 IBKR refused (309) or ended, with no book since (operator decision 2026-10-13, #913: lock, with the
 * true reason). Not "behind": there is no Level 2 at all, so the lock says so and quotes IBKR's reason.
 */
export const LEVEL2_REFUSED_LEAD = 'No Level 2 for';
export const LEVEL2_REFUSED_TAIL = 'Orders are locked until a Level 2 is live. Flatten and cancels still work.';
export const TICKET_LEVEL2_REFUSED_LABEL = 'No Level 2 · locked';

/**
 * A Level 2 that is open but has sent no book yet (operator decision 2026-10-27, #913 option 1). BKYI, 2026-10-13:
 * IBKR never answered the request, the socket beat every 250 ms, and the ticket stayed open. Each `subscribed`
 * locks until a book arrives; the backend's `BOOK_WAITING` reads the same.
 */
export const LEVEL2_WAITING_LEAD = 'No book yet on';
export const LEVEL2_WAITING_TAIL = 'Orders are locked until its first book arrives. Flatten and cancels still work.';
export const TICKET_LEVEL2_WAITING_LABEL = 'Waiting for Level 2 · locked';
export const BOOK_WAITING_CODE = 'BOOK_WAITING';

/**
 * The backend's own lock (ADR 045 amendment 2026-10-14, "one funnel"): the Time & Sales socket sends the order
 * gate's answer for the symbol (`market_view.gate.desk_lock`), and the ticket locks with the door's own words.
 * GENK, 2026-10-14: the tape missed every trade from 09:25:11 while an order went out at 09:25:19.
 */
export const TAPE_STALE_CODE = 'TAPE_STALE';
export const TICKET_TAPE_LOCKED_LABEL = 'Time & Sales behind · locked';
export const TICKET_FEED_LOCKED_LABEL = 'Nova behind the market · locked';

/** Each lock flip is written to the backend log (`backend/routes/market_view_lock.py`). */
export const VIEW_LOCK_REPORT_PATH = '/market-view/lock';

/** The backend's refusal codes (`market_view.gate`). */
export const VIEW_REFUSAL_CODES = ['VIEW_STALE', 'ORDER_LATE', 'FEED_STALE', 'BOOK_WAITING', 'TAPE_STALE', 'VIEW_MISSING'] as const;
