/**
 * Header Cash / Margin chip from IBKR AccountType only.
 * Never infer Margin from BuyingPower or account-structure tags.
 */
import {
  GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
} from '../constantGroups/global_bar';
import type { IbkrAccountSummary } from './types';

export type AccountTypeKind = 'cash' | 'margin' | 'unknown';

export type AccountTypeChipView = {
  kind: AccountTypeKind;
  label: string;
  tooltip: string;
};

const CASH_TOKENS = new Set(['CASH', 'CASH ACCOUNT']);
const MARGIN_TOKENS = new Set([
  'MARGIN',
  'MRGN',
  'REGT',
  'REGT MARGIN',
  'REG T MARGIN',
  'PORTFOLIO MARGIN',
  'PMRGN',
  'UNCLEARED MARGIN ACCOUNT',
  'PM',
]);

const LABELS: Record<AccountTypeKind, string> = {
  cash: GLOBAL_BAR_ACCOUNT_TYPE_CASH,
  margin: GLOBAL_BAR_ACCOUNT_TYPE_MARGIN,
  unknown: GLOBAL_BAR_ACCOUNT_TYPE_UNKNOWN,
};

export function classifyAccountType(raw: string | null | undefined): AccountTypeKind {
  const key = (raw ?? '').trim().toUpperCase();
  if (!key) return 'unknown';
  if (CASH_TOKENS.has(key)) return 'cash';
  if (MARGIN_TOKENS.has(key)) return 'margin';
  return 'unknown';
}

export function accountTypeChipView(opts: {
  ibkrConnected: boolean;
  summary: IbkrAccountSummary | null;
}): AccountTypeChipView | null {
  if (!opts.ibkrConnected || !opts.summary?.connected) return null;
  const kind = classifyAccountType(opts.summary.AccountType);
  return {
    kind,
    label: LABELS[kind],
    tooltip: GLOBAL_BAR_ACCOUNT_TYPE_TOOLTIP,
  };
}
