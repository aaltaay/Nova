import { describe, expect, it } from 'vitest';
import { SAMPLE_SETUPS_BOARD } from '../sample_data/sampleSetups';
import {
  distanceLabel, fmtCents, fmtPx, fmtR, isActionable, outcomeLabel, rowClass, stagedLimit,
} from './setupsFormat';
import type { SetupRow } from './types';

const [near, armed, triggered, leg] = SAMPLE_SETUPS_BOARD.rows as SetupRow[];

describe('setupsFormat', () => {
  it('formats prices, cents and R without inventing a value', () => {
    expect(fmtPx(4.3)).toBe('4.30');
    expect(fmtPx(0.4521)).toBe('0.4521');
    expect(fmtPx(null)).toBe('—');
    expect(fmtPx(Number.NaN)).toBe('—');
    expect(fmtCents(0.08)).toBe('8¢');
    expect(fmtR(1.44)).toBe('+1.44R');
    expect(fmtR(-0.5)).toBe('-0.50R');
    expect(fmtR(undefined)).toBe('—');
  });

  it('labels the distance to the trigger in cents', () => {
    expect(distanceLabel(near)).toBe('2¢ under');
    expect(distanceLabel({ ...near, distance: 0 })).toBe('at trigger');
    expect(distanceLabel({ ...near, distance: -0.01 })).toBe('at trigger');
    expect(distanceLabel(leg)).toBe('');
  });

  it('stages the proposal entry, else the armed entry', () => {
    expect(stagedLimit(near)).toBe('4.38');
    expect(stagedLimit(armed)).toBe('7.13');
    expect(stagedLimit(leg)).toBe('');
  });

  it('knows which rows are actionable and how a triggered one went', () => {
    expect(isActionable(near)).toBe(true);
    expect(isActionable(armed)).toBe(true);
    expect(isActionable(triggered)).toBe(false);
    expect(outcomeLabel(triggered)).toBe('Target first');
    expect(outcomeLabel({ ...triggered, outcome: 'stop_first' })).toBe('Stop first');
    expect(outcomeLabel({ ...triggered, outcome: null })).toBe('Open');
    expect(outcomeLabel(near)).toBe('');
    expect(rowClass(near)).toContain('setups-row--proposal');
    expect(rowClass(armed)).not.toContain('setups-row--proposal');
  });
});
