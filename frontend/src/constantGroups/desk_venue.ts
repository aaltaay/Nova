/**
 * Desk venue copy and endpoints (ADR 020 -- three venues on one feed).
 *
 * The header pills are venue pills: Live = IBKR, real money; Paper = Nova's
 * practice account (fake money on the live feed); Sim = the replay playground.
 * Paper never launches a Gateway -- the IBKR paper Gateway (port 4002) is legacy
 * with no desk button: by hand only via `POST /api/ibkr/gateway-mode`, never an
 * automatic fallback (ADR 020, second pass).
 */

export type DeskVenue = 'live' | 'paper' | 'sim';

/** GET -> {venue}; POST {venue} -> {venue}. */
export const DESK_VENUE_API_PATH = '/api/desk/venue';
/** Legacy Sim toggle, used only when the venue route is missing (stale API). */
export const DESK_VENUE_SIM_FALLBACK_API_PATH = '/api/sim';
/** Live keeps ensuring the live Gateway through the existing gateway-mode flow. */
export const DESK_VENUE_GATEWAY_MODE_API_PATH = '/api/ibkr/gateway-mode';

/** Practice account ids the backend reports on the practice venues. */
export const DESK_VENUE_PAPER_ACCOUNT_ID = 'NOVA-PAPER';
export const DESK_VENUE_SIM_ACCOUNT_ID = 'NOVA-SIM';

/** Pill tooltips -- what each venue is. */
export const DESK_VENUE_LIVE_TITLE =
  'Live -- IBKR, real money. Live data and live orders through the live Gateway (port 4001). Spend stays locked until the desk is armed and IBKR_LIVE_TRADING_CONFIRMED is set.';
export const DESK_VENUE_PAPER_TITLE =
  "Paper -- Nova's practice account. Fake money on the live data feed. Orders fill locally against live quotes and prints; nothing reaches IBKR. Not the IBKR paper Gateway.";
export const DESK_VENUE_SIM_TITLE =
  'Sim -- replay playground. Trade a recorded or downloaded session with a scratch account that unwinds when you rewind. No IBKR Gateway places. Not paper. Not live.';

/** Confirm dialog titles for a venue switch. */
export const DESK_VENUE_CONFIRM_LIVE_TITLE = 'Switch to Live (IBKR, real money)';
export const DESK_VENUE_CONFIRM_PAPER_TITLE = 'Switch to Paper (Nova practice account)';
export const DESK_VENUE_CONFIRM_SIM_TITLE = 'Switch to Sim (replay playground)';

/** Hot strip above Stock View / Trading while the venue is Paper. */
export const DESK_VENUE_PAPER_BANNER_TEXT =
  "PAPER TRADING -- orders go to Nova's practice account: fake money on the live feed, never to IBKR.";

/** Header account-id chip tooltip on a practice venue. */
export const deskVenuePracticeAccountTooltip = (id: string): string =>
  id === DESK_VENUE_SIM_ACCOUNT_ID
    ? `${id} -- Nova-managed Sim practice account. Fake money on the loaded replay; unwinds when you rewind, clears when the replay unloads. Not an IBKR account.`
    : `${id} -- Nova-managed practice account. Fake money on the live data feed; nothing reaches IBKR. Not an IBKR account.`;

export const isPracticeAccountId = (id: string | null | undefined): boolean =>
  id === DESK_VENUE_PAPER_ACCOUNT_ID || id === DESK_VENUE_SIM_ACCOUNT_ID;

/** Capsule errors. */
export const DESK_VENUE_SWITCH_UNREACHABLE = 'Could not reach Nova backend to switch the desk venue';
export const deskVenueSwitchFailed = (venue: DeskVenue): string => `Switch to ${venue} failed`;
export const DESK_VENUE_API_RESTART_HINT =
  'Restart Nova API (venue route missing), then try switching again.';
