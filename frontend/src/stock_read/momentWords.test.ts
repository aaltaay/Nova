/**
 * A short setup's plan before the trade (ADR 049): the badge names it ▼ SHORT, the call says SHORT NOW under the
 * trigger, the track reads Short, and the entry is the operator's own click (ADR 072: the strategies only watch).
 */
import { describe, expect, it } from 'vitest';
import { planBadgeText } from './chartShapes';
import { inputs, pfsaRead } from './momentFixtures';
import { momentOf, type MomentInputs } from './momentModel';
import type { StockPlan, StockRead } from './types';

const SHORT: Partial<StockPlan> = {
  side: 'short', setup_type: 'bear_flag', kind: 'bear_flag', trigger: 4.26, entry: 4.25, stop: 4.38, target: 3.99,
  risk: 0.13, reward: 0.26,
};

function shortRead(state: StockPlan['state'], distance: number | null = 0.03, setupType = 'bear_flag'): StockRead {
  const read = pfsaRead(state, { ...SHORT, setup_type: setupType, kind: setupType }, distance);
  return { ...read, setups: read.setups.map(l => ({ ...l, setup_type: setupType, side: 'short' as const })) };
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
    expect(now?.call?.detail).toMatch(/Your click: stage the short with its buy stop\.$/);
    expect(now?.call?.pin?.label).toBe('SHORT NOW');
  });

  it("the SSR bounce's short rests over the price for a buyer to lift", () => {
    const near = at({ read: shortRead('near', 0.03, 'ssr_bounce'), last: 4.23 });
    expect(near?.call?.title).toBe('GET READY');
    expect(near?.call?.detail).toMatch(/under the trigger\. A short rests at 4\.26: a buyer lifting the offer to it fills it/);
  });
});
