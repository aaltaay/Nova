/**
 * The three lanes read at the boundary (ADR 071): a malformed lane is an empty one, nothing is invented, and who
 * records what comes from the lanes alone.
 */
import { describe, expect, it } from 'vitest';
import { laneRecording, lanesOn, parseLanes, parseRecordingSwitch } from './lanes';

const empty = { symbol: null, since: null, depth: false, tape: false, recording: false, error: null };

const VIEW = {
  schema_version: 1, generated_at: 5, recording_error: null, tape_capacity: { limit: null },
  you: { symbol: 'xlab', since: 4, depth: true, tape: true, recording: true, error: null },
  claude: { ...empty, symbol: 'AISP', depth: true, tape: true, recording: true },
  bots: { symbol: 'AISP', since: 3, depth: true, tape: true, recording: true, error: null, setup: 'first_pullback',
    why: 'near', waiting: [{ symbol: 'runr', setup: 'bull_flag', why: 'armed' }, { setup: 'x' }, 'junk'] },
};

describe('the lanes view', () => {
  it('reads each lane, upper-cases its stock and drops a malformed waiting setup', () => {
    const v = parseLanes(VIEW)!;
    expect(v.you).toEqual({ symbol: 'XLAB', since: 4, depth: true, tape: true, recording: true, error: null });
    expect(v.bots.setup).toBe('first_pullback');
    expect(v.bots.waiting).toEqual([{ symbol: 'RUNR', setup: 'bull_flag', why: 'armed' }]);
  });

  it('a lane that is not an object is empty, and an answer without a schema is not the view', () => {
    const v = parseLanes({ schema_version: 1, you: 'x', claude: null, bots: 7 })!;
    expect(v.you).toEqual(empty);
    expect(v.bots).toEqual({ ...empty, setup: null, why: null, waiting: [] });
    expect(parseLanes({ you: VIEW.you })).toBeNull();
    expect(parseLanes(null)).toBeNull();
  });

  it('says which lanes are on a stock: two lanes on one stock share its lines', () => {
    const v = parseLanes(VIEW)!;
    expect(lanesOn(v, 'aisp')).toEqual(['claude', 'bots']);
    expect(lanesOn(v, 'XLAB')).toEqual(['you']);
    expect(lanesOn(v, 'TGHL')).toEqual([]);
    expect(lanesOn(null, 'XLAB')).toEqual([]);
  });

  it('who records what: each stock once, yours first, with the bots\' setup and why', () => {
    const sw = parseRecordingSwitch({ mode: 'on', source: 'operator', day: null, until: null, error: null });
    const rec = laneRecording(parseLanes(VIEW), sw);
    expect(rec.symbols).toEqual(['XLAB', 'AISP']);
    expect(rec.owners).toEqual({ XLAB: ['you'], AISP: ['claude', 'bots'] });
    expect(rec.setup).toEqual({ AISP: 'first_pullback' });
    expect(rec.why).toEqual({ AISP: 'near' });
    expect(rec.switch?.mode).toBe('on');
  });

  it('a lane not recording records nothing, and no lanes record nothing', () => {
    const rec = laneRecording(parseLanes({ ...VIEW, you: { ...VIEW.you, recording: false } }), null);
    expect(rec.symbols).toEqual(['AISP']);
    expect(laneRecording(null, null)).toMatchObject({ symbols: [], switch: null });
  });

  it('reads the recording switch only in a shape it knows', () => {
    expect(parseRecordingSwitch({ mode: 'off_today', source: 'env', day: '2026-11-13', until: 99, error: null }))
      .toEqual({ mode: 'off_today', source: 'env', day: '2026-11-13', until: 99, error: null });
    expect(parseRecordingSwitch({ mode: 'sometimes', source: 'operator' })).toBeNull();
    expect(parseRecordingSwitch('on')).toBeNull();
  });
});
