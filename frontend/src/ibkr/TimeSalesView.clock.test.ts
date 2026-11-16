import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { fmtTapeTime, TapeRow } from './TapeRow';
import type { TapePrint } from './tapeFeed';

describe('the tape clock is Eastern whatever the browser zone (QA W24)', () => {
  it('prints HH:MM:SS in ET', () => {
    // 09:44:02 UTC on Sep 22 is 05:44:02 EDT.
    expect(fmtTapeTime('2026-09-22T09:44:02Z')).toBe('05:44:02');
    // 04:00:00 UTC is midnight ET: 00, never 24.
    expect(fmtTapeTime('2026-09-22T04:00:00Z')).toBe('00:00:00');
  });
});

// 2026-11-06 09:30 ET: VIVK's trades of 09:30:03 reached the desk at 09:30:10 and read 09:30:10.
describe('a Time & Sales row shows when the trade happened (ADR 045 amendment 2026-11-06)', () => {
  const print: TapePrint = {
    symbol: 'VIVK', time: '2026-11-06T14:30:10.200Z', price: 0.82, size: 100, exchange: 'ARCA',
  };
  const shown = (p: TapePrint) => renderToStaticMarkup(createElement(TapeRow, { print: p }));

  it("reads IBKR's second, not the late arrival", () => {
    const exchangeTs = Date.parse('2026-11-06T14:30:03Z') / 1000;
    expect(shown({ ...print, exchangeTs })).toContain('>09:30:03<');
  });

  it('falls back to arrival only when IBKR gave no second', () => {
    expect(shown({ ...print, exchangeTs: null })).toContain('>09:30:10<');
    expect(shown(print)).toContain('>09:30:10<');
  });
});

