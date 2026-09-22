/**
 * Boundary parser for `GET /api/capture/sessions` (QA 2026-09-22, C13 / C21 /
 * C22). The listing feeds the Records page, the Sim Day / Ticker pickers and
 * the recorded lane; a missing `tickers_by_day`, a list where a map belongs or
 * a row without a symbol used to replace the Records page with an error card.
 * Now a malformed listing reads as "no Session Records", a malformed row is
 * skipped, and a count Nova does not know is `null` -- never a sentinel.
 */
import { finite, flag, isObject, objects, rangePairs, text, type Obj } from './payloadGuards';
import { unreadable } from './simPayloadParse';
import type { CaptureSessionRow, CaptureSessions } from './useSimSessionController';

/** A row count; the backend's `-1` ("rows on disk, not counted yet") and junk read as unknown. */
function rowCount(value: unknown): number | null {
  const n = finite(value);
  return n != null && n >= 0 ? n : null;
}

function nullable(value: unknown): string | null | undefined {
  return value === null ? null : text(value);
}

function parseRow(row: Obj): CaptureSessionRow | null {
  const symbol = text(row.symbol)?.trim().toUpperCase();
  if (!symbol) return null;
  const out: CaptureSessionRow = {
    ...row,
    symbol,
    prints: rowCount(row.prints),
    l2: rowCount(row.l2),
    usable: flag(row.usable),
    empty: flag(row.empty),
    unavailable_reason: nullable(row.unavailable_reason),
    segments: finite(row.segments),
    missing_sec: finite(row.missing_sec),
    last_reason: nullable(row.last_reason),
    status: text(row.status),
    source: nullable(row.source),
    spans: rangePairs(row.spans),
  };
  for (const key of Object.keys(out) as (keyof CaptureSessionRow)[]) {
    if (out[key] === undefined) delete out[key];
  }
  return out;
}

export function parseCaptureSessions(raw: unknown): CaptureSessions {
  if (!isObject(raw)) throw new Error(unreadable('Session Record listing'));
  const tickers_by_day: CaptureSessions['tickers_by_day'] = {};
  if (isObject(raw.tickers_by_day)) {
    for (const [date, rows] of Object.entries(raw.tickers_by_day)) {
      tickers_by_day[date] = objects(rows).map(parseRow).filter((row): row is CaptureSessionRow => row != null);
    }
  }
  const days = objects(raw.days)
    .map(day => ({ date: text(day.date) ?? '', ticker_count: finite(day.ticker_count) ?? 0 }))
    .filter(day => day.date);
  return { ...raw, days, tickers_by_day };
}
