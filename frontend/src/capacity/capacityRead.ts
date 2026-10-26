/**
 * What IBKR lets this desk hold, and how much is in use (operator ask, 2026-10-16): `GET /api/ibkr/capacity`, read
 * every few seconds for the strip at the bottom of the desk. An answer this desk cannot read is said as unread,
 * never a guessed count. Schema: architecture/schema/desk-ops.md ("IBKR capacity on the desk").
 */
import { useEffect, useState } from 'react';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { CAPACITY_PATH, CAPACITY_POLL_MS, CAPACITY_READ_TIMEOUT_MS } from './capacityConstants';

export interface CapacityCell {
  used: number;
  /** null: IBKR has not said its cap (Time & Sales). */
  cap: number | null;
  /** Who uses it, largest first: [label, count]. */
  users: [string, number][];
  /** A line under the count, e.g. "next in 2:27". */
  note: string | null;
}

export interface CapacityModel {
  l1: CapacityCell;
  l2: CapacityCell;
  history: CapacityCell;
  tape: CapacityCell;
}

export type CapacityRead = { state: 'loading' } | { state: 'ok'; model: CapacityModel } | { state: 'unread'; why: string };

const OWNER_LABELS: Record<string, string> = {
  scanner: 'Scanner',
  hod: 'HOD Momo',
  detail: 'Trader tabs',
  depth: 'Level 2 books',
  listing: 'Listings',
  followed: 'TraderTV',
  live_trader: 'Live Trader bot',
};

const KIND_LABELS: Record<string, string> = {
  charts: 'Chart bars',
  tape: 'TraderTV exits, ticker checks, LULD',
  daily: 'Daily bars: SSR, Market ETFs, Cryptos',
  market: 'Market page tiles',
  global: 'Global page',
  forex: 'Forex page',
};

const HELD_BY_LABELS: Record<string, string> = { tab: 'Trader tab', auto_record: 'recording', bot: 'bot' };

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function counted(raw: unknown, labels: Record<string, string>): [string, number][] {
  if (!raw || typeof raw !== 'object') return [];
  return Object.entries(raw as Record<string, unknown>)
    .map(([k, v]) => [labels[k] ?? k, num(v) ?? 0] as [string, number])
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
}

/** "2:27" for 147 s. */
export function clock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** The answer as cells, or null when this desk cannot read it. */
export function parseCapacity(body: unknown): CapacityModel | null {
  if (!body || typeof body !== 'object') return null;
  const b = body as Record<string, Record<string, unknown> | undefined> & { schema_version?: unknown };
  if (b.schema_version !== 1 || !b.l1 || !b.l2 || !b.history || !b.tape) return null;
  const { l1, l2, history, tape } = b;
  const l1Used = num(l1.used), l1Cap = num(l1.cap), l2Used = num(l2.used), l2Cap = num(l2.cap);
  const hUsed = num(history.used), hCap = num(history.cap), tUsed = num(tape.used);
  if (l1Used == null || l1Cap == null || l2Used == null || l2Cap == null || hUsed == null || hCap == null || tUsed == null) {
    return null;
  }
  const next = num(history.next_free_sec) ?? 0;
  const l2Users: [string, number][] = Array.isArray(l2.symbols)
    ? (l2.symbols as { symbol?: unknown; held_by?: unknown }[]).map((row) => [
        `${String(row.symbol ?? '?')} (${HELD_BY_LABELS[String(row.held_by)] ?? String(row.held_by ?? '?')})`,
        1,
      ])
    : [];
  const tapeUsers: [string, number][] = Array.isArray(tape.symbols)
    ? (tape.symbols as unknown[]).map((s) => [String(s), 1])
    : [];
  return {
    l1: {
      used: l1Used,
      cap: l1Cap,
      users: counted(l1.by_owner, OWNER_LABELS),
      note: l1.cap_learned === true ? 'cap IBKR set (lines shared with your other platforms)' : null,
    },
    l2: { used: l2Used, cap: l2Cap, users: l2Users, note: null },
    history: {
      used: hUsed,
      cap: hCap,
      users: counted(history.by_kind, KIND_LABELS),
      note: next > 0 ? `next in ${clock(next)}` : null,
    },
    tape: { used: tUsed, cap: num(tape.cap), users: tapeUsers, note: null },
  };
}

/** `ok` under 80% of the cap, `warn` from 80%, `full` at the cap; `ok` when the cap is unknown. */
export function toneOf(cell: CapacityCell): 'ok' | 'warn' | 'full' {
  if (cell.cap == null || cell.cap <= 0) return 'ok';
  if (cell.used >= cell.cap) return 'full';
  return cell.used >= cell.cap * 0.8 ? 'warn' : 'ok';
}

/** Read now and every `pollMs`, one read at a time, each given up after `timeoutMs`. */
export function useCapacity(
  pollMs: number = CAPACITY_POLL_MS,
  fetchImpl: typeof fetch = novaFetch,
  timeoutMs: number = CAPACITY_READ_TIMEOUT_MS,
): CapacityRead {
  const [read, setRead] = useState<CapacityRead>({ state: 'loading' });
  useEffect(() => {
    let cancelled = false;
    let reading = false;
    const pull = async () => {
      if (reading) return;
      reading = true;
      const gaveUp = new AbortController();
      const timer = window.setTimeout(() => gaveUp.abort(), timeoutMs);
      let next: CapacityRead;
      try {
        const res = await fetchImpl(`${API_BASE_URL}${CAPACITY_PATH}`, { cache: 'no-store', signal: gaveUp.signal });
        const body = await res.json().catch(() => null);
        const model = res.ok ? parseCapacity(body) : null;
        const why = (body as { detail?: { why?: unknown } } | null)?.detail?.why;
        next = model
          ? { state: 'ok', model }
          : { state: 'unread', why: typeof why === 'string' ? why : `the backend answered ${res.status}` };
      } catch {
        next = { state: 'unread', why: gaveUp.signal.aborted ? 'the backend did not answer' : 'the backend is not reachable' };
      } finally {
        window.clearTimeout(timer);
        reading = false;
      }
      if (!cancelled) setRead(next);
    };
    void pull();
    const id = window.setInterval(() => void pull(), pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [fetchImpl, pollMs, timeoutMs]);
  return read;
}
