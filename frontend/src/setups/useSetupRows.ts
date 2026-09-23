/**
 * One day's armed setups from the scoreboard store (`GET /api/setups/rows`,
 * ADR 022): when each armed, came near its trigger, triggered, failed or was
 * scored. The Bots page timeline reads them; polled while it is on screen.
 * The sample desk polls nothing (V4).
 */
import { useEffect, useState } from 'react';
import { API_BASE_URL, SETUPS_ROWS_PATH } from '../constants';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import type { TapeVerdict } from './types';

/** A tape read as the store keeps it: the verdict and its reasons. */
export interface StoredTapeRead {
  verdict: TapeVerdict | string | null;
  reasons?: string[] | null;
}

/** One setups.db row (backend setup_scanner/store.py COLUMNS); every unknown is null. */
export interface SetupStoreRow {
  id: string;
  session_date: string;
  symbol: string;
  kind: string | null;
  state: string | null;
  reason: string | null;
  armed_at: number | null;
  trigger: number | null;
  entry_planned: number | null;
  stop: number | null;
  target1: number | null;
  leg_pct: number | null;
  pullback_bars: number | null;
  grade: string | null;
  near_at: number | null;
  near_tape: StoredTapeRead | null;
  triggered_at: number | null;
  entry: number | null;
  trigger_tape: StoredTapeRead | null;
  failed_at: number | null;
  fail_reason: string | null;
  disarmed_at: number | null;
  outcome: string | null;
  outcome_at: number | null;
  bar_r: number | null;
}

export interface SetupRowsState {
  rows: SetupStoreRow[];
  error: string | null;
}

function isRow(value: unknown): value is SetupStoreRow {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return typeof row.id === 'string' && typeof row.symbol === 'string';
}

/** `{rows: [...]}` -> the rows, or null when the body is not one. */
export function readSetupRows(body: unknown): SetupStoreRow[] | null {
  if (!body || typeof body !== 'object') return null;
  const rows = (body as { rows?: unknown }).rows;
  return Array.isArray(rows) ? rows.filter(isRow) : null;
}

export function useSetupRows(date: string | null, pollMs: number): SetupRowsState {
  const [state, setState] = useState<SetupRowsState>({ rows: [], error: null });

  useEffect(() => {
    if (!date || onSampleDesk()) return undefined;
    let cancelled = false;
    async function poll() {
      try {
        const res = await fetch(`${API_BASE_URL}${SETUPS_ROWS_PATH}?date=${encodeURIComponent(date ?? '')}`);
        if (!res.ok) throw new Error(`Setup rows: HTTP ${res.status}`);
        const rows = readSetupRows(await res.json());
        if (!rows) throw new Error('Setup rows: unreadable response');
        if (!cancelled) setState({ rows, error: null });
      } catch (err) {
        if (!cancelled) setState(prev => ({ rows: prev.rows, error: err instanceof Error ? err.message : String(err) }));
      }
    }
    void poll();
    const id = window.setInterval(() => void poll(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [date, pollMs]);

  return state;
}
