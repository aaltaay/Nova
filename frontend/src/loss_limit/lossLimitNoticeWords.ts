/**
 * The daily loss limit's notices and voice lines (ADR 056): what the desk says at 80% of the limit and at
 * the limit, in every window. Plain and short -- the operator reads them mid-trade.
 */

/** The cross-window poll share: one window reads `GET /api/loss-limit`, every window shows its notices. */
export const LOSS_LIMIT_POLL_SHARE = 'loss-limit';
/** A leader quiet this long hands the poll to another window (two missed polls). */
export const LOSS_LIMIT_LEADER_STALE_MS = 7_000;

export const LOSS_LIMIT_WARN_TITLE = 'Loss limit: 80% reached';
export const LOSS_LIMIT_TRIP_TITLE = 'Daily loss limit reached';

/** "Paper is down $1,620 of your $2,000 daily loss limit." */
export const lossLimitWarnBody = (account: string, loss: string, limit: string): string =>
  `${account} is down ${loss} of your ${limit} daily loss limit.`;

/** "Paper is down $2,040 against your $2,000 limit · 10:12 ET" */
export const lossLimitTripLine = (account: string, loss: string, limit: string, clock: string): string =>
  `${account} is down ${loss} against your ${limit} limit${clock ? ` · ${clock}` : ''}`;

/** "Sold 1,000 WETO · order 259"; a short's cover reads "Bought back". */
export const lossLimitSoldLine = (verb: string, qty: string, symbol: string, orderId: number | null): string =>
  `${verb} ${qty}${symbol}${orderId != null ? ` · order ${orderId}` : ''}`;

/** "1,000 WETO was not sold — the close was refused" */
export const lossLimitNotSoldLine = (qty: string, symbol: string, error: string): string =>
  `${qty}${symbol} was not sold — ${error}`;

export const LOSS_LIMIT_NOT_SOLD_UNKNOWN = 'the close was refused';
export const LOSS_LIMIT_STILL_SELLING = 'Auto sell is still selling what was opened today: the Orders table shows each close.';

/** The voice (desk-ops.md, "The desk's voice and the header mute"): numbers as whole dollars. */
export const lossLimitWarnSpoken = (account: string, loss: string, limit: string): string =>
  `Loss limit warning. ${account} is down ${loss} dollars of ${limit}.`;

export const lossLimitTripSpoken = (account: string): string => `Daily loss limit reached on ${account}.`;
