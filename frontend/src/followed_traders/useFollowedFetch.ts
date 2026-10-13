/**
 * The page's other reads: each trader's Week / All record (`/record`, asked again every
 * FOLLOWED_RECORD_REFRESH_MS while it shows, since exits fill in as IBKR is read) and one trade's reads (`/reads`,
 * asked once). A failed read says why; nothing is filled in. Schema: architecture/schema/followed-traders.md.
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import {
  FOLLOWED_READS_PATH,
  FOLLOWED_RECORD_PATH,
  FOLLOWED_RECORD_REFRESH_MS,
  FOLLOWED_SCHEMA_VERSION,
} from './constants';
import type { FollowedReads, FollowedRecords, RecordRange } from './types';

export interface Fetched<T> {
  data: T | null;
  error: string | null;
}

async function getJson<T extends { schema_version: number }>(path: string): Promise<T> {
  const res = await novaFetch(`${API_BASE_URL}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = (await res.json()) as T;
  if (!body || body.schema_version !== FOLLOWED_SCHEMA_VERSION) throw new Error('the answer is not one this desk can read');
  return body;
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function recordPath(range: RecordRange, date: string | null): string {
  const q = new URLSearchParams({ range });
  if (date) q.set('date', date);
  return `${FOLLOWED_RECORD_PATH}?${q.toString()}`;
}

/** The record over `range` ending on `date`; asks nothing for `day` (the day's own answer has it). */
export function useFollowedRecord(range: RecordRange, date: string | null): Fetched<FollowedRecords> {
  const [state, setState] = useState<Fetched<FollowedRecords>>({ data: null, error: null });
  useEffect(() => {
    setState({ data: null, error: null });
    if (range === 'day') return undefined;
    let cancelled = false;
    let timer: number | undefined;
    const read = async () => {
      try {
        const body = await getJson<FollowedRecords>(recordPath(range, date));
        if (!cancelled) setState({ data: body, error: null });
      } catch (e) {
        if (!cancelled) setState((s) => ({ ...s, error: message(e) }));
      }
      if (!cancelled) timer = window.setTimeout(() => void read(), FOLLOWED_RECORD_REFRESH_MS);
    };
    void read();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [range, date]);
  return state;
}

export function readsPath(date: string, trader: string, fromTs: number, toTs: number): string {
  const q = new URLSearchParams({ date, trader, from_ts: String(fromTs), to_ts: String(toTs) });
  return `${FOLLOWED_READS_PATH}?${q.toString()}`;
}

/** What the feed read off `trader`'s slot from `fromTs` to `toTs`, asked once per window. */
export function useFollowedReads(date: string, trader: string, fromTs: number, toTs: number): Fetched<FollowedReads> {
  const [state, setState] = useState<Fetched<FollowedReads>>({ data: null, error: null });
  useEffect(() => {
    let cancelled = false;
    setState({ data: null, error: null });
    getJson<FollowedReads>(readsPath(date, trader, fromTs, toTs))
      .then((body) => { if (!cancelled) setState({ data: body, error: null }); })
      .catch((e: unknown) => { if (!cancelled) setState({ data: null, error: message(e) }); });
    return () => { cancelled = true; };
  }, [date, trader, fromTs, toTs]);
  return state;
}
