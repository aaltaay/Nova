import { describe, expect, it } from 'vitest';
import { normalizeHotList } from './hotListApi';
import { listedOn } from './hotListStore';

const wire = {
  schema_version: 1, date: '2026-10-01', cap: 20,
  auto: { n: 5, start: '07:00', end: '16:00', rule: 'the top 5 of the live Gainers board by the leaders rule', error: null },
  default: { buy: 'you', sell: 'you' },
  entries: [
    { symbol: 'meds', how: 'auto', at: 1790852400, board: 'gainers', rank: 1, change_pct: 0.3, followed: true },
    { symbol: 'AISP', how: 'star', at: 1790865120, board: null, rank: null, change_pct: null, followed: true },
    { how: 'star' },
  ],
  yesterday: ['IMCC', 7],
  error: null,
};

describe('the hot list on the wire (ADR 044)', () => {
  it('reads the view, upper-casing symbols and dropping rows without one', () => {
    const v = normalizeHotList(wire);
    expect(v?.entries.map(e => e.symbol)).toEqual(['MEDS', 'AISP']);
    expect(v?.entries[0].how).toBe('auto');
    expect(v?.yesterday).toEqual(['IMCC']);
    expect(v?.auto.n).toBe(5);
  });

  it('refuses a shape it does not know instead of guessing an empty list', () => {
    expect(normalizeHotList({ ...wire, schema_version: 2 })).toBeNull();
    expect(normalizeHotList({ schema_version: 1 })).toBeNull();
    expect(normalizeHotList(null)).toBeNull();
  });

  it('says listed only once the list has been read', () => {
    const v = normalizeHotList(wire);
    expect(listedOn(v, 'aisp')).toBe(true);
    expect(listedOn(v, 'EJH')).toBe(false);
    expect(listedOn(null, 'AISP')).toBeNull();
  });
});
