import type { SymbolInspect } from './hodMomoDebugTypes';

/** A missing figure is a dash on its own -- never "—x" or "—%" (QA C67). */
export const HOD_DEBUG_ABSENT = '—';
/**
 * An enrichment older than this is not an age the debug panel can state: an
 * older backend sent a monotonic clock, which read "1790012783s ago" (QA C34).
 */
export const HOD_DEBUG_ENRICHED_MAX_AGE_SEC = 7 * 24 * 3600;

function finite(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

export function fmtTs(ts: number): string {
  if (!ts) return HOD_DEBUG_ABSENT;
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
  });
}

export function fmtNum(v: number | null | undefined, decimals = 2): string {
  if (!finite(v)) return HOD_DEBUG_ABSENT;
  return v.toFixed(decimals);
}

/** "$1.23"; absent is a bare dash. */
export function fmtUsd(v: number | null | undefined): string {
  return finite(v) ? `$${v.toFixed(2)}` : HOD_DEBUG_ABSENT;
}

/** "2.34x"; absent is a bare dash (was "—x"). */
export function fmtTimes(v: number | null | undefined): string {
  return finite(v) ? `${v.toFixed(2)}x` : HOD_DEBUG_ABSENT;
}

/** "12.34%" for a value already in percent points; absent is a bare dash (was "—%"). */
export function fmtPctPoints(v: number | null | undefined): string {
  return finite(v) ? `${v.toFixed(2)}%` : HOD_DEBUG_ABSENT;
}

export function fmtVol(v: number | null | undefined): string {
  if (!finite(v)) return HOD_DEBUG_ABSENT;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

/**
 * "12s ago" / "3m ago" / "2h ago" from an epoch-seconds enrichment stamp; a
 * missing, future or implausibly old stamp is a dash (QA C34).
 */
export function fmtEnrichedAgo(lastEnriched: number | null | undefined, nowSec: number): string {
  if (!finite(lastEnriched) || lastEnriched <= 0) return HOD_DEBUG_ABSENT;
  const age = Math.round(nowSec - lastEnriched);
  if (age < 0 || age > HOD_DEBUG_ENRICHED_MAX_AGE_SEC) return HOD_DEBUG_ABSENT;
  if (age < 90) return `${age}s ago`;
  if (age < 90 * 60) return `${Math.floor(age / 60)}m ago`;
  return `${Math.floor(age / 3600)}h ago`;
}

export function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * A /api/hod-momo/debug/symbol reply the inspector can render, or null.
 * QA C10: a 404 `{"detail":"Not Found"}` (e.g. for "BRK/B") has no `snap`, and
 * rendering it crashed the Scanner view.
 */
export function readInspectReply(data: unknown): SymbolInspect | null {
  if (!isRecord(data) || !isRecord(data.snap)) return null;
  return {
    ...(data as unknown as SymbolInspect),
    decisions: Array.isArray(data.decisions) ? (data.decisions as SymbolInspect['decisions']) : [],
    would_fire_now: isRecord(data.would_fire_now)
      ? (data.would_fire_now as unknown as SymbolInspect['would_fire_now'])
      : null,
  };
}

/** The error line for an inspector reply that is not a symbol snapshot. */
export function inspectErrorText(status: number, data: unknown): string {
  const detail = isRecord(data) && typeof data.detail === 'string' && data.detail.trim()
    ? data.detail.trim()
    : null;
  if (status >= 400) return `Inspector: ${detail ?? 'request failed'} (HTTP ${status})`;
  return 'Inspector: the reply was not a symbol snapshot';
}
