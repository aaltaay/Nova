/**
 * Each Market block's 1 D / 7 D / 30 D switch, remembered on the desk across restarts (ADR 053, operator pick
 * 2026-10-13: "each block remembers its last choice").
 *
 * Owner: this module. Key `nova.marketBoard.periods.v1`, shape `{schema_version: 1, sectors, industries,
 * climate, top: {kind, period}}` (architecture/schema/market-board.md). Invalidation: an unknown schema_version,
 * or any value that is not a known period / kind, falls back to 1 D / movers for that field -- never migrated by
 * guesswork. The sample desk never writes it.
 */
import { useCallback, useState } from 'react';
import {
  MARKET_PERIODS,
  MARKET_PERIODS_SCHEMA_VERSION,
  MARKET_PERIODS_STORAGE_KEY,
  MARKET_TOP_KINDS,
} from './constants';
import type { BlockPeriods, Period, TopKind } from './types';

export const DEFAULT_PERIODS: BlockPeriods = {
  sectors: '1D',
  industries: '1D',
  climate: '1D',
  top: { kind: 'movers', period: '1D' },
};

function period(value: unknown): Period {
  return (MARKET_PERIODS as readonly unknown[]).includes(value) ? (value as Period) : '1D';
}

function kind(value: unknown): TopKind {
  return (MARKET_TOP_KINDS as readonly unknown[]).includes(value) ? (value as TopKind) : 'movers';
}

export function parsePeriods(raw: unknown): BlockPeriods {
  if (!raw || typeof raw !== 'object') return DEFAULT_PERIODS;
  const r = raw as Record<string, unknown>;
  if (r.schema_version !== MARKET_PERIODS_SCHEMA_VERSION) return DEFAULT_PERIODS;
  const top = (r.top && typeof r.top === 'object' ? r.top : {}) as Record<string, unknown>;
  return {
    sectors: period(r.sectors),
    industries: period(r.industries),
    climate: period(r.climate),
    top: { kind: kind(top.kind), period: period(top.period) },
  };
}

export function readPeriods(): BlockPeriods {
  try {
    const text = window.localStorage.getItem(MARKET_PERIODS_STORAGE_KEY);
    return text ? parsePeriods(JSON.parse(text)) : DEFAULT_PERIODS;
  } catch {
    return DEFAULT_PERIODS; // storage blocked or the value unreadable: the defaults, said nowhere else
  }
}

export function writePeriods(p: BlockPeriods): void {
  try {
    window.localStorage.setItem(
      MARKET_PERIODS_STORAGE_KEY,
      JSON.stringify({ schema_version: MARKET_PERIODS_SCHEMA_VERSION, ...p }),
    );
  } catch {
    // storage blocked (private window, a quota): the switch still works for this session
  }
}

/** The blocks' switches and a setter that remembers them (`persist` false on the sample desk). */
export function useBlockPeriods(persist: boolean): [BlockPeriods, (next: BlockPeriods) => void] {
  const [periods, setPeriods] = useState<BlockPeriods>(() => (persist ? readPeriods() : DEFAULT_PERIODS));
  const set = useCallback(
    (next: BlockPeriods) => {
      setPeriods(next);
      if (persist) writePeriods(next);
    },
    [persist],
  );
  return [periods, set];
}
