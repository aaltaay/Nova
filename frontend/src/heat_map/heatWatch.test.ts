/**
 * The book watcher's verdicts on the heat map (ADR 061 amendment, 2026-10-21): the depth socket's `book_watch` frames
 * kept per stock for the whole window -- drops in market time, a repeated drop kept once, each hidden stretch's newest
 * word, gone with the window, gone when the stock starts over, and the watcher's own reason when it is off.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { HEAT_KEEP_SEC } from './heatMapConstants';
import { heatOf, noteHeatBook, noteHeatPrint, resetAllHeatForTests, resetHeat } from './heatStore';
import { heatWatchState, noteHeatWatch, resetHeatWatchForTests } from './heatWatch';

const T = 1792592797.316;   // SPCX 2026-10-21 10:26:37.316 ET: 3,719 of 5,219 at 162.00 traded
const iso = (sec: number) => new Date(sec * 1000).toISOString();

function drop(over: Record<string, unknown> = {}) {
  return {
    event: 'drop', symbol: 'SPCX', ts: T, side: 'bid', price: 162.0, dropped: 3719, pulled: 0, filled: 3719,
    outcome: 'traded', level_before: 5219, level_after: 1500, on_approach: false, seq: 7, ...over,
  };
}

function frame(over: Record<string, unknown> = {}) {
  return { schema_version: 1, source: 'live', now: T + 1, reset: false, seq: 7, watching: true, reason: null,
    window_sec: 60, sides: null, drops: [], hidden: [], ...over };
}

afterEach(() => {
  resetAllHeatForTests();
  resetHeatWatchForTests();
});

describe('noteHeatWatch', () => {
  it('keeps each large drop in market time with the watcher\'s verdict', () => {
    noteHeatBook('SPCX', [{ price: 162.0, size: 5219 }], [{ price: 162.06, size: 105 }], false, (T - 1) * 1000);
    noteHeatWatch('SPCX', frame({ drops: [drop(), drop({ ts: T - 21.4, outcome: 'pulled', pulled: 2000, filled: 0,
      level_before: 7276, seq: 3 })] }));
    const s = heatOf('SPCX')!;
    expect(s.drops.map((d) => [d.t, d.traded, d.filled, d.pulled])).toEqual([
      [T - 21.4, false, 0, 2000],
      [T, true, 3719, 0],
    ]);
    expect(s.drops[1].levelBefore).toBe(5219);
  });

  it("keeps a drop once when a socket's first frame repeats the last minute, even renumbered", () => {
    noteHeatWatch('SPCX', frame({ drops: [drop()] }));
    noteHeatWatch('SPCX', frame({ reset: true, seq: 1, drops: [drop({ seq: 1 })] }));   // a rebuilt watch counts from 1
    expect(heatOf('SPCX')!.drops).toHaveLength(1);
  });

  it('keeps two drops that leave one price in the same millisecond', () => {
    const pull = { outcome: 'pulled', filled: 0, pulled: 3000, ts: 101.0 };
    noteHeatWatch('SPCX', frame({ drops: [drop({ ...pull, level_before: 10_000, level_after: 7000, seq: 8 }),
      drop({ ...pull, level_before: 7000, level_after: 4000, seq: 9 })] }));
    expect(heatOf('SPCX')!.drops.map((d) => d.levelBefore)).toEqual([10_000, 7000]);
  });

  it('keeps the newest word on each hidden stretch, from its start to its end', () => {
    const word = { event: 'hidden', id: '1792581615000-OLOX-ask-1.15', kind: 'hidden_seller', side: 'ask', price: 1.15,
      state: 'holding', hidden: 35654, printed: 51771, shown_max: 16117, started_ts: 1792581615.0,
      last_print_ts: 1792581626.0, ended_ts: null, ts: 1792581626.0, seq: 1 };
    noteHeatWatch('OLOX', frame({ hidden: [word] }));
    noteHeatWatch('OLOX', frame({ hidden: [{ ...word, state: 'moved', hidden: 97127, printed: 113244,
      ended_ts: 1792581629.0, ts: 1792581629.0, seq: 3 }] }));
    noteHeatWatch('OLOX', frame({ hidden: [{ ...word, ts: 1792581620.0, seq: 2 }] }));   // late and older: ignored
    const h = [...heatOf('OLOX')!.hidden.values()];
    expect(h).toHaveLength(1);
    expect(h[0]).toMatchObject({ hidden: 97127, printed: 113244, shownMax: 16117, state: 'moved',
      t0: 1792581615.0, t1: 1792581629.0 });
  });

  it('lets verdicts go with the window and when the stock starts over', () => {
    noteHeatWatch('SPCX', frame({ drops: [drop()] }));
    noteHeatPrint('SPCX', iso(T + HEAT_KEEP_SEC + 5), 162.1, 100, 'ask', (T + HEAT_KEEP_SEC + 5) * 1000);
    expect(heatOf('SPCX')!.drops).toHaveLength(0);
    noteHeatWatch('SPCX', frame({ drops: [drop({ ts: T + HEAT_KEEP_SEC })] }));
    expect(heatOf('SPCX')!.drops).toHaveLength(1);
    resetHeat('SPCX');
    expect(heatOf('SPCX')!.drops).toHaveLength(0);
    expect(heatOf('SPCX')!.dropKeys.size).toBe(0);
  });

  it('starts the stock over when a replay\'s first frame is far behind what it holds', () => {
    noteHeatPrint('SPCX', iso(T), 162.0, 100, 'bid', T * 1000);
    noteHeatWatch('SPCX', frame({ source: 'replay', now: T, drops: [drop()] }));
    noteHeatWatch('SPCX', frame({ source: 'replay', reset: true, now: T - 120, seq: 1,
      drops: [drop({ ts: T - 130, seq: 1 })] }));
    const s = heatOf('SPCX')!;
    expect(s.drops.map((d) => d.t)).toEqual([T - 130]);
    expect(s.lastPrintT).toBe(Number.NEGATIVE_INFINITY);
  });

  it("keeps the watcher's own reason when it is not watching, and ignores a shape it does not know", () => {
    noteHeatWatch('SPCX', frame({ watching: false, reason: 'Replay has no Level 2 at the playhead.' }));
    expect(heatWatchState('SPCX')).toEqual({ watching: false, reason: 'Replay has no Level 2 at the playhead.' });
    noteHeatWatch('SPCX', frame({ schema_version: 2, drops: [drop()] }));
    expect(heatOf('SPCX')).toBeNull();
    expect(heatWatchState('SPCX')!.watching).toBe(false);
  });
});
