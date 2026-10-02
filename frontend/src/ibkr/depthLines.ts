/**
 * The Level 2 lines and their loans (ADR 043 decision 6): `GET /api/ibkr/depth/lines` and
 * `PATCH /api/ibkr/depth/lending`. A Trader tab whose line is lent polls the view to know when
 * the loan ended (useIbkrDepth); the Bots page draws it. Unknown fields are dropped, a malformed
 * row is skipped, and nothing is invented: a missing value stays null.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constantGroups/chart_api';
import { L2_DEPTH_LENDING_PATH, L2_DEPTH_LINES_PATH } from '../constantGroups/market_ui';

export type DepthLineHolder = 'tab' | 'record' | 'auto_record' | 'loan' | 'replay';

export interface DepthLine {
  symbol: string;
  held_by: DepthLineHolder;
  /** A visible window shows the symbol's Trader tab; null while the focus is unknown. */
  front: boolean | null;
  viewers: number;
}

export interface DepthLoan {
  lender: string;
  borrower: string;
  setup_type: string | null;
  setup_id: string | null;
  since: number | null;
  /** Why the line went, in words ("near its trigger"). */
  why: string | null;
  /** The same reason as a code: trade | near | armed. */
  tier: string | null;
  text: string | null;
}

export interface DepthLoanEnded {
  lender: string;
  borrower: string;
  since: number | null;
  ended: number | null;
  end: string | null;
  text: string | null;
}

export interface DepthLinesView {
  schema_version: number;
  cap: number | null;
  lines: DepthLine[];
  lending: { on: boolean; loans: DepthLoan[]; recent: DepthLoanEnded[]; error: string | null };
}

const HOLDERS: readonly DepthLineHolder[] = ['tab', 'record', 'auto_record', 'loan', 'replay'];

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function rows(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? v.filter((r): r is Record<string, unknown> => r != null && typeof r === 'object') : [];
}

/** The view as the desk reads it; null when the answer is not one. */
export function normalizeDepthLines(raw: unknown): DepthLinesView | null {
  if (raw == null || typeof raw !== 'object') return null;
  const body = raw as Record<string, unknown>;
  const lending = (body.lending ?? {}) as Record<string, unknown>;
  if (typeof body.schema_version !== 'number' || !Array.isArray(body.lines)) return null;
  const lines: DepthLine[] = rows(body.lines).flatMap((r) => {
    const symbol = str(r.symbol);
    const held = HOLDERS.includes(r.held_by as DepthLineHolder) ? (r.held_by as DepthLineHolder) : null;
    if (!symbol || !held) return [];
    return [{ symbol, held_by: held, front: typeof r.front === 'boolean' ? r.front : null, viewers: num(r.viewers) ?? 0 }];
  });
  const loans: DepthLoan[] = rows(lending.loans).flatMap((r) => {
    const lender = str(r.lender);
    const borrower = str(r.borrower);
    if (!lender || !borrower) return [];
    return [{
      lender: lender.toUpperCase(), borrower: borrower.toUpperCase(), setup_type: str(r.setup_type),
      setup_id: str(r.setup_id), since: num(r.since), why: str(r.why), tier: str(r.tier), text: str(r.text),
    }];
  });
  const recent: DepthLoanEnded[] = rows(lending.recent).flatMap((r) => {
    const lender = str(r.lender);
    const borrower = str(r.borrower);
    if (!lender || !borrower) return [];
    return [{ lender, borrower, since: num(r.since), ended: num(r.ended), end: str(r.end), text: str(r.text) }];
  });
  return {
    schema_version: body.schema_version,
    cap: num(body.cap),
    lines,
    lending: { on: lending.on === true, loans, recent, error: str(lending.error) },
  };
}

/** The loan that took ``symbol``'s line, if one stands. */
export function loanFor(view: DepthLinesView, symbol: string): DepthLoan | null {
  const sym = symbol.toUpperCase();
  return view.lending.loans.find((l) => l.lender === sym) ?? null;
}

/** What a lent tab's poll learned: the loan still stands, it ended, or the answer could not be read. */
export type LoanPoll = { kind: 'standing'; loan: DepthLoan } | { kind: 'ended' } | { kind: 'unknown' };

export async function pollLoan(symbol: string, signal?: AbortSignal): Promise<LoanPoll> {
  try {
    const res = await novaFetch(`${API_BASE_URL}${L2_DEPTH_LINES_PATH}`, { signal });
    // A backend without the route lends nothing, so no loan stands.
    if (res.status === 404) return { kind: 'ended' };
    if (!res.ok) return { kind: 'unknown' };
    const view = normalizeDepthLines(await res.json());
    if (!view) return { kind: 'unknown' };
    const loan = loanFor(view, symbol);
    return loan ? { kind: 'standing', loan } : { kind: 'ended' };
  } catch {
    return { kind: 'unknown' };
  }
}

export async function fetchDepthLines(signal?: AbortSignal): Promise<DepthLinesView | null> {
  const res = await novaFetch(`${API_BASE_URL}${L2_DEPTH_LINES_PATH}`, { signal });
  if (!res.ok) throw new Error(`GET ${L2_DEPTH_LINES_PATH} answered ${res.status}`);
  return normalizeDepthLines(await res.json());
}

/** Line lending on or off; answers the lines view. */
export async function setDepthLending(on: boolean): Promise<DepthLinesView | null> {
  const res = await novaFetch(`${API_BASE_URL}${L2_DEPTH_LENDING_PATH}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ on }),
  });
  if (!res.ok) throw new Error(`PATCH ${L2_DEPTH_LENDING_PATH} answered ${res.status}`);
  return normalizeDepthLines(await res.json());
}
