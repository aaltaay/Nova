/**
 * IBKR Gateway login / reconnect UX copy and tunables.
 * Feature-local so market_ui.ts does not keep growing past its size floor.
 */

/** Loud global banner (all scanner tabs) shown while discovery=ibkr and Gateway is down. */
export const GATEWAY_BANNER_TITLE = 'ACTION REQUIRED -- IB Gateway login';
export const GATEWAY_BANNER_CTA_LABEL = 'Open IB Gateway';
export const GATEWAY_BANNER_CTA_BUSY_LABEL = 'Opening...';
export const PREREQ_OPEN_PAPER_LABEL = 'Open paper Gateway';
export const PREREQ_OPEN_LIVE_LABEL = 'Open live Gateway';
export const PREREQ_CLOSE_LABEL = 'X';
export const PREREQ_CLOSE_ARIA = 'Close checklist';
export const HEADER_DESK_ROLE = 'Desk';
export const HEADER_DESK_API_DOWN_LABEL = 'API down';
export const PREREQ_LEAD_MANUAL =
  'Pick paper (4002) or live (4001). Nova switches to that door and starts IBC. Approve IBKR Mobile 2FA if prompted.';
export const PREREQ_LEAD_API =
  'Nova API is down. Start the API before trusting live data or placing orders.';

/** Trading prerequisites -- Gateway API port listening but Nova session not READY. */
export const PREREQ_GATEWAY_PORT_OPEN_DETAIL =
  'IB Gateway API port is open, but Nova session is not READY (reconnect stuck or Error 1100). Use Reconnect -- Gateway login is usually already done.';
export const PREREQ_GATEWAY_CLIENT_ID_DETAIL =
  'Another Nova API already holds IBKR clientId 17. Stop the extra API (only one process on port 8000), then Reconnect -- this is not a Gateway login / 2FA problem.';
export const PREREQ_GATEWAY_RECONNECT_CTA_LABEL = 'Reconnect Nova to Gateway';
export const PREREQ_GATEWAY_RECONNECT_CTA_BUSY_LABEL = 'Reconnecting...';
/** Default when ports look dark / login needed. */
export const PREREQ_GATEWAY_LOGIN_DETAIL =
  'Log into IB Gateway (API port 4001 live / 4002 paper). Look at your desktop for 2FA.';
/** Preferred port dark, the other Gateway is already logged in. */
export const PREREQ_GATEWAY_FOLLOW_PAPER_DETAIL =
  'Paper Gateway is already up on 4002. Nova is still targeting Live 4001 -- use Paper, or log into Live.';
export const PREREQ_GATEWAY_FOLLOW_LIVE_DETAIL =
  'Live Gateway is already up on 4001. Nova is still targeting Paper 4002 -- use Live, or log into Paper.';
export const PREREQ_GATEWAY_FOLLOW_PAPER_CTA_LABEL = 'Use paper Gateway';
export const PREREQ_GATEWAY_FOLLOW_LIVE_CTA_LABEL = 'Use live Gateway';
export const PREREQ_GATEWAY_FOLLOW_CTA_BUSY_LABEL = 'Switching...';

/** The Second Factor prompt on screen is older than IBC's own timeout --
 * approving it now will not complete the login (PROBLEM_LOG 2026-08-25). */
export const PREREQ_GATEWAY_STALE_SECOND_FACTOR_DETAIL =
  'The Second Factor prompt on screen has expired -- IBKR will not accept an approval now.';
export const PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_LABEL = 'Start fresh login';
export const PREREQ_GATEWAY_STALE_SECOND_FACTOR_CTA_BUSY_LABEL = 'Restarting login...';

/** D-058 -- READY desk, but the Gateway stopped answering reqCompletedOrders
 * (usually after a Gateway <-> IBKR server reconnect; PROBLEM_LOG 2026-09-19).
 * A warning, not a blocker. Never claim orders work: a Read-Only API Gateway
 * shows the same timeout and rejects every order (PROBLEM_LOG 2026-07-22). */
export const PREREQ_COMPLETED_ORDERS_STUCK_PREFIX = 'Completed orders not answering since';
export const PREREQ_COMPLETED_ORDERS_STUCK_DETAIL =
  'Prices and positions still update; Closed Orders may miss orders from before this session. Nova keeps re-checking and clears this when the Gateway answers. To fix, restart IB Gateway when convenient (IBKR Mobile 2FA). If orders are rejected too, check the Gateway Read-Only API setting first.';

/** D-076 -- IB Gateway "Read-Only API" is ticked, so the session reaches READY
 * and looks tradeable while every order, cancel and replace comes back as
 * Error 321 (PROBLEM_LOG 2026-07-22). A named blocker, not a login problem. */
export const PREREQ_GATEWAY_READ_ONLY_LABEL = 'IB Gateway Read-Only API';
export const PREREQ_GATEWAY_READ_ONLY_DETAIL =
  'Gateway is in Read-Only API mode -- orders will be rejected (Error 321). Untick Configure > Settings > API > Read-Only API, then reconnect. Prices and positions are unaffected.';

export const DOOR_TRAIL_TITLE = 'Door trail';
export const DOOR_TRAIL_KICKER = 'Paper / Live audit';
export const DOOR_TRAIL_HINT =
  'Who clicked Paper or Live, what IBC did, and whether Nova attached. Not order Activity.';
export const DOOR_TRAIL_EMPTY =
  'No door events yet. A Paper/Live click or Gateway attach will show here.';
export const DOOR_TRAIL_REFRESH = 'Refresh';
export const DOOR_TRAIL_FETCH_FAILED =
  'Could not load the door trail -- the API did not answer. If two Nova APIs are running, stop the extra one (only one process on port 8000).';

/** How long (seconds) after a disconnected→connected transition to keep showing the
 * reconnect warm-up empty-state copy instead of the generic "no rows" message —
 * covers ADR 008 persistent scanner roster + L1 resubscribe time. */
export const IBKR_RECONNECT_WARMUP_SEC = 45;

/** Shown in Gainers/Losers empty state right after Gateway reconnects, before the
 * scanner roster/L1 stream has finished resubscribing (ADR 008) — distinct from a
 * genuinely quiet market so it never reads as "no data". */
export const EMPTY_IBKR_RECONNECT_WARMUP =
  'IB Gateway just reconnected — the scanner is resubscribing. First rows typically arrive within 30-45s.';
