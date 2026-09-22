/**
 * Pure view model for the header account pill: "Individual Margin (U1234567)"
 * on Live, "Nova Paper Margin (NOVA-PAPER)" / "Nova Sim Margin (NOVA-SIM)" on
 * the practice venues (ADR 020).
 *
 * Structure is IBKR's raw AccountType (ownership: INDIVIDUAL, IRA, ...); class
 * is the backend-stamped account_class. A word that is not reported is
 * omitted, never inferred. The full id is shown because it is what tells two
 * accounts apart; IBKR's API never exposes the login username. Null while
 * disconnected -- an old id would be a lie.
 */
import {
  DESK_VENUE_PAPER_ACCOUNT_ID,
  DESK_VENUE_SIM_ACCOUNT_ID,
  deskVenuePracticeAccountTooltip,
  isPracticeAccountId,
} from '../constantGroups/desk_venue';
import {
  GLOBAL_BAR_ACCOUNT_PILL_SWITCH_NOTE,
  GLOBAL_BAR_ACCOUNT_STRUCTURE_LABELS,
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING,
  GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX,
  globalBarAccountIdTooltip,
} from '../constantGroups/global_bar';
import {
  PRACTICE_PILL_CLASS,
  PRACTICE_PILL_ONLY_ACCOUNT_NOTE,
  PRACTICE_PILL_PREFIX,
  type PracticeVenue,
} from '../constantGroups/practice';
import type { IbkrAccountSummary, IbkrStatus } from '../ibkr/types';
import { isPracticeVenue } from '../practice/practiceAccountModel';

export type HeaderAccountPillKind = 'live' | 'paper' | 'unknown' | 'practice';
export type HeaderAccountClass = 'cash' | 'margin';

export interface HeaderAccountPillView {
  /** IBKR account kind from the id (U… live, DU… paper) or Nova's practice ledger. */
  kind: HeaderAccountPillKind;
  /** What the pill says, e.g. "Individual Margin (U1234567)". */
  label: string;
  structure: string | null;
  accountClass: HeaderAccountClass | null;
  id: string | null;
  tooltip: string;
  /** Every managed account on the login; the active one is what Nova trades. */
  accounts: { id: string; active: boolean }[];
  /** Why the list is information only. */
  note: string;
}

export type HeaderAccountPillStatus = Pick<
  IbkrStatus,
  'connected' | 'account_id' | 'account_ids' | 'broker_account_kind'
>;

const CLASS_LABELS: Record<HeaderAccountClass, string> = {
  cash: GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  margin: GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
};

const PRACTICE_IDS: Record<PracticeVenue, string> = {
  paper: DESK_VENUE_PAPER_ACCOUNT_ID,
  sim: DESK_VENUE_SIM_ACCOUNT_ID,
};

/** Raw IBKR AccountType -> pill word; unknown or absent -> null (omitted). */
export function accountStructureLabel(raw: string | null | undefined): string | null {
  const key = (raw ?? '').trim().toUpperCase();
  if (!key) return null;
  return GLOBAL_BAR_ACCOUNT_STRUCTURE_LABELS[key] ?? null;
}

/** Backend-stamped Cash / Margin on a connected snapshot; null is omitted, not guessed. */
export function accountClassOf(summary: IbkrAccountSummary | null): HeaderAccountClass | null {
  if (!summary?.connected) return null;
  return summary.account_class === 'cash' || summary.account_class === 'margin'
    ? summary.account_class
    : null;
}

/** Short-gate note plus the raw AccountType / TradingType (carried from the old Cash / Margin chip). */
export function accountTypeTooltip(summary: IbkrAccountSummary): string {
  const raw = (summary.AccountType ?? '').trim() || GLOBAL_BAR_ACCOUNT_TYPE_RAW_MISSING;
  const parts = [GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP, `${GLOBAL_BAR_ACCOUNT_TYPE_RAW_PREFIX} ${raw}`];
  const trading = (summary.TradingType ?? '').trim();
  if (trading) parts.push(`${GLOBAL_BAR_ACCOUNT_TYPE_TRADING_PREFIX} ${trading}`);
  return parts.join(' ');
}

function practicePill(
  venue: PracticeVenue,
  status: HeaderAccountPillStatus,
  practiceId: string | null,
): HeaderAccountPillView {
  // The id is the venue's own constant, so it can be stated before the ledger loads.
  const id =
    practiceId ?? (isPracticeAccountId(status.account_id) ? String(status.account_id) : PRACTICE_IDS[venue]);
  const structure = PRACTICE_PILL_PREFIX[venue];
  return {
    kind: 'practice',
    label: `${structure} ${PRACTICE_PILL_CLASS} (${id})`,
    structure,
    accountClass: 'margin',
    id,
    tooltip: deskVenuePracticeAccountTooltip(id),
    accounts: [{ id, active: true }],
    note: PRACTICE_PILL_ONLY_ACCOUNT_NOTE,
  };
}

export function headerAccountPillView(opts: {
  venue: string | null | undefined;
  status: HeaderAccountPillStatus;
  summary: IbkrAccountSummary | null;
  /** account_id from the loaded practice ledger on Paper / Sim. */
  practiceId?: string | null;
}): HeaderAccountPillView | null {
  if (isPracticeVenue(opts.venue)) return practicePill(opts.venue, opts.status, opts.practiceId ?? null);
  const { status, summary } = opts;
  if (!status.connected) return null;
  // The poller normalises these (C4); the guards keep any other caller safe too.
  const id = typeof status.account_id === 'string' ? status.account_id.trim() || null : null;
  const structure = summary?.connected ? accountStructureLabel(summary.AccountType) : null;
  const accountClass = accountClassOf(summary);
  if (!id && !structure && !accountClass) return null;
  const words = [structure, accountClass ? CLASS_LABELS[accountClass] : null].filter(
    (word): word is string => Boolean(word),
  );
  const label = id ? (words.length ? `${words.join(' ')} (${id})` : id) : words.join(' ');
  const kind: HeaderAccountPillKind = status.broker_account_kind ?? 'unknown';
  const listed = Array.isArray(status.account_ids)
    ? status.account_ids.filter((acct): acct is string => typeof acct === 'string')
    : [];
  const ids = id && !listed.includes(id) ? [id, ...listed] : listed;
  const others = ids.filter((other) => other !== id);
  const tooltip = [
    id ? globalBarAccountIdTooltip(id, kind, others) : null,
    summary?.connected ? accountTypeTooltip(summary) : null,
  ]
    .filter(Boolean)
    .join(' ');
  return {
    kind,
    label,
    structure,
    accountClass,
    id,
    tooltip,
    accounts: ids.map((account) => ({ id: account, active: account === id })),
    note: GLOBAL_BAR_ACCOUNT_PILL_SWITCH_NOTE,
  };
}
