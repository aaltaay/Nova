/**
 * The day's LULD band step by step (ADR 047 amendment, operator ask 2026-10-12): the 1-minute chart's line. Pure: the
 * backend's `GET /api/luld/{symbol}/trail` goes in, checked. Each step holds from its `ts` until the next one's (the
 * last until `as_of`); a step without a band (`lower` and `upper` null) is a halt, the close, or no previous close.
 * Live, the steps begin when Nova began holding the stock's tape (`watching_since`); on a Sim replay they come from the
 * recording, never past the playhead.
 */
import { LULD_SCHEMA_VERSION } from '../constantGroups/luld';
import type { LuldState } from './luld';

export interface LuldStep {
  ts: number;
  lower: number | null;
  upper: number | null;
  /** False where Nova did not see the stock open or reopen with its tape unbroken since. */
  exact: boolean;
}

export interface LuldTrail {
  schema_version: number;
  symbol: string;
  source: 'live' | 'replay';
  state: LuldState;
  reason: string | null;
  /** False when every step's percentage rests on Nova's guess of the tier (no index list; over $3.00). */
  tier_sure: boolean;
  watching_since: number | null;
  steps: LuldStep[];
  as_of: number;
}

function num(x: unknown): number | null {
  return typeof x === 'number' && Number.isFinite(x) ? x : null;
}

/** A version-1 trail, its steps in time order; null for anything else. */
export function readLuldTrail(raw: unknown): LuldTrail | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const asOf = num(r.as_of);
  if (r.schema_version !== LULD_SCHEMA_VERSION || typeof r.symbol !== 'string' || typeof r.state !== 'string'
    || !Array.isArray(r.steps) || asOf === null) return null;
  const steps: LuldStep[] = [];
  for (const s of r.steps as unknown[]) {
    if (!s || typeof s !== 'object') continue;
    const o = s as Record<string, unknown>;
    const ts = num(o.ts);
    if (ts === null || (steps.length > 0 && ts < steps[steps.length - 1].ts)) continue;
    steps.push({ ts, lower: num(o.lower), upper: num(o.upper), exact: o.exact === true });
  }
  return {
    schema_version: LULD_SCHEMA_VERSION,
    symbol: r.symbol.toUpperCase(),
    source: r.source === 'replay' ? 'replay' : 'live',
    state: r.state as LuldState,
    reason: typeof r.reason === 'string' ? r.reason : null,
    tier_sure: r.tier_sure !== false,
    watching_since: num(r.watching_since),
    steps,
    as_of: asOf,
  };
}
