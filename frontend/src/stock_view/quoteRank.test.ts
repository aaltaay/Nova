import { describe, expect, it } from 'vitest';
import { rankTip, symbolRanks } from './quoteRank';

const rows = (...syms: string[]) => syms.map((symbol) => ({ symbol }));

function feed(over: Record<string, unknown> = {}) {
  return {
    gappers: rows('AAA', 'VBIO', 'CCC'),
    gainers: rows('X1', 'X2', 'X3', 'vbio', 'X5'),
    losers: rows('L1'),
    afterhours: [],
    largeCap: rows('AAPL'),
    historyDate: null,
    replay: null,
    ...over,
  } as unknown as Parameters<typeof symbolRanks>[1];
}

describe('symbolRanks', () => {
  it('gives the 1-based place on every list that holds the symbol, in list order', () => {
    const r = symbolRanks('VBIO', feed());
    expect(r).toEqual({
      state: 'ranked',
      replay: false,
      ranks: [
        { list: 'gappers', label: 'Gappers', rank: 2, total: 3 },
        { list: 'gainers', label: 'Gainers', rank: 4, total: 5 },
      ],
    });
  });

  it('says not on a list when no list holds it', () => {
    expect(symbolRanks('ZZZ', feed())).toEqual({ state: 'unranked', replay: false });
  });

  it('is unknown without a feed, on a saved day, or with no board at the playhead', () => {
    expect(symbolRanks('VBIO', null).state).toBe('unknown');
    expect(symbolRanks('VBIO', feed({ historyDate: '2026-09-29' })).state).toBe('unknown');
    const gap = { status: 'ready', gap: { reason: 'not_running' } };
    expect(symbolRanks('VBIO', feed({ replay: gap, gappers: [], gainers: [] })).state).toBe('unknown');
    expect(symbolRanks('VBIO', feed({ replay: { status: 'loading', gap: null } })).state).toBe('unknown');
  });

  it('marks a ready playhead board as a replay', () => {
    const r = symbolRanks('VBIO', feed({ replay: { status: 'ready', gap: null } }));
    expect(r.state === 'ranked' && r.replay).toBe(true);
    expect(rankTip({ list: 'gappers', label: 'Gappers', rank: 1, total: 12 }, true))
      .toMatch(/^1st of 12 on Gappers at the Sim playhead\./);
  });

  it('names the ordinal right', () => {
    const t = (rank: number) => rankTip({ list: 'gainers', label: 'Gainers', rank, total: 120 }, false);
    expect(t(2)).toMatch(/^2nd /);
    expect(t(3)).toMatch(/^3rd /);
    expect(t(11)).toMatch(/^11th /);
    expect(t(22)).toMatch(/^22nd /);
  });
});
