/**
 * The daily loss limit's notices and voice lines (ADR 056, ADR 061): what the desk says at 80% of a line and at
 * the line, in every window, naming which line it is -- the account's, your trades' or the bots'. Plain and
 * short -- the operator reads them mid-trade.
 */
import type { LossLimitLineId } from './lossLimitApi';

/** The cross-window poll share: one window reads `GET /api/loss-limit`, every window shows its notices. */
export const LOSS_LIMIT_POLL_SHARE = 'loss-limit';
/** A leader quiet this long hands the poll to another window (two missed polls). */
export const LOSS_LIMIT_LEADER_STALE_MS = 7_000;

/** Each line's words: its titles, who is down, whose limit, and what the voice calls it. */
const LINE: Record<LossLimitLineId, {
  warnTitle: string; tripTitle: string; who: (account: string) => string; whose: string; spoken: string;
}> = {
  account: {
    warnTitle: 'Loss limit: 80% reached',
    tripTitle: 'Daily loss limit reached',
    who: (account) => `${account} is`,
    whose: 'your',
    spoken: 'Daily loss limit',
  },
  you: {
    warnTitle: "Your trades' loss limit: 80% reached",
    tripTitle: "Your trades' loss limit reached",
    who: (account) => `Your trades on ${account} are`,
    whose: 'your',
    spoken: "Your trades' loss limit",
  },
  bots: {
    warnTitle: "The bots' loss limit: 80% reached",
    tripTitle: "The bots' loss limit reached",
    who: (account) => `The bots' trades on ${account} are`,
    whose: 'their',
    spoken: "The bots' loss limit",
  },
};

export const lossLimitWarnTitle = (line: LossLimitLineId): string => LINE[line].warnTitle;
export const lossLimitTripTitle = (line: LossLimitLineId): string => LINE[line].tripTitle;

/** "Paper is down $1,620 of your $2,000 daily loss limit."; "The bots' trades on Paper are down $420 of their $500 limit." */
export const lossLimitWarnBody = (line: LossLimitLineId, account: string, loss: string, limit: string): string =>
  line === 'account'
    ? `${account} is down ${loss} of your ${limit} daily loss limit.`
    : `${LINE[line].who(account)} down ${loss} of ${LINE[line].whose} ${limit} limit.`;

/** "Paper is down $2,040 against your $2,000 limit · 10:12 ET"; a side line names whose trades. */
export const lossLimitTripLine = (
  line: LossLimitLineId, account: string, loss: string, limit: string, clock: string,
): string => `${LINE[line].who(account)} down ${loss} against ${LINE[line].whose} ${limit} limit${clock ? ` · ${clock}` : ''}`;

/** "Sold 1,000 WETO · order 259"; a short's cover reads "Bought back". */
export const lossLimitSoldLine = (verb: string, qty: string, symbol: string, orderId: number | null): string =>
  `${verb} ${qty}${symbol}${orderId != null ? ` · order ${orderId}` : ''}`;

/** "1,000 WETO was not sold — the close was refused" */
export const lossLimitNotSoldLine = (qty: string, symbol: string, error: string): string =>
  `${qty}${symbol} was not sold — ${error}`;

export const LOSS_LIMIT_NOT_SOLD_UNKNOWN = 'the close was refused';
export const LOSS_LIMIT_STILL_SELLING = 'Auto sell is still selling what was opened today: the Orders table shows each close.';

/** The voice (desk-ops.md, "The desk's voice and the header mute"): numbers as whole dollars. */
export const lossLimitWarnSpoken = (line: LossLimitLineId, account: string, loss: string, limit: string): string =>
  line === 'account'
    ? `Loss limit warning. ${account} is down ${loss} dollars of ${limit}.`
    : `Loss limit warning. ${LINE[line].who(account)} down ${loss} dollars of ${limit}.`;

/** "Daily loss limit reached on Paper." / "The bots' loss limit reached on Paper." */
export const lossLimitTripSpoken = (line: LossLimitLineId, account: string): string =>
  `${LINE[line].spoken} reached on ${account}.`;
