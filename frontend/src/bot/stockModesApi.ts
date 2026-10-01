/**
 * `GET /api/stock-mode` for the Bots page's Who trades card (ADR 037, ADR 042 F):
 * every stock not at Signal only on the desk venue -- Bot, Auto-entry, Approve --
 * with the notes that keep Nova from acting on it. Read-only here; the switch
 * itself lives above each stock's Level 2. A row the wire does not describe is
 * dropped, never guessed into a mode; an unreadable answer throws its reason.
 */
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';

export type StockModeName = 'signal' | 'approve' | 'auto_entry' | 'bot';

export interface StockModeNote {
  id: string;
  tone: 'info' | 'warn';
  text: string;
}

export interface StockModeRow {
  symbol: string;
  mode: StockModeName;
  venue: string | null;
  /** Why Nova cannot take buying now (the Live lock, a replay desk); null when it can. */
  buyLock: string | null;
  /** Every condition that keeps Nova from acting on it, not only the first. */
  notes: StockModeNote[];
  /** Approve's plan: waiting / sent / withdrawn. */
  approval: string | null;
  /** The trade Nova holds on it: entering / holding / closed / missed / handed. */
  trade: { state: string; qty: number | null; setupType: string | null } | null;
  lastEvent: { ts: number; tone: string; text: string } | null;
  /** What Nova would send for the stock's current plan, in words. */
  size: string | null;
}

const MODES: ReadonlySet<string> = new Set<StockModeName>(['signal', 'approve', 'auto_entry', 'bot']);

function obj(v: unknown): Record<string, unknown> | null {
  return v != null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v.trim().replace(/ -- /g, ' — ') : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function parseStockModeRow(raw: unknown): StockModeRow | null {
  const v = obj(raw);
  if (!v || typeof v.symbol !== 'string' || typeof v.mode !== 'string' || !MODES.has(v.mode)) return null;
  const locks = obj(v.locks);
  const trade = obj(v.trade);
  const event = obj(v.last_event);
  const size = obj(v.size);
  const notes = (Array.isArray(v.notes) ? v.notes : []).flatMap((n): StockModeNote[] => {
    const row = obj(n);
    if (!row || typeof row.text !== 'string') return [];
    return [{ id: String(row.id ?? ''), tone: row.tone === 'warn' ? 'warn' : 'info', text: row.text.replace(/ -- /g, ' — ') }];
  });
  return {
    symbol: v.symbol.toUpperCase(),
    mode: v.mode as StockModeName,
    venue: str(v.venue),
    // A view without its locks reads locked: Nova never looks free to buy by omission.
    buyLock: locks && locks.buy === null ? null : str(locks?.buy) ?? 'The desk could not read whether Nova may buy it.',
    notes,
    approval: str(obj(v.approval)?.state),
    trade: trade && typeof trade.state === 'string'
      ? { state: trade.state, qty: num(trade.qty), setupType: str(trade.setup_type) }
      : null,
    lastEvent: event && typeof event.text === 'string'
      ? { ts: num(event.ts) ?? 0, tone: String(event.tone ?? 'info'), text: event.text.replace(/ -- /g, ' — ') }
      : null,
    size: size ? str(size.text) : null,
  };
}

/** `{stocks: [...]}` -> the rows, or null when the container is not one. */
export function parseStockModes(body: unknown): StockModeRow[] | null {
  const b = obj(body);
  if (!b || !Array.isArray(b.stocks)) return null;
  return b.stocks.map(parseStockModeRow).filter((r): r is StockModeRow => r != null);
}

export async function fetchStockModes(): Promise<StockModeRow[]> {
  const res = await novaFetch(`${API_URL}/stock-mode`);
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = obj(body)?.detail;
    const words = typeof detail === 'string' ? detail : str(obj(detail)?.error);
    throw new Error(words ?? `HTTP ${res.status}`);
  }
  const rows = parseStockModes(body);
  if (!rows) throw new Error(`an unreadable answer (HTTP ${res.status})`);
  return rows;
}
