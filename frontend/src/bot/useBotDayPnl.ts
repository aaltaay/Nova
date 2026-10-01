/**
 * The account's day P&L the loss breakers compare (GET /api/bot/pnl, owner backend
 * bot/day_pnl.py), with the parts it is made of, so the breakers card can show the
 * exact figure and how it was reached (ADR 042 D). Polled while the Bots page is up;
 * `null` when the backend has no figure (unknown, never $0). The sample desk has no bot
 * and polls nothing (V4).
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { BOTS_BOT_PNL_POLL_MS } from '../constantGroups/bots_page';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

export interface BotDayPnl {
  pnl: number | null;
  error: string | null;
  /** How the figure was reached, in words; null before the backend answered. */
  parts: string | null;
}

/** `{day_pnl}` -> the number, or null when it is absent or not finite. */
export function readBotDayPnl(body: unknown): number | null {
  if (!body || typeof body !== 'object') return null;
  const value = (body as { day_pnl?: unknown }).day_pnl;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function num(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function usd(v: number): string {
  const text = Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v < 0 ? '−' : ''}$${text}`;
}

/**
 * The meter in words: the practice ledger's own day P&L on Paper and Sim; realized +
 * unrealized − the session's commissions on Live; and, when the commissions cannot be
 * read, the figure before them -- the day is at least that bad, and the breakers still
 * trip on it. Null when the meter says nothing.
 */
export function dayPnlParts(body: unknown): string | null {
  const meter = body && typeof body === 'object' ? (body as { meter?: unknown }).meter : null;
  if (!meter || typeof meter !== 'object') return null;
  const m = meter as Record<string, unknown>;
  if (typeof m.error === 'string' && m.error) return `The account could not be read: ${m.error}`;
  if (m.source === 'practice_ledger_day_pnl') {
    return 'The practice ledger\'s day P&L: net liquidation less the 04:00 ET equity, every fee already paid.';
  }
  const realized = num(m.RealizedPnL);
  const unrealized = num(m.UnrealizedPnL);
  if (m.commissions_unknown === true) {
    const before = num(m.day_pnl_before_commissions);
    return `Commissions unreadable${typeof m.commissions_error === 'string' ? ` (${m.commissions_error})` : ''}: `
      + `before commissions the day is ${before == null ? 'unknown' : usd(before)} — the breakers still trip on that.`;
  }
  const commissions = num(m.commissions);
  if (realized == null && unrealized == null) return null;
  const sum = `realized ${usd(realized ?? 0)} + unrealized ${usd(unrealized ?? 0)}`;
  return commissions == null ? sum : `${sum} − commissions ${usd(Math.abs(commissions))}`;
}

export function useBotDayPnl(enabled = true): BotDayPnl {
  const [state, setState] = useState<BotDayPnl>({ pnl: null, error: null, parts: null });

  useEffect(() => {
    if (!enabled || onSampleDesk()) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const res = await novaFetch(`${API_URL}/bot/pnl`);
        if (!res.ok) throw new Error(`Bot P&L: HTTP ${res.status}`);
        const body: unknown = await res.json();
        if (!cancelled) setState({ pnl: readBotDayPnl(body), error: null, parts: dayPnlParts(body) });
      } catch (err) {
        if (!cancelled) setState(prev => ({ ...prev, error: err instanceof Error ? err.message : String(err) }));
      }
    }
    void poll();
    const id = window.setInterval(() => void poll(), BOTS_BOT_PNL_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled]);

  return state;
}
