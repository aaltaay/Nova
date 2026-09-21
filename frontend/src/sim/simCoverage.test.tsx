/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { coverageFraction, playheadBeyondCoverage } from './simCoverage';
import { HistoricalTimeSales } from './HistoricalTimeSales';
import type { HistoricalSnapshot } from './useHistoricalSnapshot';

// 09:15-11:30 ET on 2026-09-18 is 13:15-15:30 UTC.
const START = Date.parse('2026-09-18T13:15:00Z') / 1000;
const END = Date.parse('2026-09-18T15:30:00Z') / 1000;
const THROUGH = Date.parse('2026-09-18T13:40:00Z') / 1000; // trades reach 09:40 ET
const selection = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30',
  start_ts: START, end_ts: END, coverage_through: THROUGH };
const snap = (asOf: string, over: Partial<HistoricalSnapshot> = {}): HistoricalSnapshot => ({
  active: true, symbol: 'IMCC', source: 'mixed', as_of: asOf, last: 5.1, volume: 10,
  selection, prints: [{ time: '2026-09-18T13:39:59Z', price: 5.1, size: 100, exchange: 'NSDQ' }], ...over,
});

describe('coverageFraction', () => {
  it('is the downloaded share of the window', () => {
    expect(coverageFraction(selection)).toBeCloseTo(25 / 135);
  });

  it('is unknown rather than guessed without bounds', () => {
    expect(coverageFraction({ ...selection, start_ts: undefined })).toBeNull();
    expect(coverageFraction(null)).toBeNull();
  });
});

describe('playheadBeyondCoverage', () => {
  it('is true past the download edge and false inside it', () => {
    expect(playheadBeyondCoverage(snap('2026-09-18T15:00:00Z'))).toBe(true);   // 11:00 ET
    expect(playheadBeyondCoverage(snap('2026-09-18T13:30:00Z'))).toBe(false);  // 09:30 ET
  });

  it('never fires for a candles-only replay -- that has its own label', () => {
    expect(playheadBeyondCoverage(snap('2026-09-18T15:00:00Z', { source: 'completed_bars' }))).toBe(false);
  });
});

describe('HistoricalTimeSales past the download edge', () => {
  it("says the moment is not downloaded instead of passing the edge's prints off as current", () => {
    render(<HistoricalTimeSales symbol="IMCC" snapshot={snap('2026-09-18T15:00:00Z')} />);
    expect(screen.getByText(/Not downloaded yet -- trades reach 09:40:00 ET/)).toBeTruthy();
    expect(screen.queryByText('5.10')).toBeNull();
  });
});
