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

/**
 * Header account pill on the practice venues: "Nova Paper Margin (NOVA-PAPER)"
 * / "Nova Sim Margin (NOVA-SIM)". The ledger lends margin-style buying power
 * (practice margin model), so its class is Margin.
 */
export const PRACTICE_PILL_PREFIX: Record<PracticeVenue, string> = {
  paper: 'Nova Paper',
  sim: 'Nova Sim',
};
export const PRACTICE_PILL_CLASS = 'Margin';
export const PRACTICE_PILL_ONLY_ACCOUNT_NOTE =
  "Nova's practice account is the only account on this venue. Switch the venue pill to Live to trade an IBKR account.";

/** Rows the practice venues add to the header cards. */
export const PRACTICE_CARD_FEES_LABEL = 'Fees today';
export const PRACTICE_CARD_STARTING_CASH_LABEL = 'Starting cash';
export const PRACTICE_CARD_REPLAY_LABEL = 'Replay';
export const PRACTICE_ACCOUNT_LOADING = 'Practice account loading';
export const PRACTICE_ACCOUNT_UNAVAILABLE = 'Practice account unavailable';
export const PRACTICE_NO_REPLAY = 'No replay loaded';
/** How a replay_key's first member (the ledger's replay source) reads in the header. */
export const PRACTICE_REPLAY_SOURCE_LABELS: Record<string, string> = {
  historical: 'download',
  capture: 'recording',
};

/** Tooltips -- every number says whose money it is. */
export const practiceTavTitle = (venue: PracticeVenue, id: string): string =>
  `Net liquidation of Nova's ${PRACTICE_VENUE_LABELS[venue]} practice account ${id} -- fake money: cash plus positions at their last mark.`;
export const PRACTICE_DAY_START_FALLBACK = 'the day start';
/** Adds up by construction: open change = day P&L - realized today (QA W3). */
export const practiceDayPnlTitle = (realized: string, openChange: string, since: string | null): string =>
  `Day P&L = realized today ${realized} + open P&L change ${openChange}, since ${since || PRACTICE_DAY_START_FALLBACK}.`;
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
/** Blank resets to the default, never "the current" (C43: backend PracticeResetRequest.starting_cash). */
export const PRACTICE_STARTING_CASH_PLACEHOLDER = 'Blank = $100,000 (the default)';
export const PRACTICE_PAPER_ARCHIVE_NOTE =
  'Paper archives the old ledger as practice-paper-<date-time>.json before starting over.';
export const PRACTICE_SIM_RESET_NOTE =
  'Sim resets the scratch account for the loaded replay only.';
export const practiceResetButtonLabel = (venue: PracticeVenue): string =>
  `Reset ${PRACTICE_VENUE_LABELS[venue]} account`;
export const practiceResetConfirmTitle = (venue: PracticeVenue): string =>
  `Reset the ${PRACTICE_VENUE_LABELS[venue]} practice account?`;
export const practiceResetConfirmMessage = (venue: PracticeVenue, startingCash: string | null): string => {
  // A blank amount resets to PRACTICE_STARTING_CASH_DEFAULT, whatever the old starting cash was (C43).
  const cash = startingCash
    ? `Starting cash will be ${startingCash}.`
    : `Starting cash resets to ${PRACTICE_STARTING_CASH_DEFAULT_LABEL}.`;
  const tail = venue === 'paper' ? PRACTICE_PAPER_ARCHIVE_NOTE : PRACTICE_SIM_RESET_NOTE;
  return `Positions, working orders and today's P&L are cleared. ${cash} ${tail}`;
};
export const PRACTICE_RESET_CONFIRM_LABEL = 'Reset';
export const practiceResetDone = (venue: PracticeVenue, cash: string): string =>
  `${PRACTICE_VENUE_LABELS[venue]} practice account reset -- cash ${cash}.`;
export const PRACTICE_RESET_FAILED = 'Reset failed';
/** Why the reset form is locked while its POST is in flight (ux/whyTip.ts). */
export const practiceResetBusyWhy = (venue: PracticeVenue): string =>
  `Resetting the ${PRACTICE_VENUE_LABELS[venue]} account -- wait for it to finish`;
export const practiceStartingCashInvalid = (min: string, max: string): string =>
  `Starting cash must be a whole-dollar amount between ${min} and ${max}, or left blank.`;

/* ---------- QA batch: orders / account / safety (2026-09-22) ---------- */
/** Mirrors backend PRACTICE_STARTING_CASH: what a reset with no amount starts from (C43). */
export const PRACTICE_STARTING_CASH_DEFAULT = 100_000;
export const PRACTICE_STARTING_CASH_DEFAULT_LABEL = '$100,000';

/* ── QA batch fix/qa-sim-replay (2026-09-22): stale money, practice-ticket copy ── */

/** A failed practice poll keeps the last figures this long (a blip), then drops them -- money never outlives its source (C44). */
export const PRACTICE_ACCOUNT_STALE_MS = 3 * PRACTICE_ACCOUNT_POLL_MS;
export const PRACTICE_ACCOUNT_REQUEST_FAILED = 'Practice account request failed';
/** Both practice venues refuse every short entry (`PRACTICE_NO_SHORTS`, AGENTS.md section 3). */
export const PRACTICE_NO_SHORTS_REASON = 'Nova does not support short entries yet';

/* ── QA batch fix/qa2-account-practice-sim (2026-09-22): the ticket's BP after ── */
/**
 * The practice ledger's fee and margin rules, mirrored from
 * backend/constants_practice.py (architecture/practice-account.md) so the
 * ticket's "BP after" follows the ledger instead of BP +/- the order value
 * (QA W28). Keep in step with the backend: IBKR Pro Fixed commission, SEC +
 * FINRA TAF pass-throughs on sells, FINRA 4210 intraday margin 4x from the
 * USD 2,000 margin minimum, cash (1x) below it.
 */
export const PRACTICE_COMMISSION_PER_SHARE = 0.005;
export const PRACTICE_COMMISSION_MIN = 1.0;
export const PRACTICE_COMMISSION_MAX_PCT = 0.01;
export const PRACTICE_SEC_FEE_RATE = 20.6 / 1_000_000;
export const PRACTICE_FINRA_TAF_PER_SHARE = 0.000195;
export const PRACTICE_FINRA_TAF_MAX = 9.79;
export const PRACTICE_MARGIN_INTRADAY_MULT = 4.0;
export const PRACTICE_MARGIN_MIN_EQUITY = 2_000;
export const PRACTICE_CASH_MULT = 1.0;
