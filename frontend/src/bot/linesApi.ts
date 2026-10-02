/**
 * IBKR's three Level 2 lines and the lending switch (ADR 043): `GET /api/ibkr/depth/lines`, `PATCH
 * /api/ibkr/depth/lending`. The switch changes who may take a line from a hidden Trader tab, so it carries
 * the desk's API key; the sample desk refuses it before any request.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

export type LineHolder = 'tab' | 'record' | 'auto_record' | 'loan' | 'replay';
export interface DepthLine { symbol: string; heldBy: LineHolder; front: boolean | null; viewers: number }
export interface LineLoan { lender: string; borrower: string; setupType: string | null; since: number | null; why: string | null }
export interface LineLoanEnded { lender: string; borrower: string; since: number | null; ended: number | null; end: string | null }
export interface LinesView {
  cap: number;
  lines: DepthLine[];
  lending: { on: boolean; loans: LineLoan[]; recent: LineLoanEnded[] };
}

const obj = (v: unknown): Record<string, unknown> | null =>
  (v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const HOLDERS = new Set<LineHolder>(['tab', 'record', 'auto_record', 'loan', 'replay']);

export function parseLines(raw: unknown): LinesView | null {
  const r = obj(raw);
  const lending = obj(r?.lending);
  if (!r || r.schema_version !== 1 || !Array.isArray(r.lines) || !lending) return null;
  const lines: DepthLine[] = [];
  for (const l of r.lines as unknown[]) {
    const o = obj(l);
    const symbol = str(o?.symbol)?.toUpperCase();
    if (!o || !symbol) continue;
    const held = String(o.held_by ?? '') as LineHolder;
    lines.push({ symbol, heldBy: HOLDERS.has(held) ? held : 'tab', front: typeof o.front === 'boolean' ? o.front : null,
      viewers: num(o.viewers) ?? 0 });
  }
  const loans = (Array.isArray(lending.loans) ? lending.loans : []).map(obj).filter(Boolean).map(x => ({
    lender: str(x!.lender) ?? '', borrower: str(x!.borrower) ?? '', setupType: str(x!.setup_type),
    since: num(x!.since), why: str(x!.why),
  }));
  const recent = (Array.isArray(lending.recent) ? lending.recent : []).map(obj).filter(Boolean).map(x => ({
    lender: str(x!.lender) ?? '', borrower: str(x!.borrower) ?? '', since: num(x!.since), ended: num(x!.ended),
    end: str(x!.end),
  }));
  return { cap: num(r.cap) ?? 3, lines, lending: { on: lending.on !== false, loans, recent } };
}

async function read(res: Response): Promise<LinesView> {
  if (res.status === 404) throw new Error('This backend cannot say who holds the Level 2 lines yet: reload the backend after the update.');
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = obj(body)?.detail;
    const error = typeof detail === 'string' ? detail : str(obj(detail)?.error);
    throw new Error(error ?? `The desk answered ${res.status}.`);
  }
  const view = parseLines(body);
  if (!view) throw new Error('The Level 2 lines answered in a shape this desk does not read.');
  return view;
}

export async function fetchLines(): Promise<LinesView> {
  return read(await novaFetch(`${API_BASE_URL}/api/ibkr/depth/lines`));
}

export async function setLending(on: boolean): Promise<LinesView> {
  if (onSampleDesk()) throw new Error(SAMPLE_WRITE_REFUSAL);
  return read(await novaFetch(`${API_BASE_URL}/api/ibkr/depth/lending`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on }),
  }));
}
