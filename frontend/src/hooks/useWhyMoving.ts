/**
 * Polls `GET /api/why/{symbol}` (ADR 028) for the Trader's News panel: the rules read of what drove the
 * move -- news, halts, float turnover, a reverse split, short interest and IBKR's borrow market. The
 * sample desk reads nothing live (`unavailable`), and neither does an API from before the route.
 *
 * On a Sim replay the read is as of the playhead, so the caller passes the playhead (epoch seconds; null off a
 * replay). A rewind, or a move between a replay and the live desk, drops the read on screen at once and reads
 * again -- a read from a later moment is never shown over an earlier playhead, and an answer that was in
 * flight across the rewind is thrown away. Playing forward reads again once the playhead is
 * `WHY_MOVING_REPLAY_REFRESH_SEC` past the last read.
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, WHY_MOVING_PATH, WHY_MOVING_POLL_MS, WHY_MOVING_REPLAY_REFRESH_SEC } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { WhyCheck, WhyCheckState, WhyLikely, WhyMovingRead, WhyPricedBy, WhyReadFacts, WhyStep } from '../types/whyMoving';
import { normalizeCatalystVerdict } from '../utils/catalystVerdict';

export interface WhyMovingState {
  read: WhyMovingRead | null;
  loading: boolean;
  unavailable: boolean;
  /** The last read's failure; the last good answer stays on screen. */
  error: string | null;
}

const STATES: ReadonlySet<string> = new Set<WhyCheckState>(['yes', 'no', 'unknown']);

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function normalizeCheck(raw: unknown): WhyCheck | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id);
  const label = str(r.label);
  if (!id || !label || typeof r.state !== 'string' || !STATES.has(r.state)) return null;
  return {
    id,
    label,
    state: r.state as WhyCheckState,
    value: str(r.value),
    detail: str(r.detail),
    source: str(r.source) ?? '',
    as_of: num(r.as_of),
  };
}

function normalizeLikely(raw: unknown): WhyLikely | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const kind = str(r.kind);
  const label = str(r.label);
  if (!kind || !label) return null;
  return {
    kind,
    label,
    detail: str(r.detail),
    confidence: r.confidence === 'likely' ? 'likely' : 'possible',
    steps: Array.isArray(r.steps) ? r.steps.map(normalizeStep).filter((s): s is WhyStep => s !== null) : [],
  };
}

function normalizeStep(raw: unknown): WhyStep | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const kind = str(r.kind);
  const name = str(r.name);
  if (!kind || !name) return null;
  return { kind, name, fits: typeof r.fits === 'boolean' ? r.fits : null, why: str(r.why) ?? '' };
}

const PRICED_BY: ReadonlySet<string> = new Set<WhyPricedBy>(['board_row', 'last_trade', 'row', 'quote', 'replay']);

function normalizeFacts(raw: unknown): WhyReadFacts {
  const r = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
  const t = r.last_trade && typeof r.last_trade === 'object' ? r.last_trade as Record<string, unknown> : null;
  const tradePrice = num(t?.price);
  const tradeTs = num(t?.ts);
  return {
    board: str(r.board),
    priced_by: typeof r.priced_by === 'string' && PRICED_BY.has(r.priced_by) ? r.priced_by as WhyPricedBy : null,
    price: num(r.price),
    change_pct: num(r.change_pct),
    last_trade: tradePrice != null && tradeTs != null ? { price: tradePrice, change_pct: num(t?.change_pct), ts: tradeTs } : null,
    catalyst: normalizeCatalystVerdict(r.catalyst),
  };
}

/** The read off the wire; null when it is not one. */
export function normalizeWhyMoving(raw: unknown): WhyMovingRead | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const likely = normalizeLikely(r.likely);
  if (typeof r.symbol !== 'string' || !likely || !Array.isArray(r.checks)) return null;
  return {
    schema_version: num(r.schema_version) ?? 0,
    symbol: r.symbol,
    generated_at: num(r.generated_at) ?? 0,
    rules_version: str(r.rules_version) ?? '',
    replay: r.replay === true,
    likely,
    checks: r.checks.map(normalizeCheck).filter((c): c is WhyCheck => c !== null),
    facts: normalizeFacts(r.facts),
  };
}

export function useWhyMoving(symbol: string | null | undefined, playheadSec: number | null = null): WhyMovingState {
  const sample = useSampleDataOptional();
  const [read, setRead] = useState<WhyMovingRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const pending = useRef(false);                // a read asked for while one was in flight
  const generation = useRef(0);                 // bumped by a rewind: an older answer is thrown away
  const askedAt = useRef<number | null>(null);  // the playhead the last read was asked at
  const playhead = useRef(playheadSec);
  const pollNow = useRef<() => void>(() => {});
  const sym = (symbol ?? '').trim().toUpperCase();
  playhead.current = playheadSec;

  useEffect(() => {
    setRead(null);
    setUnavailable(false);
    setError(null);
    if (sample || !sym) return;
    let cancelled = false;
    setLoading(true);

    async function poll() {
      if (inFlight.current) {
        pending.current = true;
        return;
      }
      inFlight.current = true;
      const mine = generation.current;
      askedAt.current = playhead.current;
      try {
        const res = await fetch(`${API_BASE_URL}${WHY_MOVING_PATH}/${encodeURIComponent(sym)}`);
        if (res.status === 404) {
          if (!cancelled) setUnavailable(true);  // an API from before the route: no section
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeWhyMoving(await res.json());
        if (!body) throw new Error('not a move read');
        if (!cancelled && body.symbol === sym && mine === generation.current) {
          setRead(body);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(`Move read failed: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
        if (!cancelled && pending.current) {
          pending.current = false;
          void poll();
        }
      }
    }

    pollNow.current = () => void poll();
    void poll();
    const id = window.setInterval(() => void poll(), WHY_MOVING_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [sample, sym]);

  // The replay's playhead: a rewind or a move between replay and live drops the read and reads again; a
  // playhead a minute past the last read reads again.
  const lastPlayhead = useRef(playheadSec);
  useEffect(() => {
    const prev = lastPlayhead.current;
    lastPlayhead.current = playheadSec;
    if (sample || !sym) return;
    const switched = (prev == null) !== (playheadSec == null);
    if (switched || (playheadSec != null && prev != null && playheadSec < prev)) {
      generation.current += 1;
      setRead(null);
      setLoading(true);
      pollNow.current();
    } else if (playheadSec != null && askedAt.current != null
      && playheadSec - askedAt.current >= WHY_MOVING_REPLAY_REFRESH_SEC) {
      pollNow.current();
    }
  }, [playheadSec, sample, sym]);

  if (sample) return { read: null, loading: false, unavailable: true, error: null };
  return { read, loading, unavailable, error };
}
