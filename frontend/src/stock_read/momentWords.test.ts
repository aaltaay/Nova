/**
 * A short setup's plan before the trade (ADR 049): the badge names it ▼ SHORT, the call says SHORT NOW under the
 * trigger, the track reads Short, and no Nova mode promises to trade it until the bot trades both sides.
 */
import { describe, expect, it } from 'vitest';
import { planBadgeText } from './chartShapes';
import { momentOf, type MomentInputs } from './momentModel';
import type { StockPlan, StockRead } from './types';
import { inputs, pfsaRead, pfsaView } from './whoTradesFixtures';

const SHORT: Partial<StockPlan> = {
  side: 'short', setup_type: 'bear_flag', kind: 'bear_flag', trigger: 4.26, entry: 4.25, stop: 4.38, target: 3.99,
  risk: 0.13, reward: 0.26,
};

function shortRead(state: StockPlan['state'], distance: number | null = 0.03): StockRead {
  const read = pfsaRead(state, SHORT, distance);
  return { ...read, setups: read.setups.map(l => ({ ...l, setup_type: 'bear_flag', side: 'short' as const })) };
}

const at = (over: Partial<MomentInputs>) => momentOf(inputs(over));

describe('a short setup\'s plan before the trade', () => {
  it('names the setup ▼ SHORT on the badge and reads the short\'s track', () => {
    const m = at({ read: shortRead('near'), last: 4.29 });
    expect(m?.badge).toMatch(/^BEAR FLAG ▼ SHORT · /);
    expect(m?.side).toBe('short');
    expect(planBadgeText(shortRead('armed'))).toBe('BEAR FLAG ▼ SHORT · ARMED');
  });

  it('gets ready over the trigger and calls SHORT NOW when it prints under it with the tape at go', () => {
    const near = at({ read: shortRead('near'), last: 4.29 });
    expect(near?.call?.title).toBe('GET READY');
    expect(near?.call?.detail).toMatch(/over the trigger\. Short under 4\.26: the chart says SHORT NOW when it prints\./);
    const now = at({ read: shortRead('triggered'), last: 4.25 });
    expect(now?.call?.title).toBe('SHORT NOW · 4.25');
    expect(now?.call?.detail).toMatch(/Your click: stage the short with its buy stop\./);
    expect(now?.call?.pin?.label).toBe('SHORT NOW');
  });

  it('never promises a Nova trade on a short before step 5: it says to stage the short', () => {
    const m = at({ read: shortRead('near'), last: 4.29, who: pfsaView('approve') });
    expect(m?.call?.title).toBe('STAGE THE SHORT');
    expect(m?.call?.detail).toMatch(/trade shorts once the bot trades both sides \(#778 step 5\)/);
  });
});
