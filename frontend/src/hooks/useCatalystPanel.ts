/**
 * Polls `GET /api/catalysts/{symbol}` (ADR 024) for the Trader's News panel: the verdict on the
 * symbol's news since the prior close and every item read, each labelled -- so news that drops
 * while the ticker is open shows up without reopening it. The sample desk reads nothing live and
 * keeps its sample headlines (`unavailable`).
 */
import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL, CATALYST_PANEL_PATH, CATALYST_PANEL_POLL_MS } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { CatalystItem, CatalystPanel } from '../types/catalystVerdict';
import { normalizeCatalystVerdict } from '../utils/catalystVerdict';

export interface CatalystPanelState {
  panel: CatalystPanel | null;
  loading: boolean;
  /** True when this desk cannot read the panel (sample desk, or an API without the route). */
  unavailable: boolean;
  /** The last read's failure, shown in the panel; the last good answer stays on screen. */
  error: string | null;
}

const KINDS: ReadonlySet<string> = new Set(['catalyst', 'negative', 'routine', 'noise']);

function normalizeItem(raw: unknown): CatalystItem | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const ts = r.published_ts;
  if (typeof ts !== 'number' || !Number.isFinite(ts) || typeof r.kind !== 'string' || !KINDS.has(r.kind)) return null;
  const str = (v: unknown) => (typeof v === 'string' && v ? v : null);
  return {
    item_id: str(r.item_id),
    source: str(r.source),
    publisher: str(r.publisher),
    published_ts: ts,
    title: str(r.title),
    url: str(r.url),
    kind: r.kind as CatalystItem['kind'],
    category: str(r.category) ?? '',
    strength: r.strength === 'strong' || r.strength === 'weak' ? r.strength : null,
    dilution: r.dilution === true,
  };
}

/** The panel payload off the wire; null when it is not one. */
export function normalizeCatalystPanel(raw: unknown): CatalystPanel | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.symbol !== 'string' || !Array.isArray(r.items)) return null;
  const items = r.items.map(normalizeItem).filter((i): i is CatalystItem => i !== null);
  const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : 0);
  return {
    schema_version: num(r.schema_version),
    symbol: r.symbol,
    generated_at: num(r.generated_at),
    window_start: num(r.window_start),
    verdict: normalizeCatalystVerdict(r.verdict),
    items,
    items_total: typeof r.items_total === 'number' ? r.items_total : items.length,
  };
}

export function useCatalystPanel(symbol: string | null | undefined): CatalystPanelState {
  const sample = useSampleDataOptional();
  const [panel, setPanel] = useState<CatalystPanel | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const sym = (symbol ?? '').trim().toUpperCase();

  useEffect(() => {
    setPanel(null);
    setUnavailable(false);
    setError(null);
    if (sample || !sym) return;
    let cancelled = false;
    setLoading(true);

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const res = await fetch(`${API_BASE_URL}${CATALYST_PANEL_PATH}/${encodeURIComponent(sym)}`);
        if (res.status === 404) {
          if (!cancelled) setUnavailable(true);  // an API from before the route: keep the old panel
          return;
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = normalizeCatalystPanel(await res.json());
        if (!body) throw new Error('not a news payload');
        if (!cancelled && body.symbol === sym) {
          setPanel(body);
          setError(null);
        }
      } catch (e) {
        // Keep the last answer; a transient failure is not "no news".
        if (!cancelled) setError(`News read failed: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        inFlight.current = false;
        if (!cancelled) setLoading(false);
      }
    }

    void poll();
    const id = window.setInterval(() => void poll(), CATALYST_PANEL_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [sample, sym]);

  if (sample) return { panel: null, loading: false, unavailable: true, error: null };
  return { panel, loading, unavailable, error };
}
