import { describe, expect, it } from 'vitest';
import { collapseAlertsBySymbol } from './collapseAlertsBySymbol';
import type { AlertObject } from './types';

function alert(
  partial: Partial<AlertObject> & Pick<AlertObject, 'id' | 'ticker' | 'timestamp'>,
): AlertObject {
  return {
    strategy_id: 3,
    strategy_name: 'Low Float - Med Rel Vol',
    price: 1,
    change_pct: 0,
    rvol: 2,
    float_shares: 1e6,
    gap_pct: null,
    volume: 1000,
    momentum_pct: null,
    rvol_source: 'ibkr_pace',
    consolidation_count: 1,
    consolidated_ids: [],
    ...partial,
  };
}

describe('collapseAlertsBySymbol', () => {
  it('keeps one row per ticker, collects distinct strategies, and pins the row to its first catch', () => {
    const rows = [
      alert({
        id: '1',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:55.000Z',
        created_ts: 100,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
        price: 5.5,
      }),
      alert({
        id: '2',
        ticker: 'AEHR',
        timestamp: '2026-07-14T21:25:54.000Z',
        created_ts: 99,
        strategy_id: 3,
        strategy_name: 'Low Float - Med Rel Vol',
      }),
      alert({
        id: '3',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:50.000Z',
        created_ts: 95,
        strategy_id: 3,
        strategy_name: 'Low Float - Med Rel Vol',
        price: 5.1,
      }),
      alert({
        id: '4',
        ticker: 'TRT',
        timestamp: '2026-07-14T21:25:48.000Z',
        created_ts: 93,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
        price: 5.0,
      }),
    ];
    const out = collapseAlertsBySymbol(rows);
    expect(out).toHaveLength(2);
    // TRT's first catch (id 4, created_ts 93) is older than AEHR's only fire
    // (created_ts 99), so AEHR — the more recently first-caught ticker — sits
    // on top, even though TRT has the most recent (newest-fire) snapshot data.
    expect(out.map(r => r.ticker)).toEqual(['AEHR', 'TRT']);
    const trt = out.find(r => r.ticker === 'TRT')!;
    // Live snapshot fields still come from the newest fire.
    expect(trt.price).toBe(5.5);
    expect(trt.strategies?.map(s => s.id)).toEqual([12, 3]);
    expect(trt.consolidation_count).toBe(3);
    // But identity/stamp are pinned to the first catch, not the newest fire.
    expect(trt.id).toBe('4');
    expect(trt.created_ts).toBe(93);
    expect(trt.timestamp).toBe('2026-07-14T21:25:48.000Z');
    const aehr = out.find(r => r.ticker === 'AEHR')!;
    expect(aehr.strategies?.map(s => s.id)).toEqual([3]);
  });

  it('does not inflate Warrior burst badge across long gaps', () => {
    const rows = [
      alert({
        id: '1',
        ticker: 'CJMB',
        timestamp: '2026-07-14T21:25:55.000Z',
        created_ts: 3000,
        consolidation_count: 2,
      }),
      alert({
        id: '2',
        ticker: 'CJMB',
        timestamp: '2026-07-14T20:50:00.000Z',
        created_ts: 1000,
        consolidation_count: 50,
        strategy_id: 12,
        strategy_name: 'Running Up Alert',
      }),
    ];
    const out = collapseAlertsBySymbol(rows, 15);
    expect(out).toHaveLength(1);
    expect(out[0].consolidation_count).toBe(2);
    expect(out[0].strategies?.map(s => s.id).sort((a, b) => a - b)).toEqual([3, 12]);
  });

  it('orders rows by first-catch time, not by which ticker re-fired most recently', () => {
    const rows = [
      alert({ id: '1', ticker: 'ZZZ', timestamp: '2026-07-14T21:25:55.000Z', created_ts: 100 }),
      alert({ id: '2', ticker: 'AAA', timestamp: '2026-07-14T21:25:54.000Z', created_ts: 99 }),
      alert({ id: '3', ticker: 'ZZZ', timestamp: '2026-07-14T21:25:50.000Z', created_ts: 95 }),
    ];
    const out = collapseAlertsBySymbol(rows);
    // ZZZ's first catch (id 3, created_ts 95) predates AAA's only fire
    // (created_ts 99) — AAA sits on top despite ZZZ having the newer alert.
    expect(out.map(r => r.ticker)).toEqual(['AAA', 'ZZZ']);
    const zzz = out.find(r => r.ticker === 'ZZZ')!;
    expect(zzz.id).toBe('3');
    expect(zzz.created_ts).toBe(95);
    expect(zzz.timestamp).toBe('2026-07-14T21:25:50.000Z');
  });

  it('keeps an already-caught row stable and stamped across later re-fires (simulated live growth)', () => {
    const round1 = [
      alert({ id: 'a1', ticker: 'AAA', timestamp: '2026-07-14T21:00:00.000Z', created_ts: 1000 }),
    ];
    // BBB fires next (newer); AAA is still further back in the newest-first list.
    const round2 = [
      alert({ id: 'b1', ticker: 'BBB', timestamp: '2026-07-14T21:01:00.000Z', created_ts: 1060 }),
      ...round1,
    ];
    const out2 = collapseAlertsBySymbol(round2);
    expect(out2.map(r => r.ticker)).toEqual(['BBB', 'AAA']);

    // AAA re-fires; its new alert is prepended to the front of the live feed —
    // exactly the shape that used to yank AAA's row back to the top.
    const round3 = [
      alert({ id: 'a3', ticker: 'AAA', timestamp: '2026-07-14T21:02:00.000Z', created_ts: 1120 }),
      ...round2,
    ];
    const out3 = collapseAlertsBySymbol(round3);
    expect(out3.map(r => r.ticker)).toEqual(['BBB', 'AAA']);
    const aaa = out3.find(r => r.ticker === 'AAA')!;
    // Row identity/stamp stay pinned to the very first fire (a1), never a3.
    expect(aaa.id).toBe('a1');
    expect(aaa.created_ts).toBe(1000);
    expect(aaa.timestamp).toBe('2026-07-14T21:00:00.000Z');
  });

  it('returns empty input unchanged', () => {
    expect(collapseAlertsBySymbol([])).toEqual([]);
  });
});
