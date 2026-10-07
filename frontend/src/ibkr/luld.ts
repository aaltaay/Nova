/**
 * LULD bands on Level 2 (ADR 047). Pure: the depth socket's `luld` frame goes in; the ladder's two band
 * rows, the strip above the book and the hover's words come out.
 *
 * The bands are Nova's calculation from the published Limit Up-Limit Down rules (backend `luld/`), not
 * the SIP's published band, which IBKR does not pass on. So every word here says whose they are, an
 * approximate band (Nova did not see the stock open or reopen) carries `≈`, and the hover quotes the
 * measured track record.
 */
import { STOCK_VIEW_CLOCK_TIMEZONE } from '../constantGroups/chart_api';
import { LULD_APPROX_MARK, LULD_COLOR, LULD_LABEL, LULD_SCHEMA_VERSION } from '../constantGroups/luld';
import type { DepthMarker } from './depthMarkers';

export type LuldState = 'off' | 'unknown' | 'warming' | 'bands' | 'limit' | 'pause_due' | 'paused';

export interface LuldLimit {
  /** `down`: the best offer rests on the lower band; `up`: the best bid on the upper. */
  side: 'down' | 'up';
  since: number;
  band: number;
  /** When the listing exchange pauses the stock if the quote stays on the band (epoch seconds). */
  pause_at: number;
  /** 15 s passed: the pause is due now. */
  overdue: boolean;
}

export interface LuldTrack {
  source: string;
  measured: string;
  days: number | null;
  touches: number | null;
  exact: number | null;
  within_1c: number | null;
  text: string;
}

/** One stock's LULD view (backend `luld/views.py`; AGENTS.md §3 "LULD bands"). */
export interface LuldView {
  schema_version: number;
  symbol: string;
  source: 'live' | 'replay';
  state: LuldState;
  exact: boolean;
  lower: number | null;
  upper: number | null;
  reference: number | null;
  reference_since: number | null;
  reference_source: string | null;
  reference_words: string | null;
  percent: string | null;
  prev_close: number | null;
  tier: 1 | 2 | null;
  tier_text: string | null;
  /** False when the band's percentage rests on Nova's guess of the tier (no index list; over $3.00). */
  tier_sure: boolean;
  /** An approximate band: how far it may sit from the exchanges' (dollars). */
  spread: number | null;
  limit: LuldLimit | null;
  straddle: 'down' | 'up' | null;
  anchor: { kind: string; ts: number; price: number } | null;
  halted_since: number | null;
  watching_since: number | null;
  warm_until: number | null;
  gap: { ts: number; reason: string } | null;
  last: number | null;
  distance: { down_pct: number | null; up_pct: number | null } | null;
  near: 'down' | 'up' | null;
  reason: string | null;
  history: { ts: number; reference: number; source: string }[];
  note: string;
  rules: string;
  track: LuldTrack | null;
  as_of: number;
  text: string;
  /** Live only: Nova still holds the stock's tape line. */
  watching?: boolean;
}

const SHOWS: ReadonlySet<LuldState> = new Set(['bands', 'limit', 'pause_due']);

/** A frame's view, or null when it is not a version-1 view of this symbol. */
export function readLuldFrame(data: unknown, symbol: string): LuldView | null {
  if (!data || typeof data !== 'object') return null;
  const v = data as Partial<LuldView>;
  if (v.schema_version !== LULD_SCHEMA_VERSION || typeof v.state !== 'string') return null;
  if (typeof v.symbol !== 'string' || v.symbol.toUpperCase() !== symbol.toUpperCase()) return null;
  return v as LuldView;
}

