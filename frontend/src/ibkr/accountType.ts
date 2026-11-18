/**
 * Cash vs Margin class -- SSOT for the header chip (#181) and ticket Short (#186).
 *
 * TWS AccountType is ownership (INDIVIDUAL / LLC / IRA). A connected snapshot
 * is always cash or margin. Short is visible only on margin.
 * Prefer stamped `account_class` from GET /api/ibkr/account (includes env).
 * Unstamped: IBKR's TradingType-S word (STKCASH / STKMRGN), then leverage --
 * the figures only ever prove margin. Mirror backend/ibkr/account_class.py.
 */
import { IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO } from '../constantGroups/ibkr_account';
import type { IbkrAccountSummary } from './types';

export type AccountTypeKind = 'cash' | 'margin' | 'unknown';

const CASH_TOKENS = new Set(['CASH', 'CASH ACCOUNT', 'STKCASH']);
const MARGIN_TOKENS = new Set([
  'MARGIN',
  'MRGN',
  'STKMRGN',
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
  if (bp == null) return 'cash';
  // A held short's proceeds sit in cash, so "buying power under cash" never proves a cash account.
  for (const base of [asFinite(summary.ExcessLiquidity), asFinite(summary.TotalCashValue)]) {
    if (base != null && base > 0 && bp >= base * IBKR_ACCOUNT_CLASS_MARGIN_MIN_BP_RATIO) return 'margin';
  }
  return 'cash';
}

/** #186: Short side is hidden on Cash. On Live (a summary IBKR stamped with its own class) it follows
 * IBKR's figures alone: the .env override never gives Live a Short side (ADR 048 step 6). */
export function shortSideVisible(summary: IbkrAccountSummary | null): boolean {
  if (!summary?.connected) return false;
  if (summary.ibkr_account_class != null) return summary.ibkr_account_class === 'margin';
  return classifyMarginKind(summary) === 'margin';
}
