import { describe, expect, it } from 'vitest';
import { sweepWords } from './BotKillSwitch';

describe('sweepWords', () => {
  it('names the protective stops a freeze kept resting (ADR 048)', () => {
    expect(sweepWords({ venue: 'paper', cancelled: [101], failed: [], kept: [23], error: null }))
      .toBe('Paper: cancelled 1 order (#101) · kept 1 protective stop resting (#23)');
    expect(sweepWords({ venue: 'live', cancelled: [], failed: [], kept: [5, 6], error: null }))
      .toBe('Live: kept 2 protective stops resting (#5, #6)');
  });
});
