import { describe, expect, it } from 'vitest';
import { readGallery } from './galleryContract';
import { annotationSummary, entryTimeframes, tradeMarkers } from './annotations';
import type { Entry } from './types';

const sha = 'a'.repeat(64);
const buy = { kind: 'trade_marker', side: 'buy', second: 25522, price: 3.39, label: 'Buy 3.39' } as const;
const sell = { kind: 'trade_marker', side: 'sell', second: 25820.5, price: 4.1, label: 'Sell 4.10', color: 'gold' } as const;
const seconds = () => ({ id: 0, symbol: 'EXAMPLE', date: '2023-05-02', bar_seconds: 10,
  annotations: [buy, sell] as Entry['annotations'],
  bars_1m: [], bars_5m: [], bars_sub: [{ t: '2023-05-02T11:05:20Z', o: 3.3, h: 3.4, l: 3.3, c: 3.39, v: 900 }],
  source: { selection_sha256: sha, projection_sha256: sha } });
const gallery = (entry: object) => ({ schema_version: 1, kind: 'historical_ohlcv', family: 'Trades',
  selection_sha256: sha, entries: [entry], timings: { load_ms: 1, aggregation_ms: 0 } });

describe('trade charts on the native gallery', () => {
  it('accepts 10-second bars and buy / sell trade markers', () => {
    const parsed = readGallery(gallery(seconds())).entries[0];
    expect(parsed.bar_seconds).toBe(10);
    expect(entryTimeframes(parsed)).toEqual(['10Sec']);
    expect(entryTimeframes({ ...parsed, bar_seconds: undefined })).toEqual(['1Min', '5Min']);
  });
  it('rejects sub-minute bars without their bar size, an unsupported size, and bad markers', () => {
    const { bar_seconds: _, ...missing } = seconds();
    expect(() => readGallery(gallery(missing))).toThrow();
    expect(() => readGallery(gallery({ ...seconds(), bar_seconds: 60 }))).toThrow();
    expect(() => readGallery(gallery({ ...seconds(), bars_sub: [] }))).toThrow();
    for (const marker of [{ ...buy, side: 'short' }, { ...buy, second: 86400 }, { ...buy, price: 0 },
      { ...buy, extra: 1 }, { ...buy, color: 'url(x)' }]) {
      expect(() => readGallery(gallery({ ...seconds(), annotations: [marker] }))).toThrow();
    }
  });
  it('puts each fill on the bar that holds it: a buy arrow under, a sell arrow over', () => {
    const markers = tradeMarkers(seconds() as Entry, '10Sec');
    const midnight = Date.parse('2023-05-02T00:00:00Z') / 1000;
    expect(markers).toEqual([
      { time: midnight + 25520, position: 'belowBar', shape: 'arrowUp', color: '#10b981', text: 'Buy 3.39', id: 'trade-0' },
      { time: midnight + 25820, position: 'aboveBar', shape: 'arrowDown', color: '#e5b45b', text: 'Sell 4.10', id: 'trade-1' },
    ]);
    expect(tradeMarkers(seconds() as Entry, '1Min').map(m => m.time)).toEqual([midnight + 25500, midnight + 25800]);
  });
  it('names each fill with its side, price and second in the caption', () => {
    expect(annotationSummary([buy, sell])).toBe('Buy 3.39: BUY 3.3900 @ 07:05:22 ET | Sell 4.10: SELL 4.1000 @ 07:10:20 ET');
  });
});
