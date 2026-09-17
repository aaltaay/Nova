/**
 * Cash vs Margin class -- SSOT for the header chip (#181) and ticket Short (#186).
 *
 * TWS AccountType is ownership (INDIVIDUAL / LLC / IRA). A connected snapshot
 * is always cash or margin. Short is visible only on margin.
 * Prefer stamped `account_class` from GET /api/ibkr/account (includes env).
 */
import {
  IBKR_ACCOUNT_CLASS_CASH_MAX_BP_RATIO,
  IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO,
} from '../constantGroups/ibkr_account';
import type { IbkrAccountSummary } from './types';

export type AccountTypeKind = 'cash' | 'margin' | 'unknown';

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

export function classifyAccountType(raw: string | null | undefined): AccountTypeKind {
  const key = (raw ?? '').trim().toUpperCase();
  if (!key) return 'unknown';
  if (CASH_TOKENS.has(key)) return 'cash';
  if (MARGIN_TOKENS.has(key)) return 'margin';
  return 'unknown';
}

function asFinite(raw: number | null | undefined): number | null {
  if (raw == null || !Number.isFinite(raw)) return null;
  return raw;
}

export function classifyMarginKind(summary: IbkrAccountSummary): 'cash' | 'margin' {
  if (summary.account_class === 'cash' || summary.account_class === 'margin') {
    return summary.account_class;
  }
  for (const raw of [summary.AccountType, summary.TradingType]) {
    const kind = classifyAccountType(raw);
    if (kind === 'cash' || kind === 'margin') return kind;
  }
  const bp = asFinite(summary.BuyingPower);
  const cash = asFinite(summary.TotalCashValue);
  const excess = asFinite(summary.ExcessLiquidity);
  if (bp != null && cash != null && cash > 0) {
    if (bp <= cash * IBKR_ACCOUNT_CLASS_CASH_MAX_BP_RATIO) return 'cash';
    if (bp >= cash * IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO) return 'margin';
  }
  if (bp != null && excess != null && excess > 0) {
    if (bp >= excess * IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO) return 'margin';
  }
  return 'cash';
}

/** #186: Short side is hidden on Cash. */
export function shortSideVisible(summary: IbkrAccountSummary | null): boolean {
  if (!summary?.connected) return false;
  return classifyMarginKind(summary) === 'margin';
}
