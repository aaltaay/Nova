/**
 * Practice account (ADR 020): Nova's own ledger on the Paper and Sim venues.
 * Mirrors backend/constants_practice.py where the frontend needs a value.
 */
import type { DeskVenue } from './desk_venue';

export type PracticeVenue = Extract<DeskVenue, 'paper' | 'sim'>;
export const PRACTICE_VENUES: readonly PracticeVenue[] = ['paper', 'sim'];

/** GET ?venue=paper|sim -> the account; POST /reset {venue, starting_cash?} -> the new account. */
export const PRACTICE_ACCOUNT_API_PATH = '/api/practice/account';
export const PRACTICE_RESET_API_PATH = '/api/practice/reset';
export const practiceAccountPath = (venue: PracticeVenue): string =>
  `${PRACTICE_ACCOUNT_API_PATH}?venue=${venue}`;

/** Header strip refresh. Fills land locally, so a short cadence is cheap. */
export const PRACTICE_ACCOUNT_POLL_MS = 2000;

/** Starting-cash bounds for the reset form (mirror backend PRACTICE_STARTING_CASH_*). */
export const PRACTICE_STARTING_CASH_MIN = 1000;
export const PRACTICE_STARTING_CASH_MAX = 100_000_000;

export const PRACTICE_VENUE_LABELS: Record<PracticeVenue, string> = {
  paper: 'Paper',
  sim: 'Sim',
};

/** Strip labels. */
export const PRACTICE_STRIP_CASH_LABEL = 'Cash';
export const PRACTICE_STRIP_BP_LABEL = 'BP';
export const PRACTICE_STRIP_DAY_PNL_LABEL = 'Day P&L';
export const PRACTICE_STRIP_FEES_LABEL = 'Fees';
export const PRACTICE_STRIP_REPLAY_LABEL = 'Replay';
export const PRACTICE_STRIP_LOADING = 'Practice account loading';
export const PRACTICE_STRIP_UNAVAILABLE = 'Practice account unavailable';
export const PRACTICE_STRIP_NO_REPLAY = 'No replay loaded';

/** Strip tooltips -- every number says whose money it is. */
export const practiceAccountIdTitle = (venue: PracticeVenue, id: string, startingCash: string): string =>
  venue === 'sim'
    ? `${id} -- Nova's Sim practice account. Fake money on the loaded replay; unwinds when you rewind. Started with ${startingCash}.`
    : `${id} -- Nova's Paper practice account. Fake money on the live data feed; nothing reaches IBKR. Started with ${startingCash}.`;
export const practiceCashTitle = (netLiq: string): string =>
  `Settled practice cash after fills and fees. Net liquidation ${netLiq}.`;
export const practiceBuyingPowerTitle = (gross: string): string =>
  `Buying power from the practice margin model. Gross position value ${gross}.`;
export const practiceDayPnlTitle = (realized: string, unrealized: string, since: string): string =>
  `Day P&L = realized ${realized} + unrealized ${unrealized}, since ${since}.`;
export const practiceFeesTitle = (fills: number): string =>
  `Simulated commissions and fees charged today across ${fills} fill${fills === 1 ? '' : 's'}.`;
export const PRACTICE_REPLAY_KEY_TITLE =
  'The replay this Sim ledger belongs to. Load another session and the account starts over.';

/** Settings > Trade > Practice Account. */
export const PRACTICE_SETTINGS_SUBTAB_LABEL = 'Practice Account';
export const PRACTICE_SETTINGS_TITLE = 'Reset practice account';
export const PRACTICE_SETTINGS_HINT =
  "Start Nova's practice ledger over: cash back to the starting balance, positions and working orders cleared. Fake money only -- nothing reaches IBKR.";
export const PRACTICE_STARTING_CASH_LABEL = 'Starting cash (optional)';
export const PRACTICE_STARTING_CASH_PLACEHOLDER = 'Keep the current starting cash';
export const PRACTICE_PAPER_ARCHIVE_NOTE =
  'Paper archives the old ledger as practice-paper-<date-time>.json before starting over.';
export const PRACTICE_SIM_RESET_NOTE =
  'Sim resets the scratch account for the loaded replay only.';
export const practiceResetButtonLabel = (venue: PracticeVenue): string =>
  `Reset ${PRACTICE_VENUE_LABELS[venue]} account`;
export const practiceResetConfirmTitle = (venue: PracticeVenue): string =>
  `Reset the ${PRACTICE_VENUE_LABELS[venue]} practice account?`;
export const practiceResetConfirmMessage = (venue: PracticeVenue, startingCash: string | null): string => {
  const cash = startingCash ? `Starting cash will be ${startingCash}.` : 'Starting cash is unchanged.';
  const tail = venue === 'paper' ? PRACTICE_PAPER_ARCHIVE_NOTE : PRACTICE_SIM_RESET_NOTE;
  return `Positions, working orders and today's P&L are cleared. ${cash} ${tail}`;
};
export const PRACTICE_RESET_CONFIRM_LABEL = 'Reset';
export const practiceResetDone = (venue: PracticeVenue, cash: string): string =>
  `${PRACTICE_VENUE_LABELS[venue]} practice account reset -- cash ${cash}.`;
export const PRACTICE_RESET_FAILED = 'Reset failed';
export const practiceStartingCashInvalid = (min: string, max: string): string =>
  `Starting cash must be a whole-dollar amount between ${min} and ${max}, or left blank.`;