export function fmtBand(p: number | null | undefined): string {
  if (p == null || !Number.isFinite(p)) return '?';
  return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function pct(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return '';
  const v = x * 100;
  return `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`;
}

export function clockEt(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return '?';
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    timeZone: STOCK_VIEW_CLOCK_TIMEZONE, hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

/** The bands are drawn: the state shows them and they are numbers. */
export function luldShows(view: LuldView | null): boolean {
  return Boolean(view && SHOWS.has(view.state) && (view.lower != null || view.upper != null));
}

/** `≈` when Nova did not see the stock (re)open, or guessed its tier. */
function approx(view: LuldView): string {
  return view.exact && view.tier_sure !== false ? '' : LULD_APPROX_MARK;
}

/** How Nova knows, in a few lines: the hover on every LULD piece. */
export function luldTip(view: LuldView | null): string {
  if (!view) return '';
  const lines: string[] = [view.text];
  if (luldShows(view)) {
    lines.push(`Lower band ${approx(view)}${fmtBand(view.lower)} · upper band ${approx(view)}${fmtBand(view.upper)}`);
    if (view.reference != null) {
      lines.push(`Reference ${view.reference.toFixed(4)} -- ${view.reference_words ?? 'the 5-minute average'}, `
        + `since ${clockEt(view.reference_since)} ET`);
    }
    if (view.percent) {
      lines.push(`Band ${view.percent}`
        + (view.prev_close != null ? ` (previous close ${fmtBand(view.prev_close)})` : '')
        + (view.tier_text ? `; ${view.tier_text}` : ''));
    }
    if (view.tier_sure === false) {
      lines.push(`The tier is Nova's assumption (${view.tier_text ?? 'no size known'}): a stock in the S&P 500 / `
        + 'Russell 1000 has a 5% band, any other a 10% band.');
    }
    if (!view.exact) {
      lines.push(`Approximate: Nova did not see this stock open or reopen with its tape unbroken since, so the `
        + `exchanges' reference may differ`
        + (view.spread != null ? `; measured, an approximate band sat within ${fmtBand(view.spread)} of theirs five times in six` : '')
        + '. Exact from its next reopen.'
        + (view.gap ? ` (${view.gap.reason})` : ''));
    }
    if (view.straddle) {
      lines.push(view.straddle === 'down'
        ? 'Straddle: the best bid is under the lower band -- the listing exchange may pause the stock.'
        : 'Straddle: the best offer is over the upper band -- the listing exchange may pause the stock.');
    }
  } else if (view.reason && view.reason !== view.text) {
    lines.push(view.reason);
  }
  if (view.watching === false) lines.push('Nova no longer holds this stock\'s tape: this is the band as it last stood.');
  lines.push('');
  lines.push(view.note);
  if (view.track?.text) lines.push(`Measured: ${view.track.text}`);
  lines.push(`Rules: ${view.rules}`);
  return lines.join('\n');
}

/** The two band rows: the lower band in the bid column, the upper in the ask column, where each sits. */
export function luldMarkers(view: LuldView | null): { bid: DepthMarker[]; ask: DepthMarker[] } {
  const out: { bid: DepthMarker[]; ask: DepthMarker[] } = { bid: [], ask: [] };
  if (!view || !luldShows(view)) return out;
  const tip = luldTip(view);
  const mark = approx(view);
  const limit = view.state === 'limit' || view.state === 'pause_due' ? view.limit : null;
  if (view.lower != null) {
    out.bid.push({
      id: 'luld-lower', price: view.lower, label: `${LULD_LABEL} ${mark}${fmtBand(view.lower)}`,
      color: LULD_COLOR, working: true, rests: 'bid', tip, variant: 'luld',
      hot: limit?.side === 'down' || view.near === 'down',
    });
  }
  if (view.upper != null) {
    out.ask.push({
      id: 'luld-upper', price: view.upper, label: `${LULD_LABEL} ${mark}${fmtBand(view.upper)}`,
      color: LULD_COLOR, working: true, rests: 'ask', tip, variant: 'luld',
      hot: limit?.side === 'up' || view.near === 'up',
    });
  }
  return out;
}

export type LuldTone = 'calm' | 'near' | 'limit' | 'pause' | 'idle';

export interface LuldStripView {
  tone: LuldTone;
  /** Both bands, one per column; null for a one-line strip (`center`). */
  bid: { text: string; pct: string; near: boolean } | null;
  ask: { text: string; pct: string; near: boolean } | null;
  center: string | null;
  /** A limit state: the share of its 15 s left (1 -> 0). */
  countdown: number | null;
  tip: string;
}

function mmss(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** The strip above the book; null when there is nothing to say (outside 09:30-16:00, no view). */
export function luldStrip(view: LuldView | null, nowMs: number): LuldStripView | null {
  if (!view || view.state === 'off') return null;
  const tip = luldTip(view);
  const now = nowMs / 1000;
  const stale = view.watching === false ? ' (stale)' : '';
  if (view.state === 'limit' && view.limit) {
    const left = view.limit.pause_at - now;
    const side = view.limit.side === 'down' ? 'LIMIT DOWN' : 'LIMIT UP';
    return {
      tone: 'limit', bid: null, ask: null, tip,
      center: `${side} ${fmtBand(view.limit.band)} · PAUSE IN ${Math.max(0, Math.ceil(left))}s${stale}`,
      countdown: Math.min(1, Math.max(0, left / 15)),
    };
  }
  if (view.state === 'pause_due' && view.limit) {
    const side = view.limit.side === 'down' ? 'LIMIT DOWN' : 'LIMIT UP';
    return { tone: 'limit', bid: null, ask: null, tip, countdown: 0,
      center: `PAUSE DUE · ${side} ${fmtBand(view.limit.band)}${stale}` };
  }
  if (view.state === 'paused') {
    return { tone: 'pause', bid: null, ask: null, tip, countdown: null, center: `${LULD_LABEL} · PAUSED · no band until it reopens` };
  }
  if (view.state === 'warming') {
    const left = view.warm_until != null ? view.warm_until - now : null;
    return { tone: 'idle', bid: null, ask: null, tip, countdown: null,
      center: left != null && left > 0 ? `${LULD_LABEL} in ${mmss(left)}` : `${LULD_LABEL} · reading the tape` };
  }
  if (view.state !== 'bands') {
    return { tone: 'idle', bid: null, ask: null, tip, countdown: null, center: `${LULD_LABEL} · not known` };
  }
  const mark = approx(view);
  return {
    tone: view.near ? 'near' : 'calm',
    bid: { text: `▼ ${mark}${fmtBand(view.lower)}`, pct: pct(view.distance?.down_pct), near: view.near === 'down' },
    ask: { text: `▲ ${mark}${fmtBand(view.upper)}`, pct: pct(view.distance?.up_pct), near: view.near === 'up' },
    center: null,
    countdown: null,
    tip,
  };
}
