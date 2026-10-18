import { ANNOTATION_COLORS } from './annotations';
import { isoToEtTime } from '../../tickerChartData';
import type { Gallery } from './types';

function invalid(): never { throw new Error('Invalid historical OHLCV gallery'); }
function record(value: unknown): Record<string, unknown> {
  if (value == null || typeof value !== 'object' || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}
function keys(value: Record<string, unknown>, allowed: string[]) {
  if (Object.keys(value).some(key => !allowed.includes(key))) invalid();
}
const text = (value: unknown) => typeof value === 'string' && value.trim().length > 0;
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const minute = (value: unknown, max: number) => finite(value) && Number.isInteger(value) && value >= 0 && value <= max;
const sha = (value: unknown) => typeof value === 'string' && /^[a-fA-F0-9]{64}$/.test(value);

function annotations(value: unknown) {
  if (!Array.isArray(value) || value.length > 32) invalid();
  for (const raw of value) {
    const annotation = record(raw);
    if (!text(annotation.label) || (annotation.label as string).length > 80) invalid();
    if (annotation.color !== undefined && (typeof annotation.color !== 'string' || !Object.hasOwn(ANNOTATION_COLORS, annotation.color))) invalid();
    if (annotation.kind === 'horizontal_line') {
      keys(annotation, ['kind', 'price', 'label', 'color']);
      if (!finite(annotation.price) || annotation.price <= 0) invalid();
    } else if (annotation.kind === 'time_marker') {
      keys(annotation, ['kind', 'minute', 'label', 'color']);
      if (!minute(annotation.minute, 1439)) invalid();
    } else invalid();
  }
}

function bars(value: unknown) {
  if (!Array.isArray(value)) invalid();
  let previous = -Infinity;
  for (const raw of value) {
    const bar = record(raw);
    keys(bar, ['t', 'o', 'h', 'l', 'c', 'v']);
    if (typeof bar.t !== 'string' || !Number.isFinite(Date.parse(bar.t)) || Date.parse(bar.t) <= previous) invalid();
    const { o, h, l, c, v } = bar;
    if (!finite(o) || !finite(h) || !finite(l) || !finite(c) || !finite(v)
      || Math.min(o, h, l, c) <= 0 || v < 0 || l > Math.min(o, c) || h < Math.max(o, c) || h < l) invalid();
    previous = Date.parse(bar.t);
  }
}

/** Public wire boundary: only generic data and hash provenance reach the renderer. */
export function readGallery(value: unknown): Gallery {
  const gallery = record(value);
  keys(gallery, ['schema_version', 'kind', 'family', 'selection_sha256', 'entries', 'timings']);
  if (gallery.schema_version !== 1 || gallery.kind !== 'historical_ohlcv' || !text(gallery.family) || !sha(gallery.selection_sha256)) invalid();
  if (!Array.isArray(gallery.entries) || !gallery.entries.length || gallery.entries.length > 9) invalid();
  const ids = new Set<number>();
  for (const raw of gallery.entries) {
    const entry = record(raw);
    keys(entry, ['id', 'symbol', 'date', 'as_of_m', 'as_of_t', 'annotations', 'bars_1m', 'bars_5m', 'source']);
    if (!finite(entry.id) || !Number.isInteger(entry.id) || entry.id < 0 || ids.has(entry.id)
      || !text(entry.symbol) || typeof entry.date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(entry.date)) invalid();
    ids.add(entry.id);
    if (entry.as_of_m !== undefined || entry.as_of_t !== undefined) {
      if (!minute(entry.as_of_m, 1440) || typeof entry.as_of_t !== 'string' || !Number.isFinite(Date.parse(entry.as_of_t))) invalid();
      const expected = Date.parse(`${entry.date}T00:00:00Z`) / 1000 + (entry.as_of_m as number) * 60;
      if (isoToEtTime(entry.as_of_t as string, false) !== expected) invalid();
    }
    annotations(entry.annotations);
    bars(entry.bars_1m); bars(entry.bars_5m);
    const source = record(entry.source);
    keys(source, ['selection_sha256', 'projection_sha256']);
    if (source.selection_sha256 !== gallery.selection_sha256 || !sha(source.projection_sha256)) invalid();
  }
  const timings = record(gallery.timings);
  keys(timings, ['load_ms', 'aggregation_ms']);
  if (!finite(timings.load_ms) || timings.load_ms < 0 || !finite(timings.aggregation_ms) || timings.aggregation_ms < 0) invalid();
  return value as Gallery;
}
