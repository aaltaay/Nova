import { describe, expect, it } from 'vitest';
import { readGallery } from './galleryContract';
import { annotationSummary, priceLineOptions } from './annotations';

const sha = 'a'.repeat(64);
const entry = () => ({ id: 0, symbol: 'EXAMPLE', date: '2022-02-10', annotations: [],
  bars_1m: [{ t: '2022-02-10T15:00:00Z', o: 2, h: 3, l: 1, c: 2.5, v: 100 }], bars_5m: [],
  source: { selection_sha256: sha, projection_sha256: sha } });
const gallery = () => ({ schema_version: 1, kind: 'historical_ohlcv', family: 'Historical review',
  selection_sha256: sha, entries: [entry()], timings: { load_ms: 1, aggregation_ms: 2 } });

describe('generic historical OHLCV contract', () => {
  it('accepts a whole observed session without an as-of boundary', () => {
    expect(readGallery(gallery()).entries[0].as_of_t).toBeUndefined();
  });
  it('accepts repeated tickers on different dates and optional as-of endpoints', () => {
    const value = gallery();
    value.entries.push({ ...entry(), id: 1, date: '2022-02-11' });
    expect(readGallery(value).entries).toHaveLength(2);
    expect(readGallery({ ...gallery(), entries: [{ ...entry(), as_of_m: 1440, as_of_t: '2022-02-11T05:00:00Z' }] }).entries[0].as_of_m).toBe(1440);
  });
  it('rejects unrecognized wire keys and unsupported kinds', () => {
    expect(() => readGallery({ ...gallery(), unexpected: true })).toThrow();
    expect(() => readGallery({ ...gallery(), kind: 'other' })).toThrow();
    expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), extra: 1 }] })).toThrow();
  });
  it('never accepts a boundary without its timestamp or its paired minute', () => {
    for (const boundary of [{ as_of_m: 601 }, { as_of_t: '2022-02-10T15:01:00Z' },
      { as_of_m: true, as_of_t: '2022-02-10T15:01:00Z' }, { as_of_m: 601, as_of_t: 'invalid' }]) {
      expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), ...boundary }] })).toThrow();
    }
  });
  it('rejects an as-of timestamp that disagrees with the declared ET boundary', () => {
    expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), as_of_m: 601, as_of_t: '2022-02-10T15:02:00Z' }] })).toThrow();
  });
  it('limits source metadata to matching SHA256 identifiers', () => {
    expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), source: { ...entry().source, path: 'local-file' } }] })).toThrow();
    expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), source: { ...entry().source, projection_sha256: 'invalid' } }] })).toThrow();
  });
  it('accepts generic finite horizontal lines and ET time markers with fixed colors', () => {
    const annotations = [
      { kind: 'horizontal_line', price: 2.25, label: 'Reference', color: 'gold' },
      { kind: 'time_marker', minute: 600, label: 'Observation' },
    ];
    const parsed = readGallery({ ...gallery(), entries: [{ ...entry(), annotations }] });
    expect(priceLineOptions(parsed.entries[0].annotations)).toEqual([{ price: 2.25, title: 'Reference', color: '#e5b45b', lineWidth: 1 }]);
    expect(annotationSummary(parsed.entries[0].annotations)).toContain('Observation: 10:00 ET');
  });
  it('rejects nonfinite prices, invalid minutes, arbitrary CSS and extra annotation keys', () => {
    for (const annotation of [
      { kind: 'horizontal_line', price: Infinity, label: 'Reference' },
      { kind: 'horizontal_line', price: 0, label: 'Reference' },
      { kind: 'time_marker', minute: 1440, label: 'Observation' },
      { kind: 'time_marker', minute: true, label: 'Observation' },
      { kind: 'time_marker', minute: 600, label: 'Observation', color: 'url(x)' },
      { kind: 'time_marker', minute: 600, label: 'Observation', extra: 1 },
      { kind: 'time_marker', minute: 600, label: '' },
      { kind: 'time_marker', minute: 600, label: 'x'.repeat(81) },
    ]) expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), annotations: [annotation] }] })).toThrow();
  });
  it('rejects malformed OHLCV rather than deriving candles', () => {
    expect(() => readGallery({ ...gallery(), entries: [{ ...entry(), bars_1m: [{ ...entry().bars_1m[0], h: 0 }] }] })).toThrow();
  });
});
