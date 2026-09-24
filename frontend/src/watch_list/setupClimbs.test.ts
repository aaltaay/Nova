import { describe, expect, it } from 'vitest';
import type { SetupRow, SetupState } from '../setups';
import { setupClimbs, type SetupClimbMemory } from './setupClimbs';
import { FIXTURE_LEG_B as LEG_B, setupBoard, setupRow } from './setupFixtures';
import { WATCH_SETUP_FORMING_REPEAT_MS } from './watchListConstants';

/** Feeds frames through one memory; returns the stages each frame announced. */
function run(frames: SetupRow[][], stepMs = 1_000, start: SetupClimbMemory | null = null): string[][] {
  let memory = start;
  let now = 1_000_000;
  return frames.map(rows => {
    const read = setupClimbs(memory, setupBoard(rows), now);
    memory = read.memory;
    now += stepMs;
    return read.climbs.map(c => `${c.symbol} ${c.setupType} ${c.stage}`);
  });
}

describe('setupClimbs', () => {
  it('reads the first frame silently, then announces each rung once', () => {
    expect(run([
      [setupRow('GRML', 'armed')],
      [setupRow('GRML', 'near')],
      [setupRow('GRML', 'triggered')],
    ])).toEqual([[], ['GRML first_pullback near'], ['GRML first_pullback triggered']]);
    expect(run([
      [],
      [setupRow('grml', 'leg')],
      [setupRow('GRML', 'pullback')],
      [setupRow('GRML', 'armed')],
    ])).toEqual([[], ['GRML first_pullback forming'], [], ['GRML first_pullback armed']]);
  });

  it('never announces failed, filtered or a setup off the board', () => {
    expect(run([
      [],
      [setupRow('GRML', 'failed'), setupRow('ONCO', 'filtered')],
      [],
    ])).toEqual([[], [], []]);
  });

  it('is one toast when price wobbles in and out of the near band, or a rule holds it back', () => {
    expect(run([
      [],
      [setupRow('GRML', 'armed')],
      [setupRow('GRML', 'near')],
      [setupRow('GRML', 'armed')],
      [setupRow('GRML', 'near')],
      [setupRow('GRML', 'pullback')],
      [setupRow('GRML', 'armed')],
    ]).flat()).toEqual(['GRML first_pullback armed', 'GRML first_pullback near']);
  });

  it('starts over when a new leg replaces a setup, or after a trigger', () => {
    expect(run([
      [],
      [setupRow('GRML', 'armed')],
      [setupRow('GRML', 'armed', {}, LEG_B)],     // a newer leg armed in its place
    ])).toEqual([[], ['GRML first_pullback armed'], ['GRML first_pullback armed']]);
    const later = WATCH_SETUP_FORMING_REPEAT_MS + 1;
    expect(run([
      [],
      [setupRow('GRML', 'leg')],
      [setupRow('GRML', 'triggered')],
      [setupRow('GRML', 'leg', {}, LEG_B)],        // the second pullback's leg
      [setupRow('GRML', 'armed', {}, LEG_B)],
    ], later)).toEqual([
      [], ['GRML first_pullback forming'], ['GRML first_pullback triggered'],
      ['GRML first_pullback forming'], ['GRML first_pullback armed'],
    ]);
  });

  it('announces forming at most once per cool-down on a name that keeps failing and forming', () => {
    const chop = [[], [setupRow('GRML', 'leg')], [setupRow('GRML', 'failed')], [setupRow('GRML', 'leg', {}, LEG_B)]];
    expect(run(chop, 60_000).flat()).toEqual(['GRML first_pullback forming']);
    expect(run(chop, WATCH_SETUP_FORMING_REPEAT_MS).flat())
      .toEqual(['GRML first_pullback forming', 'GRML first_pullback forming']);
  });

  it('keeps each setup of a symbol apart, and a new session reads silently again', () => {
    const flag = (state: SetupState) => setupRow('GRML', state, { setup_type: 'bull_flag', kind: 'bull_flag' });
    const read = run([[], [setupRow('GRML', 'leg'), flag('leg')], [setupRow('GRML', 'leg'), flag('armed')]]);
    expect(read).toEqual([[], ['GRML first_pullback forming', 'GRML bull_flag forming'], ['GRML bull_flag armed']]);

    const first = setupClimbs(null, setupBoard([]), 0);
    const nextDay = setupClimbs(first.memory, setupBoard([setupRow('GRML', 'armed')], { session_date: '2026-09-25' }), 1);
    expect(nextDay.climbs).toEqual([]);
  });

  it('stamps the climb with the frame time and the row it saw', () => {
    const first = setupClimbs(null, setupBoard([]), 0);
    const row = setupRow('PFSA', 'near');
    const { climbs } = setupClimbs(first.memory, setupBoard([row], { generated_at: 1_790_001_234 }), 1);
    expect(climbs).toEqual([{ symbol: 'PFSA', setupType: 'first_pullback', stage: 'near', row, at: 1_790_001_234 }]);
  });
});
