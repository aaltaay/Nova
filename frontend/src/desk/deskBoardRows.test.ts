import { describe, expect, it } from 'vitest';
import { makeLiveScannerFeedStub } from '../scanner/ScannerDataContext';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import {
  DESK_BOARD_MIRRORED_LISTS,
  deskBoardRowsFor,
  deskHeadlineFor,
  fmtRelVol,
  gapBarPct,
  maxAbsGap,
} from './deskBoardRows';

/** Fixtures author the gap in percent; the wire carries a fraction (QA V2 / C17). */
const frac = (pct: number | null): number | null => (pct == null ? null : pct / 100);

function row(symbol: string, gap: number | null, extra: Partial<ScannerRow> = {}): ScannerRow {
  return {
    symbol, price: 1, prev_close: 1, change_pct: frac(gap), change_abs: null, gap_percent: frac(gap), volume: 0, rel_volume: null,
    has_news: false, newest_headline_at: null, market_cap: null, float: null, short_interest: null, short_ratio: null,
    ...extra,
  };
}

function catalyst(symbol: string, headline: string | null, at: string | null, source = 'GlobeNewswire'): Catalyst {
  return {
    symbol, previous_close: 9.64, current_price: 12.85, gap_percent: 33.3 / 100, volume: 4_820_000, has_news: true,
    newest_headline_at: at, catalyst_headline: headline, catalyst_url: null, catalyst_source: source,
  };
}

describe('deskBoardRowsFor', () => {
  it('condenses every mirrored list to board rows and keeps unknown figures null', () => {
    const feed = makeLiveScannerFeedStub({
      gappers: [row('grml', 33.3, { price: 12.85, volume: 4_820_000, rel_volume: 6.4, float: 8_200_000, has_news: true, newest_headline_at: '2026-09-22T12:31:00Z' })],
      gainers: [row('VXTL', null, { change_pct: 21.7 / 100 })],
      losers: [row('CBRX', -5.4)],
      afterhours: [row('NUVT', 12.4)],
      largeCap: [row('AAPL', 1.2, { rvol: 2.5 })],
      catalysts: [catalyst('GRML', 'GRML reports positive topline results', '2026-09-22T12:31:00Z')],
    });
    const gappers = deskBoardRowsFor('gappers', feed)!;
    expect(gappers.total).toBe(1);
    expect(gappers.rows[0]).toEqual({
      symbol: 'GRML', price: 12.85, gapPct: 33.3, volume: 4_820_000, relVolume: 6.4, float: 8_200_000,
      catalyst: 'PR', headline: 'GRML reports positive topline results', headlineSource: 'GlobeNewswire',
      headlineAt: '2026-09-22T12:31:00Z', state: null,
    });
    // Gap falls back to the day change; nothing becomes 0.
    expect(deskBoardRowsFor('gainers', feed)!.rows[0]).toMatchObject({ gapPct: 21.7, relVolume: null, float: null, catalyst: null });
    expect(deskBoardRowsFor('losers', feed)!.rows[0].gapPct).toBe(-5.4);
    expect(deskBoardRowsFor('afterhours', feed)!.rows[0].symbol).toBe('NUVT');
    // Large Cap carries pace RVOL under `rvol`.
    expect(deskBoardRowsFor('large_cap', feed)!.rows[0].relVolume).toBe(2.5);
    const catalysts = deskBoardRowsFor('catalysts', feed)!;
    expect(catalysts.rows[0]).toMatchObject({ symbol: 'GRML', price: 12.85, gapPct: 33.3, volume: 4_820_000, relVolume: null, float: null, catalyst: 'PR' });
    expect(DESK_BOARD_MIRRORED_LISTS).toEqual(['gappers', 'gainers', 'losers', 'afterhours', 'large_cap', 'catalysts']);
  });

  it('reports lists the feed does not carry, and a missing feed, as null -- never an empty table', () => {
    const feed = makeLiveScannerFeedStub();
    expect(deskBoardRowsFor('hod_momo', feed)).toBeNull();
    expect(deskBoardRowsFor('watchlist', feed)).toBeNull();
    expect(deskBoardRowsFor('gappers', null)).toBeNull();
    expect(deskBoardRowsFor('gappers', feed)).toEqual({ rows: [], total: 0 });
  });

  it('applies the exchange filter to the rows but counts the total before it', () => {
    const feed = makeLiveScannerFeedStub({ gappers: [row('A', 1, { exchange: 'NASDAQ' }), row('B', 2, { exchange: 'OTC' })] });
    const filtered = deskBoardRowsFor('gappers', feed, rows => rows.filter(r => r.exchange !== 'OTC'))!;
    expect(filtered.rows.map(r => r.symbol)).toEqual(['A']);
    expect(filtered.total).toBe(2);
  });
});

describe('deskHeadlineFor', () => {
  const feed = makeLiveScannerFeedStub({
    gappers: [row('GRML', 33.3, { has_news: true, newest_headline_at: '2026-09-22T12:31:00Z' }), row('VXTL', 21.7)],
    losers: [row('CBRX', -5.4, { has_news: true, newest_headline_at: '2026-09-22T11:58:00Z' })],
    catalysts: [catalyst('GRML', 'GRML reports positive topline results', '2026-09-22T12:31:00Z')],
  });

  it('reads the catalysts text with its Eastern clock and wire, else the scanner stamp alone', () => {
    expect(deskHeadlineFor('grml', feed)).toEqual({ clock: '08:31', text: 'GRML reports positive topline results', source: 'GlobeNewswire' });
    // A scanner row knows the stamp but the feed carries no text: say so, never invent one.
    expect(deskHeadlineFor('CBRX', feed)).toEqual({ clock: '07:58', text: null, source: null });
    expect(deskHeadlineFor('VXTL', feed)).toEqual({ clock: null, text: null, source: null });
  });

  it('is null for an unknown symbol, no symbol, or no feed', () => {
    expect(deskHeadlineFor('ZZZZ', feed)).toBeNull();
    expect(deskHeadlineFor(null, feed)).toBeNull();
    expect(deskHeadlineFor('GRML', null)).toBeNull();
  });
});

describe('gap bar + formatters', () => {
  it('scales the bar to the widest gap on the board, using the magnitude for losers', () => {
    const rows = deskBoardRowsFor('gappers', makeLiveScannerFeedStub({
      gappers: [row('A', 33.3), row('B', 21.7), row('C', -18.9), row('D', null)],
    }))!.rows;
    const widest = maxAbsGap(rows);
    expect(widest).toBe(33.3);
    expect(rows.map(r => gapBarPct(r.gapPct, widest))).toEqual([100, 65, 57, 0]);
    expect(gapBarPct(5, 0)).toBe(0);
    expect(maxAbsGap([])).toBe(0);
  });

  it('formats rel vol with one decimal and a multiplication sign, unknown as a dash', () => {
    expect(fmtRelVol(6.4)).toBe('6.4×');
    expect(fmtRelVol(1)).toBe('1.0×');
    expect(fmtRelVol(null)).toBe('—');
  });
});
