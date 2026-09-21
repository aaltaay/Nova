import { describe, expect, it } from 'vitest';
import type { IbkrStatus } from '../ibkr/types';
import { elapsedLabel, recordingView, stoppedView } from './recordingSignalModel';

const NOW = Date.parse('2026-09-21T12:00:00-04:00');

function status(overrides: Partial<IbkrStatus> = {}): IbkrStatus {
  return { enabled: true, connected: true, mode: 'live', ...overrides };
}

describe('recordingView', () => {
  it('describes the running recording from the server session', () => {
    const view = recordingView(status({
      recording: true,
      capture_symbol: 'GRML',
      capture_session: {
        symbol: 'GRML', session_date: '2026-09-21', started_et: '2026-09-21T11:46:35-04:00',
        segment_started_et: '2026-09-21T11:58:00-04:00', segment: 2,
        counts: { prints: 2439, quotes: 229, l2: 229 }, last_write_ts: NOW / 1000 - 3,
        dir: 'F:\\Nova\\sim_capture\\2026-09-21\\GRML', reacquired: 1,
      },
    }), 'GRML', NOW);
    expect(view).toMatchObject({
      symbol: 'GRML', segment: 2, prints: 2439, quotes: 229, l2: 229, lastWriteAgeSec: 3, reacquired: 1,
    });
    expect(view?.sinceMs).toBe(13 * 60 * 1000 + 25 * 1000);
  });

  it('is nothing when the fresh symbol and the session disagree', () => {
    const session = {
      symbol: 'IMCC', session_date: null, started_et: null, segment_started_et: null, segment: 1,
      counts: {}, last_write_ts: null, dir: null, reacquired: 0,
    };
    expect(recordingView(status({ capture_session: session }), 'GRML', NOW)).toBeNull();
    expect(recordingView(status({ capture_session: session }), null, NOW)).toBeNull();
  });
});

describe('stoppedView', () => {
  const stopped = {
    symbol: 'GRML', at: NOW / 1000 - 10, reason: 'failure', error: 'Capture writer backlog full',
    dir: 'F:/x', counts: { prints: 2439 }, resumed: false,
  };

  it('is the shout, with the resume countdown', () => {
    const view = stoppedView(status({
      capture_stopped: stopped,
      capture_resume: {
        symbol: 'GRML', reason: 'failure', error: null, session_date: '2026-09-21', attempt: 1, max_attempts: 5,
        next_at: NOW / 1000 + 4.2, gave_up: false, gave_up_reason: null, pending: true,
      },
    }), NOW);
    expect(view).toMatchObject({ symbol: 'GRML', reason: 'failure', prints: 2439, key: `GRML|${stopped.at}` });
    expect(view?.resume).toEqual({
      pending: true, attempt: 1, maxAttempts: 5, nextInSec: 5, gaveUp: false, gaveUpReason: null,
    });
  });

  it('ends once the recording is back', () => {
    expect(stoppedView(status({ capture_stopped: { ...stopped, resumed: true } }), NOW)).toBeNull();
    expect(stoppedView(status({ capture_stopped: null }), NOW)).toBeNull();
  });

  it('reports a resume that gave up', () => {
    const view = stoppedView(status({
      capture_stopped: stopped,
      capture_resume: {
        symbol: 'GRML', reason: 'failure', error: null, session_date: '2026-09-21', attempt: 5, max_attempts: 5,
        next_at: 0, gave_up: true, gave_up_reason: '5 attempts failed; last: disk gone', pending: false,
      },
    }), NOW);
    expect(view?.resume).toMatchObject({ pending: false, gaveUp: true, gaveUpReason: '5 attempts failed; last: disk gone' });
  });
});

describe('elapsedLabel', () => {
  it('reads like a stopwatch', () => {
    expect(elapsedLabel(null)).toBe('--');
    expect(elapsedLabel(12_000)).toBe('12s');
    expect(elapsedLabel(4 * 60_000 + 5_000)).toBe('4m 05s');
    expect(elapsedLabel(72 * 60_000)).toBe('1h 12m');
  });
});
