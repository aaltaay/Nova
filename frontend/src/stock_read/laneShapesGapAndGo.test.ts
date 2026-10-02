import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { laneShapes } from './laneShapes';
import type { SetupLane } from './types';

const toTime = (t: number) => t as unknown as Time;

function lane(partial: Partial<SetupLane>): SetupLane {
  return {
    setup_type: 'gap_and_go', state: 'watching', reason: '', setup: null, forming: null,
    leg: { t: 1_000, high: 4.5, low: 4.3296, pct: 0 }, series: null, ...partial,
  } as unknown as SetupLane;
}

describe('Gap and Go on the 1-minute chart', () => {
  it('draws the pre-market high from the candle that set it: dashed while forming, solid once armed', () => {
    const forming = laneShapes(lane({ forming: { trigger: 4.5, entry: 4.51, stop: 4.3296, risk: 0.1804, target1: 4.8708,
      bars: 0, blocked: null, waiting: 'waits for the 09:30 open' } }), true, { toTime });
    expect(forming.boxes).toEqual([]);
    expect(forming.segments).toHaveLength(1);
    expect(forming.segments[0]).toMatchObject({ t1: 1_000, price: 4.5, dashed: true, label: 'PMH 4.50' });
    const armed = laneShapes(lane({ state: 'armed', setup: { trigger: 4.5, entry: 4.51, stop: 4.3296, risk: 0.1804,
      target1: 4.8708, pullback_bars: 0 } as SetupLane['setup'] }), true, { toTime });
    expect(armed.segments[0]).toMatchObject({ price: 4.5, dashed: false, label: 'PMH 4.50' });
  });
});
