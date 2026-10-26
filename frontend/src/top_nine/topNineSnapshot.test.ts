import { describe, expect, it } from 'vitest';
import { makeLiveScannerFeedStub } from '../scanner/ScannerDataContext';
import { symbolRanks } from '../stock_view/quoteRank';
import type { ScannerReplay } from '../leaderboard';
import type { ScannerRow } from '../types/scanner';
import { buildTopNineSnapshot, parseTopNineSnapshot, sameTopNine, TOP_NINE_SCHEMA_VERSION } from './topNineSnapshot';

function row(symbol: string, change_pct: number, extra: Partial<ScannerRow> = {}): ScannerRow {
  return {
    symbol, price: 2, prev_close: 1, change_pct, change_abs: 1, gap_percent: null, volume: 1_000_000,
    rel_volume: null, has_news: false, newest_headline_at: null, market_cap: null, float: 4_083_260,
    short_interest: null, short_ratio: null, ...extra,
  } as ScannerRow;
}

const GAINERS = ['XLAB', 'ZTG', 'SMX', 'FVNNU', 'WORX', 'SGRX', 'TCRT', 'SITC', 'CORD', 'BLNE', 'MRKR']
  .map((s, i) => row(s, 140 - i * 10, s === 'XLAB' ? { halted: true } : {}));

describe('buildTopNineSnapshot', () => {
  it('takes the first nine rows as served, ranked like the Trader rank chip, with the list total', () => {
    const feed = makeLiveScannerFeedStub({ gainers: GAINERS, gappers: GAINERS.slice(0, 3) });
    const snap = buildTopNineSnapshot(feed, 1_792_160_075_000);
    expect(snap.source).toEqual({ kind: 'live' });
    expect(snap.asOf).toBe(1_792_160_040); // now's minute: it changes once a minute, not on every send
    expect(snap.lists.gainers.total).toBe(11);
    expect(snap.lists.gainers.rows.map((r) => r.symbol)).toEqual(GAINERS.slice(0, 9).map((r) => r.symbol));
    expect(snap.lists.gappers.rows).toHaveLength(3);
    expect(snap.lists.afterhours).toEqual({ rows: [], total: 0 });
    // One rule for rank: the pop-up's ZTG is the rank chip's ZTG.
    const chip = symbolRanks('ZTG', feed);
    expect(chip.state === 'ranked' && chip.ranks.find((r) => r.list === 'gainers')?.rank).toBe(2);
    expect(snap.lists.gainers.rows[1]).toEqual({
      symbol: 'ZTG', rank: 2, changePct: 130, price: 2, volume: 1_000_000, float: 4_083_260, halted: false,
    });
    expect(snap.lists.gainers.rows[0].halted).toBe(true);
  });

  it('sends no rows, with the reason, when the desk cannot rank (a saved board, a gap at the playhead)', () => {
    const saved = buildTopNineSnapshot(makeLiveScannerFeedStub({ gainers: GAINERS, historyDate: '2026-10-16' }));
    expect(saved.source.kind).toBe('unknown');
    expect(saved.lists.gainers.rows).toEqual([]);
    expect(buildTopNineSnapshot(null).source).toEqual({ kind: 'unknown', why: 'No scanner feed in this window.' });
  });

  it('labels a Sim playhead board as the Scanner does', () => {
    const replay = {
      date: '2026-10-16', minute: 1_792_160_040, status: 'ready', source: 'recorded', minuteTs: null, gap: null,
      error: null, tables: { gappers: [], gainers: [], losers: [], afterhours: [], largeCap: [] },
      boardStates: {}, leaders: [],
    } as unknown as ScannerReplay;
    const snap = buildTopNineSnapshot(makeLiveScannerFeedStub({ gainers: GAINERS, replay }));
    expect(snap.source.kind).toBe('replay');
    expect(snap.asOf).toBe(1_792_160_040); // the playhead's board minute
    expect(snap.source.kind === 'replay' && snap.source.label).toContain('2026-10-16');
  });
});

describe('parseTopNineSnapshot', () => {
  it('round-trips what the desk sends, and refuses another schema version or a broken row', () => {
    const snap = buildTopNineSnapshot(makeLiveScannerFeedStub({ gainers: GAINERS }));
    const wire = JSON.parse(JSON.stringify(snap));
    expect(parseTopNineSnapshot(wire)).toEqual(snap);
    expect(sameTopNine(parseTopNineSnapshot(wire), snap)).toBe(true);
    expect(parseTopNineSnapshot({ ...wire, schema_version: TOP_NINE_SCHEMA_VERSION + 1 })).toBeNull();
    expect(parseTopNineSnapshot({ ...wire, asOf: 'now' })).toBeNull();
    const broken = JSON.parse(JSON.stringify(wire));
    broken.lists.gainers.rows[0].rank = 0;
    expect(parseTopNineSnapshot(broken)).toBeNull();
    expect(parseTopNineSnapshot('nope')).toBeNull();
  });
});
