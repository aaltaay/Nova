/**
 * The account's day P&L the loss breakers compare (GET /api/bot/pnl, owner
 * backend bot/day_pnl.py): -$50 trips the bot, -$200 locks the day. Polled
 * while the Bots page is up; `null` when the backend has no figure (unknown,
 * never $0). The sample desk has no bot and polls nothing (V4).
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_URL } from '../constantGroups/chart_api';
import { BOTS_BOT_PNL_POLL_MS } from '../constantGroups/bots_page';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';

export interface BotDayPnl {
  pnl: number | null;
  error: string | null;
}

/** `{day_pnl}` -> the number, or null when it is absent or not finite. */
export function readBotDayPnl(body: unknown): number | null {
  if (!body || typeof body !== 'object') return null;
  const value = (body as { day_pnl?: unknown }).day_pnl;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function useBotDayPnl(enabled = true): BotDayPnl {
  const [state, setState] = useState<BotDayPnl>({ pnl: null, error: null });

  useEffect(() => {
    if (!enabled || onSampleDesk()) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const res = await novaFetch(`${API_URL}/bot/pnl`);
        if (!res.ok) throw new Error(`Bot P&L: HTTP ${res.status}`);
        const pnl = readBotDayPnl(await res.json());
        if (!cancelled) setState({ pnl, error: null });
      } catch (err) {
        if (!cancelled) setState(prev => ({ pnl: prev.pnl, error: err instanceof Error ? err.message : String(err) }));
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
