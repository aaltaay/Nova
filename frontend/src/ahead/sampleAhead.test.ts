import { describe, expect, it } from 'vitest';
import { normalizeAnswer, normalizeStatus } from './aheadApi';
import { AHEAD_WORDS } from './aheadConstants';
import { sampleAhead, sampleAheadStatus } from './sampleAhead';

describe("the demo desk's Ahead", () => {
  it('answers that there is no forecaster, in the wire shape, with no AI number', () => {
    const a = sampleAhead('smpl', 1792500065);
    expect(normalizeAnswer(a, 'SMPL')).toEqual(a);
    expect(a.ai.state).toBe('not_set_up');
    expect(a.ai.reason).toBe(AHEAD_WORDS.demoReason);
    expect([a.ai.close, a.ai.paths, a.ai.volume]).toEqual([null, null, null]);
  });

  it('says the demo has no forecaster in its status', () => {
    const s = sampleAheadStatus(1792500065);
    expect(normalizeStatus(s)).toEqual(s);
    expect(s).toMatchObject({ configured: false, health: null });
  });
});
