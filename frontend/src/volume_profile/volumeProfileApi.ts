/**
 * The profiles the 5-minute pane draws, read from `GET /api/volume-profile/{symbol}` (ADR 058,
 * `architecture/schema/volume-profile.md`). The backend builds them from IBKR's 1-minute bars: the desk holds one day of
 * them, so yesterday's profile cannot be built here. An empty answer is a stated null with the backend's reason;
 * `filling` means ask again soon.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import type { VolumeProfile } from './volumeProfile';

export type ProfileKind = 'today' | 'yesterday';

/** One row on the wire: `[row's low price, up volume, down volume]`. */
type WireRow = [number, number, number];

export interface VolumeProfileWire {
  schema_version: 1;
  enabled: boolean;
  symbol?: string;
  kind?: ProfileKind;
  day?: string;
  from?: number;
  to?: number;
  source?: string;
  /** Who drew the bars: `ibkr`, `massive` (a Massive Sim replay) or `capture` (a Session Record). */
  feed?: string;
  bars?: number;
  row_size?: number | null;
  low?: number | null;
  high?: number | null;
  total_volume?: number | null;
  poc?: number | null;
  vah?: number | null;
  val?: number | null;
  poc_row?: number | null;
  vah_row?: number | null;
  val_row?: number | null;
  histogram?: WireRow[];
  filling?: boolean;
  error?: string | null;
}

export interface ProfileAnswer {
  profile: VolumeProfile | null;
  /** The backend is still reading the bars (or IBKR's budget said not now): ask again. */
  filling: boolean;
  error: string | null;
  feed: string | null;
}

export function profileToWire(symbol: string, kind: ProfileKind, p: VolumeProfile, source: string, day: string): VolumeProfileWire {
  return {
    schema_version: 1, enabled: true, symbol, kind, day, from: p.from, to: p.to, source,
    row_size: p.rowSize, low: p.low, high: p.high, total_volume: p.total,
    poc: p.poc, vah: p.vah, val: p.val, poc_row: p.pocRow, vah_row: p.vahRow, val_row: p.valRow,
    histogram: p.up.map((u, i): WireRow => [p.low + i * p.rowSize, u, p.down[i]]),
    filling: false, error: null,
  };
}

export function wireToAnswer(w: VolumeProfileWire): ProfileAnswer {
  const filling = !!w.filling;
  const error = w.error ?? null;
  const feed = w.feed ?? null;
  if (!w.enabled || !w.histogram?.length || w.low == null || w.high == null || w.row_size == null
    || w.poc == null || w.vah == null || w.val == null) {
    return { profile: null, filling, error: error ?? (w.enabled ? 'No profile' : null), feed };
  }
  return {
    profile: {
      from: w.from ?? 0, to: w.to ?? 0, low: w.low, high: w.high, rowSize: w.row_size,
      up: w.histogram.map((r) => r[1]), down: w.histogram.map((r) => r[2]),
      total: w.total_volume ?? 0, pocRow: w.poc_row ?? 0, vahRow: w.vah_row ?? 0, valRow: w.val_row ?? 0,
      poc: w.poc, vah: w.vah, val: w.val,
    },
    filling: false,
    error: null,
    feed,
  };
}

/** `day` is the exchange day the pane calls today; `anchor` epoch seconds (today's profile only). */
export async function fetchVolumeProfile(
  symbol: string, kind: ProfileKind, day: string, anchor: number | null, signal: AbortSignal,
): Promise<ProfileAnswer> {
  const q = new URLSearchParams({ kind, day });
  if (anchor != null) q.set('anchor', String(Math.round(anchor)));
  const res = await novaFetch(`${API_BASE_URL}/api/volume-profile/${encodeURIComponent(symbol)}?${q}`, { signal });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = typeof body?.detail === 'string' ? body.detail : `the desk answered ${res.status}`;
    return { profile: null, filling: false, error: `Volume profile: ${detail}`, feed: null };
  }
  return wireToAnswer((await res.json()) as VolumeProfileWire);
}
