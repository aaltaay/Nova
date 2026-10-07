/**
 * The short check, read-only (ADR 048: `GET /api/short-check/{symbol}?qty=&price=&stop=&target=`).
 *
 * The ticket asks it while its Short side is chosen, so the SHORT CHECK box lists every rule the execution
 * door will run -- borrow, SSR, the halt, the hours, the margin cushion with its liquidation price, the buy
 * stop, "you hold none long" and equity -- with their numbers before the operator presses. Level 2 asks it
 * for one share to show SSR and the halt cool-off. Asking places nothing. The sample desk asks nothing, and
 * an API from before the route (404) is "not available", never a pass.
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';

export const SHORT_CHECK_PATH = '/api/short-check';
export const SHORT_CHECK_TICKET_POLL_MS = 3000;
export const SHORT_CHECK_CHIP_POLL_MS = 15000;
export const SHORT_CHECK_DEBOUNCE_MS = 350;

export type ShortRuleState = 'ok' | 'bad' | 'unknown' | 'info';

export interface ShortCheckRule {
  id: string;
  label: string;
  ok: boolean;
  state: ShortRuleState;
  text: string;
  code: string | null;
  value: string | null;
  numbers: Record<string, unknown>;
}

export interface ShortSsrFact {
  state: 'on' | 'off' | 'unknown';
  effective_on: boolean | null;
  text: string;
  trigger: number | null;
  prior_close: number | null;
}

export interface ShortHaltFact {
  state: string;
  text: string;
  until: number | null;
}

export interface ShortCheck {
  symbol: string;
  venue: string | null;
  ok: boolean;
  first: { text: string; code: string | null } | null;
  rules: ShortCheckRule[];
  bid: number | null;
  ask: number | null;
  ssr: ShortSsrFact | null;
  halt: ShortHaltFact | null;
  borrowShares: number | null;
}

export interface ShortCheckParams {
  qty: number;
  price?: number | null;
  stop?: number | null;
  target?: number | null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function rec(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

const RULE_STATES: readonly ShortRuleState[] = ['ok', 'bad', 'unknown', 'info'];

export function normalizeShortCheck(raw: unknown): ShortCheck | null {
  const body = rec(raw);
  if (!body || typeof body.symbol !== 'string' || !Array.isArray(body.rules)) return null;
  const rules: ShortCheckRule[] = [];
  for (const r of body.rules) {
    const row = rec(r);
    if (!row || typeof row.id !== 'string') continue;
    const state = RULE_STATES.includes(row.state as ShortRuleState) ? (row.state as ShortRuleState) : 'unknown';
    rules.push({
      id: row.id, label: str(row.label) || row.id, ok: row.ok === true, state, text: str(row.text),
      code: typeof row.code === 'string' ? row.code : null, value: typeof row.value === 'string' ? row.value : null,
      numbers: rec(row.numbers) ?? {},
    });
  }
  const facts = rec(body.facts) ?? {};
  const ssr = rec(facts.ssr);
  const halt = rec(facts.halt);
  const borrow = rec(facts.borrow);
  const first = rec(body.first);
  return {
    symbol: body.symbol,
    venue: typeof body.venue === 'string' ? body.venue : null,
    ok: body.ok === true,
    first: first ? { text: str(first.text), code: typeof first.code === 'string' ? first.code : null } : null,
    rules,
    bid: num(facts.bid),
    ask: num(facts.ask),
    ssr: ssr ? {
      state: ssr.state === 'on' || ssr.state === 'off' ? ssr.state : 'unknown',
      effective_on: typeof ssr.effective_on === 'boolean' ? ssr.effective_on : null,
      text: str(ssr.text), trigger: num(ssr.trigger), prior_close: num(ssr.prior_close),
    } : null,
    halt: halt ? { state: str(halt.state) || 'unknown', text: str(halt.text), until: num(halt.until) } : null,
    borrowShares: num(borrow?.shares),
  };
}

export function shortCheckUrl(symbol: string, p: ShortCheckParams): string {
  const q = new URLSearchParams({ qty: String(Math.max(1, Math.floor(p.qty))) });
  if (p.price != null && p.price > 0) q.set('price', String(p.price));
  if (p.stop != null && p.stop > 0) q.set('stop', String(p.stop));
  if (p.target != null && p.target > 0) q.set('target', String(p.target));
  return `${SHORT_CHECK_PATH}/${encodeURIComponent(symbol.trim().toUpperCase())}?${q.toString()}`;
}

export interface ShortCheckState {
  check: ShortCheck | null;
  /** The route is not on this backend (404), or this is the sample desk. */
  unavailable: boolean;
  error: string | null;
  loading: boolean;
}

export const SHORT_CHECK_IDLE: ShortCheckState = { check: null, unavailable: false, error: null, loading: false };
export const SHORT_CHECK_UNAVAILABLE_STATE: ShortCheckState = { check: null, unavailable: true, error: null, loading: false };

/** One read of ``path`` (from ``shortCheckUrl``): the check, "not available" on a 404, or a stated error. */
export async function readShortCheck(path: string, signal: AbortSignal): Promise<ShortCheckState> {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, { signal });
    if (res.status === 404) return SHORT_CHECK_UNAVAILABLE_STATE;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const check = normalizeShortCheck(await res.json());
    if (!check) throw new Error('not a short check');
    return { check, unavailable: false, error: null, loading: false };
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    return { check: null, unavailable: false, error: e instanceof Error ? e.message : String(e), loading: false };
  }
}

/** Ask the short check for ``params`` while they are set (null asks nothing), every ``pollMs``. */
export function useShortCheck(symbol: string, params: ShortCheckParams | null, pollMs: number): ShortCheckState {
  const sample = useSampleDataOptional();
  const url = params && symbol.trim() ? shortCheckUrl(symbol, params) : null;
  const [state, setState] = useState<ShortCheckState>(SHORT_CHECK_IDLE);
  const symRef = useRef(symbol.trim().toUpperCase());

  useEffect(() => {
    if (symRef.current !== symbol.trim().toUpperCase()) {
      symRef.current = symbol.trim().toUpperCase();
      setState(SHORT_CHECK_IDLE);
    }
  }, [symbol]);

  useEffect(() => {
    if (sample) {
      setState(SHORT_CHECK_UNAVAILABLE_STATE);
      return;
    }
    if (!url) return;
    let cancelled = false;
    let controller: AbortController | null = null;

    async function read(path: string) {
      controller?.abort();
      controller = new AbortController();
      setState((s) => ({ ...s, loading: true }));
      try {
        const next = await readShortCheck(path, controller.signal);
        if (cancelled) return;
        // A failed read keeps the last check on screen with its error (the door still decides).
        setState((s) => (next.error && s.check ? { ...s, error: next.error, loading: false } : next));
      } catch {
        // maintainer: allow-swallow an aborted read: a newer read, or the unmount, owns the state
      }
    }

    const first = window.setTimeout(() => void read(url), SHORT_CHECK_DEBOUNCE_MS);
    const id = window.setInterval(() => void read(url), pollMs);
    return () => {
      cancelled = true;
      window.clearTimeout(first);
      window.clearInterval(id);
      controller?.abort();
    };
  }, [sample, url, pollMs]);

  return state;
}

/** The rule the margin cushion reads, for its liquidation price and requirement. */
export function marginNumbers(check: ShortCheck | null): { requirement: number | null; liquidation: number | null } {
  const rule = check?.rules.find((r) => r.id === 'cushion') ?? check?.rules.find((r) => r.id === 'margin');
  return { requirement: num(rule?.numbers.requirement), liquidation: num(rule?.numbers.liquidation_price) };
}
