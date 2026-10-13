/**
 * The Followed traders page. Mirrors backend/followed_traders/constants_followed.py
 * (FOLLOWED_SCHEMA_VERSION, FOLLOWED_CAPTURE_STALE_SEC). Schema: architecture/schema/followed-traders.md.
 */

export const FOLLOWED_SCHEMA_VERSION = 1;
export const FOLLOWED_CONFIG_PATH = '/api/followed-traders/config';
export const FOLLOWED_DAY_PATH = '/api/followed-traders/day';

/** The page asks this often while it shows. */
export const FOLLOWED_REFRESH_MS = 3_000;
/** The gate probe asks again this soon when the backend did not answer at all (still starting). */
export const FOLLOWED_PROBE_RETRY_MS = 10_000;
/** The feed's capture reads stale when its status is older than this. */
export const FOLLOWED_CAPTURE_STALE_SEC = 60;

export const FT_TITLE = 'Followed traders';
/** The page is a placeholder until the operator approves its design (2026-10-13). */
export const FT_PLACEHOLDER_NOTE =
  'Placeholder while the page’s design is agreed: the feed’s trades as Nova reads and prices them.';
export const FT_LOADING = 'Asking the feed…';
export const FT_OFF = 'The followed traders feed is not configured on this desk (NOVA_FOLLOW_FEED_URL in the backend’s .env).';
export const FT_UNREACHABLE = 'The feed did not answer:';
export const FT_BAD_ANSWER = 'The feed answered something Nova cannot read:';
export const FT_READ_FAILED = 'Nova’s backend did not answer:';
export const FT_NO_TRADES = 'The feed recorded no trades on this day.';
export const FT_NO_STATUS = 'The feed has not reported its capture yet.';

export const FT_EXIT_PENDING = 'reading tape…';
/** Pending with a reason: IBKR not connected, its history budget, a retry. */
export const FT_EXIT_WAITING = 'waiting for IBKR';
export const FT_EXIT_UNAVAILABLE = 'no price';
