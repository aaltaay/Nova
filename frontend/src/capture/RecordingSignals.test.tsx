/** @vitest-environment jsdom */
import { act, type ReactElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import {
  _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests, pollIbkrStatusOnce,
} from '../ibkr/ibkrStatusPoller';
import type { IbkrStatus } from '../ibkr/types';
import { RecordingChip } from './RecordingChip';
import { RecordingSignals } from './RecordingSignals';
import { _resetSessionRecordStoreForTests } from './sessionRecordStore';

const command = vi.hoisted(() => vi.fn());
vi.mock('../api/novaFetch', () => ({ novaFetch: command }));

const NOW = Date.parse('2026-09-21T12:00:00-04:00');
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;

function state(overrides: Partial<IbkrStatus>): IbkrStatus {
  return { mode: 'live', connected: true, enabled: true, capture: false, recording: false, capture_symbol: null, ...overrides };
}

const recording = state({
  capture: true, recording: true, capture_symbol: 'GRML',
  capture_session: {
    symbol: 'GRML', session_date: '2026-09-21', started_et: '2026-09-21T11:46:35-04:00',
    segment_started_et: '2026-09-21T11:46:35-04:00', segment: 1,
    counts: { prints: 2439, quotes: 229, l2: 229 }, last_write_ts: NOW / 1000 - 1, dir: 'F:/x', reacquired: 0,
  },
});

const died = state({
  capture_stopped: {
    symbol: 'GRML', at: NOW / 1000 - 5, reason: 'failure', error: 'Capture writer backlog full',
    dir: 'F:/x', counts: { prints: 2439 }, resumed: false,
  },
  capture_resume: {
    symbol: 'GRML', reason: 'failure', error: null, session_date: '2026-09-21', attempt: 0, max_attempts: 5,
    next_at: NOW / 1000 + 2, gave_up: false, gave_up_reason: null, pending: true,
  },
});

async function poll(body: IbkrStatus) {
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response(body)));
  await act(async () => { await pollIbkrStatusOnce(); });
}

/** The first subscriber starts the poller, whose first fetch must resolve before a test polls. */
async function mount(ui: ReactElement) {
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response(state({}))));
  await act(async () => { render(ui); });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(NOW));
  sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
  _resetIbkrStatusPollerForTests();
  _resetSessionRecordStoreForTests();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  command.mockReset();
});

afterEach(() => {
  cleanup();
  _resetIbkrStatusPollerForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('RecordingSignals', () => {
  it('shows the hairline only while the server says a recording runs', async () => {
    await mount(<RecordingSignals />);
    await poll(state({}));
    expect(screen.queryByTestId('recording-hairline')).toBeNull();
    await poll(recording);
    expect(screen.getByTestId('recording-hairline').title).toBe('Recording GRML');
    await poll(state({}));
    expect(screen.queryByTestId('recording-hairline')).toBeNull();
  });

  it('shouts about a stop the operator did not ask for, and goes quiet once it resumed', async () => {
    const open = vi.fn();
    await mount(<RecordingSignals onOpenSymbol={open} />);
    await poll(died);
    const toast = screen.getByTestId('recording-stopped');
    expect(toast.textContent).toContain('GRML recording stopped on its own');
    expect(toast.textContent).toContain('2,439 prints are on disk. Capture writer backlog full');
    expect(screen.getByTestId('recording-stopped-resume').textContent)
      .toBe('Resuming on its own in 2s (attempt 1 of 5).');
    fireEvent.click(screen.getByTestId('recording-stopped-open'));
    expect(open).toHaveBeenCalledWith('GRML');
    await poll(state({ ...died, capture_stopped: { ...died.capture_stopped!, resumed: true } }));
    expect(screen.queryByTestId('recording-stopped')).toBeNull();
  });

  it('Resume now starts the recording through the same server door', async () => {
    await mount(<RecordingSignals />);
    await poll(died);
    command.mockResolvedValue(response({ capture: true, capture_symbol: 'GRML' }));
    await act(async () => { fireEvent.click(screen.getByTestId('recording-stopped-resume-now')); });
    expect(command).toHaveBeenCalledWith(expect.stringMatching(/\/api\/capture$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ enabled: true, symbol: 'GRML' }),
    }));
  });

  it('a dismissed stop stays dismissed; the next stop is a new shout', async () => {
    await mount(<RecordingSignals />);
    await poll(died);
    fireEvent.click(screen.getByTestId('recording-stopped-dismiss'));
    expect(screen.queryByTestId('recording-stopped')).toBeNull();
    await poll(died);
    expect(screen.queryByTestId('recording-stopped')).toBeNull();
    await poll(state({ capture_stopped: { ...died.capture_stopped!, at: NOW / 1000 + 60 } }));
    expect(screen.getByTestId('recording-stopped')).toBeTruthy();
  });

  it('says when the backend gave up', async () => {
    await mount(<RecordingSignals />);
    await poll(state({
      ...died,
      capture_resume: { ...died.capture_resume!, attempt: 5, gave_up: true, pending: false, gave_up_reason: '5 attempts failed; last: disk gone' },
    }));
    expect(screen.getByTestId('recording-stopped-resume').textContent)
      .toContain('Gave up resuming: 5 attempts failed; last: disk gone');
  });
});

describe('RecordingChip', () => {
  it('exists only while recording, and carries the counts in its tooltip', async () => {
    const open = vi.fn();
    await mount(<RecordingChip onOpenSymbol={open} />);
    await poll(state({}));
    expect(screen.queryByTestId('status-chip-recording')).toBeNull();
    await poll(recording);
    const chip = screen.getByTestId('status-chip-recording');
    expect(chip.textContent).toContain('REC');
    expect(chip.textContent).toContain('GRML · 13m 25s');
    expect(chip.title).toContain('Recording GRML for 13m 25s');
    expect(chip.title).toContain('2,439 prints · 229 quotes · 229 L2 books');
    expect(chip.title).toContain('Last write 1s ago');
    fireEvent.click(chip);
    expect(open).toHaveBeenCalledWith('GRML');
  });

  it('after a resume, "for" is this segment and the tooltip says when the session began', async () => {
    await mount(<RecordingChip />);
    await poll({ ...recording, capture_session: {
      ...recording.capture_session!, segment: 4, segment_started_et: '2026-09-21T11:59:20-04:00',
    } });
    const chip = screen.getByTestId('status-chip-recording');
    expect(chip.textContent).toContain('GRML · 40s');
    expect(chip.title).toContain('Recording GRML for 40s -- segment 4 of a session that began 13m 25s ago');
  });
});
