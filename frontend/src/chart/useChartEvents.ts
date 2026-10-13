/**
 * One symbol's earnings and split marks (`GET /api/chart-events/{symbol}`), for the daily panes. Panes on
 * one symbol share a read: kept in memory by symbol, asked again after `CHART_EVENTS_REFRESH_MS`, and every
 * `CHART_EVENTS_RETRY_MS` while the desk is still reading (a foreign issuer's 6-Ks), at most
 * `CHART_EVENTS_MAX_RETRIES` times. A failed ask keeps what was held and says why in `notes`. A new newest
 * candle asks again at once: a Sim replay that moved on to a later day is answered up to its playhead.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  CHART_EVENTS_MAX_RETRIES,
  CHART_EVENTS_PATH,
  CHART_EVENTS_REFRESH_MS,
  CHART_EVENTS_RETRY_MS,
} from './chartEventConstants';
import { EMPTY_CHART_EVENTS, normalizeChartEvents, type ChartEventsRead } from './chartEvents';

interface Held {
  read: ChartEventsRead;
  at: number;
  /** The newest candle's day when it was asked. */
  newest: string | null;
  inflight: Promise<ChartEventsRead> | null;
}

const held = new Map<string, Held>();

/** Read the symbol's marks from the desk; shares an ask already in flight. */
export function fetchChartEvents(symbol: string, newest: string | null = null): Promise<ChartEventsRead> {
  const entry = held.get(symbol);
  if (entry?.inflight) return entry.inflight;
  const ask = novaFetch(`${API_BASE_URL}${CHART_EVENTS_PATH}/${encodeURIComponent(symbol)}`)
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return normalizeChartEvents(await res.json(), symbol);
    })
    .catch((err: unknown) => {
      const before = held.get(symbol)?.read ?? { ...EMPTY_CHART_EVENTS, symbol };
      const why = err instanceof Error ? err.message : String(err);
      return { ...before, busy: false, notes: [...before.notes.filter((n) => !n.startsWith('The desk did not answer')),
        `The desk did not answer for earnings and splits (${why}).`] };
    })
    .then((read) => {
      held.set(symbol, { read, at: Date.now(), newest, inflight: null });
      return read;
    });
  held.set(symbol, { read: entry?.read ?? { ...EMPTY_CHART_EVENTS, symbol }, at: entry?.at ?? 0, newest, inflight: ask });
  return ask;
}

/** Tests: forget every read. */
export function resetChartEventsForTests(): void {
  held.clear();
}

export function useChartEvents(symbol: string | null, newest: string | null): ChartEventsRead {
  const sym = (symbol ?? '').trim().toUpperCase();
  const [read, setRead] = useState<ChartEventsRead>(() => (sym ? held.get(sym)?.read : null) ?? EMPTY_CHART_EVENTS);

  useEffect(() => {
    if (!sym) {
      setRead(EMPTY_CHART_EVENTS);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let tries = 0;
    const entry = held.get(sym);
    setRead(entry?.read ?? { ...EMPTY_CHART_EVENTS, symbol: sym });

    const ask = () => {
      fetchChartEvents(sym, newest).then((next) => {
        if (cancelled) return;
        setRead(next);
        tries += 1;
        const wait = next.busy && tries < CHART_EVENTS_MAX_RETRIES ? CHART_EVENTS_RETRY_MS : CHART_EVENTS_REFRESH_MS;
        timer = setTimeout(ask, wait);
      });
    };
    const age = entry && !entry.inflight ? Date.now() - entry.at : Infinity;
    if (entry && !entry.read.busy && entry.newest === newest && age < CHART_EVENTS_REFRESH_MS) {
      timer = setTimeout(ask, CHART_EVENTS_REFRESH_MS - age);
    } else {
      ask();
    }
    return () => {
      cancelled = true;
      if (timer != null) clearTimeout(timer);
    };
  }, [sym, newest]);

  return read;
}
