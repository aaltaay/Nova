/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { recordingChipTitle, RECORDING_STOP_REASONS } from '../capture/constants';
import { stoppedViews } from '../capture/recordingSignalModel';
import { normalizeIbkrStatus } from '../ibkr/ibkrStatusNormalize';
import type { IbkrStatus, LeaderboardRecorderStatus } from '../ibkr/types';
import { ownRecordingFor } from '../sim/ownRecording';
import { captureMissingSeconds } from '../sim/simCoverage';
import { LeaderboardRecorderToast } from './LeaderboardRecorderToast';

const status = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => status.current }));

const recorder = (over: Partial<LeaderboardRecorderStatus>): LeaderboardRecorderStatus => ({
  recording: true, ok: true, error: null, since: 1, run_id: 'r1', ...over,
});

afterEach(() => cleanup());

describe('LeaderboardRecorderToast', () => {
  it('stays silent while the recorder is healthy -- no chip, no toast', () => {
    status.current = { leaderboard_recorder: recorder({}) };
    render(<LeaderboardRecorderToast />);
    expect(screen.queryByTestId('leaderboard-recorder-toast')).toBeNull();
  });

  it('fires ONE toast when ok flips to false, and not again until it recovers and fails again', () => {
    status.current = { leaderboard_recorder: recorder({}) };
    const { rerender } = render(<LeaderboardRecorderToast />);
    status.current = { leaderboard_recorder: recorder({ ok: false, error: 'database is locked' }) };
    rerender(<LeaderboardRecorderToast />);
    expect(screen.getAllByTestId('leaderboard-recorder-toast')).toHaveLength(1);
    expect(screen.getByRole('alert').textContent).toMatch(/Scanner board recording failed.*database is locked/);

    fireEvent.click(screen.getByTestId('leaderboard-recorder-toast-dismiss'));
    status.current = { leaderboard_recorder: recorder({ ok: false, error: 'database is locked', since: 2 }) };
    rerender(<LeaderboardRecorderToast />);
    expect(screen.queryByTestId('leaderboard-recorder-toast')).toBeNull();

    status.current = { leaderboard_recorder: recorder({}) };
    rerender(<LeaderboardRecorderToast />);
    status.current = { leaderboard_recorder: recorder({ ok: false, error: 'disk full' }) };
    rerender(<LeaderboardRecorderToast />);
    expect(screen.getAllByTestId('leaderboard-recorder-toast')).toHaveLength(1);
  });
});

describe('status fields and the planned "auto" stop (ADR 023)', () => {
  it('parses the recorder and auto-record blocks; a malformed block is unknown, never a failure', () => {
    const parsed = normalizeIbkrStatus({
      connected: true, mode: 'sim',
      leaderboard_recorder: { recording: true, ok: false, error: 'disk full', since: 5, run_id: 7 },
      auto_record: { active: true, window: '07:00-10:00', symbols: ['GRML', 3], yielded: 'x', last_error: null },
    })!;
    expect(parsed.leaderboard_recorder).toEqual({ recording: true, ok: false, error: 'disk full', since: 5, run_id: null });
    expect(parsed.auto_record).toEqual({ active: true, window: '07:00-10:00', symbols: ['GRML'], yielded: [], last_error: null });
    expect(normalizeIbkrStatus({ mode: 'sim', leaderboard_recorder: 'broken' })!.leaderboard_recorder).toBeNull();
    expect(normalizeIbkrStatus({ mode: 'sim', leaderboard_recorder: {} })!.leaderboard_recorder?.ok).toBe(true);
  });

  it('an auto stop is labelled, quiet (no toast) and leaves no "missing" gap', () => {
    expect(RECORDING_STOP_REASONS.auto).toMatch(/auto-record/);
    const stopped = { symbol: 'GRML', at: 100, reason: 'auto', error: null, dir: null, counts: { prints: 5 }, resumed: false };
    const st = { mode: 'sim', connected: true, enabled: true, capture_stopped: [stopped] } as unknown as IbkrStatus;
    expect(stoppedViews(st, 0)).toEqual([]);
    expect(stoppedViews({ ...st, capture_stopped: [{ ...stopped, reason: 'failure' }] } as IbkrStatus, 0)).toHaveLength(1);
    const clock = {
      sim: true, session_close_et: '2026-09-21T20:00:00-04:00',
      replay_load: { segments: [
        { started_et: '2026-09-21T07:00:00-04:00', stopped_et: '2026-09-21T08:00:00-04:00', reason: 'auto' },
        { started_et: '2026-09-21T09:00:00-04:00', stopped_et: '2026-09-21T09:30:00-04:00', reason: 'failure' },
      ] },
    };
    expect(captureMissingSeconds(clock)).toBe(0);
  });

  it('the REC chip card marks an auto-recorded symbol "auto"', () => {
    const card = recordingChipTitle({
      symbol: 'GRML', elapsed: '5m', sessionElapsed: '5m', segment: 1, prints: 1, quotes: 1, l2: 1,
      lastWriteAgeSec: 1, reacquired: 0, dir: null, auto: true,
    });
    expect(card).toMatch(/^auto -- recorded by auto-record/m);
  });

  it("a Sim tab offers the desk day's own recording before today's", () => {
    const sessions = { days: [], tickers_by_day: {
      '2026-09-22': [{ symbol: 'GRML', prints: 50, l2: 1, usable: true, status: 'recording' }],
      '2026-09-18': [{ symbol: 'GRML', prints: 900, l2: 1, usable: true, status: 'stopped_partial_ok' }],
    } };
    expect(ownRecordingFor(sessions, 'GRML', '2026-09-22', '2026-09-18')?.date).toBe('2026-09-18');
    expect(ownRecordingFor(sessions, 'GRML', '2026-09-22')?.date).toBe('2026-09-22');
    expect(ownRecordingFor(sessions, 'GRML', '2026-09-22', '2026-09-17')?.date).toBe('2026-09-22');
  });
});
