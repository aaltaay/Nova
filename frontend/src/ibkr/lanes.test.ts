/**
 * The three lanes read at the boundary (ADR 071; lane 3 is the brain's since ADR 072): a malformed lane is an empty
 * one, nothing is invented, who records what comes from the lanes alone, and an older backend's answer -- lane 3
 * as `bots` with the setup picker's fields -- still parses, with the brain's lane empty.
 */
import { describe, expect, it } from 'vitest';
import { LANE_OWNERS, laneRecording, lanesOn, parseLanes, parseRecordingSwitch } from './lanes';

const empty = { symbol: null, since: null, depth: false, tape: false, recording: false, error: null };

const VIEW = {
  schema_version: 2, generated_at: 5, recording_error: null, tape_capacity: { limit: null },
  you: { symbol: 'xlab', since: 4, depth: true, tape: true, recording: true, error: null },
  claude: { ...empty, symbol: 'AISP', depth: true, tape: true, recording: true },
  brain: { symbol: 'aisp', since: 3, depth: true, tape: true, recording: true, error: null,
    why: 'First pullback holding the 4.30 bid', setup: 'first_pullback', waiting: [{ symbol: 'runr' }] },
};

/** Version 1, from a backend before ADR 072's lane 3: `bots` with the picker's fields, and no `brain`. */
const VIEW_V1 = {
  schema_version: 1, generated_at: 5, recording_error: null, tape_capacity: { limit: null },
  you: VIEW.you,
  claude: VIEW.claude,
  bots: { symbol: 'RUNR', since: 3, depth: true, tape: true, recording: true, error: null, setup: 'first_pullback',
    why: 'near', waiting: [{ symbol: 'runr', setup: 'bull_flag', why: 'armed' }, { setup: 'x' }, 'junk'] },
};

describe('the lanes view', () => {
  it('names the three owners: you, Claude and the brain', () => {
    expect(LANE_OWNERS).toEqual(['you', 'claude', 'brain']);
  });

  it('reads each lane, upper-cases its stock, keeps the brain\'s own words and drops the picker\'s fields', () => {
    const v = parseLanes(VIEW)!;
    expect(v.schema_version).toBe(2);
    expect(v.you).toEqual({ symbol: 'XLAB', since: 4, depth: true, tape: true, recording: true, error: null });
    expect(v.brain).toEqual({
      symbol: 'AISP', since: 3, depth: true, tape: true, recording: true, error: null,
      why: 'First pullback holding the 4.30 bid',
    });
    expect(v).not.toHaveProperty('bots');
  });

  it('a lane that is not an object is empty, and an answer without a schema is not the view', () => {
    const v = parseLanes({ schema_version: 2, you: 'x', claude: null, brain: 7 })!;
    expect(v.you).toEqual(empty);
    expect(v.brain).toEqual({ ...empty, why: null });
    expect(parseLanes({ you: VIEW.you })).toBeNull();
    expect(parseLanes(null)).toBeNull();
  });

  it('an older backend\'s answer (lane 3 as `bots`, no `brain`) parses, and the brain\'s lane reads empty', () => {
    const v = parseLanes(VIEW_V1)!;
    expect(v.schema_version).toBe(1);
    expect(v.you.symbol).toBe('XLAB');
    expect(v.claude.symbol).toBe('AISP');
    expect(v.brain).toEqual({ ...empty, why: null });
    expect(v).not.toHaveProperty('bots');
    expect(lanesOn(v, 'RUNR')).toEqual([]);
    const rec = laneRecording(v, null);
    expect(rec.symbols).toEqual(['XLAB', 'AISP']);
    expect(rec.owners).toEqual({ XLAB: ['you'], AISP: ['claude'] });
    expect(rec.why).toEqual({});
  });

  it('says which lanes are on a stock: two lanes on one stock share its lines', () => {
    const v = parseLanes(VIEW)!;
    expect(lanesOn(v, 'aisp')).toEqual(['claude', 'brain']);
    expect(lanesOn(v, 'XLAB')).toEqual(['you']);
    expect(lanesOn(v, 'TGHL')).toEqual([]);
    expect(lanesOn(null, 'XLAB')).toEqual([]);
  });

  it('who records what: each stock once, yours first, with the brain\'s own words for its stock', () => {
    const sw = parseRecordingSwitch({ mode: 'on', source: 'operator', day: null, until: null, error: null });
    const rec = laneRecording(parseLanes(VIEW), sw);
    expect(rec.symbols).toEqual(['XLAB', 'AISP']);
    expect(rec.owners).toEqual({ XLAB: ['you'], AISP: ['claude', 'brain'] });
    expect(rec.why).toEqual({ AISP: 'First pullback holding the 4.30 bid' });
    expect(rec).not.toHaveProperty('setup');
    expect(rec.switch?.mode).toBe('on');
  });

  it('a lane not recording records nothing and says no why, and no lanes record nothing', () => {
    const rec = laneRecording(parseLanes({ ...VIEW, you: { ...VIEW.you, recording: false } }), null);
    expect(rec.symbols).toEqual(['AISP']);
    const quiet = laneRecording(parseLanes({ ...VIEW, brain: { ...VIEW.brain, symbol: 'RUNR', recording: false } }), null);
    expect(quiet.symbols).toEqual(['XLAB', 'AISP']);
    expect(quiet.why).toEqual({});
    expect(laneRecording(null, null)).toMatchObject({ symbols: [], switch: null });
  });

  it('reads the recording switch only in a shape it knows', () => {
    expect(parseRecordingSwitch({ mode: 'off_today', source: 'env', day: '2026-11-13', until: 99, error: null }))
      .toEqual({ mode: 'off_today', source: 'env', day: '2026-11-13', until: 99, error: null });
    expect(parseRecordingSwitch({ mode: 'sometimes', source: 'operator' })).toBeNull();
    expect(parseRecordingSwitch('on')).toBeNull();
  });
});
