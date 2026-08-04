/**
 * IBKR Gateway login / reconnect UX copy and tunables.
 * Feature-local so market_ui.ts does not keep growing past its size floor.
 */

/** Loud global banner (all scanner tabs) shown while discovery=ibkr and Gateway is down. */
export const GATEWAY_BANNER_TITLE = 'ACTION REQUIRED -- IB Gateway login';
export const GATEWAY_BANNER_CTA_LABEL = 'Open IB Gateway';
export const GATEWAY_BANNER_CTA_BUSY_LABEL = 'Opening...';

/** Trading prerequisites -- Gateway API port listening but Nova session not READY. */
export const PREREQ_GATEWAY_PORT_OPEN_DETAIL =
  'IB Gateway API port is open, but Nova session is not READY (reconnect stuck or Error 1100). Use Reconnect -- Gateway login is usually already done.';
export const PREREQ_GATEWAY_RECONNECT_CTA_LABEL = 'Reconnect Nova to Gateway';
export const PREREQ_GATEWAY_RECONNECT_CTA_BUSY_LABEL = 'Reconnecting...';
/** Default when ports look dark / login needed. */
export const PREREQ_GATEWAY_LOGIN_DETAIL =
  'Log into IB Gateway (API port 4001 live / 4002 paper). Look at your desktop for 2FA.';

/** How long (seconds) after a disconnected→connected transition to keep showing the
 * reconnect warm-up empty-state copy instead of the generic "no rows" message —
 * covers ADR 008 persistent scanner roster + L1 resubscribe time. */
export const IBKR_RECONNECT_WARMUP_SEC = 45;

/** Shown in Gainers/Losers empty state right after Gateway reconnects, before the
 * scanner roster/L1 stream has finished resubscribing (ADR 008) — distinct from a
 * genuinely quiet market so it never reads as "no data". */
export const EMPTY_IBKR_RECONNECT_WARMUP =
  'IB Gateway just reconnected — the scanner is resubscribing. First rows typically arrive within 30-45s.';
