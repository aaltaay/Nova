/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SimReplayTargetNotice } from './SimReplayTargetNotice';
import type { SimClockState } from './simClockTypes';

const mocks = vi.hoisted(() => ({ openStockView: vi.fn(), mode: 'sim' as string }));
vi.mock('../workspace', () => ({ useWorkspace: () => ({ openStockView: mocks.openStockView }) }));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.mode }) }));

// useSyncExternalStore requires a STABLE snapshot reference between calls, the
// same contract replayPollResource keeps by publishing one state object. A mock
// that rebuilds the object each read loops forever.
let state: { data: SimClockState | null; error: string | null } = { data: null, error: null };
const setClock = (clock: SimClockState | null) => { state = { data: clock, error: null }; };
vi.mock('./simClockResource', () => ({
  simClockResource: {
    subscribe: () => () => {},
    getSnapshot: () => state,
  },
}));

beforeEach(() => {
  mocks.openStockView.mockReset();
  mocks.mode = 'sim';
  setClock(null);
});
afterEach(cleanup);

const notice = () => screen.queryByTestId('sim-replay-target-notice');

describe('SimReplayTargetNotice', () => {
  it('renders nothing before the clock is read', () => {
    render(<SimReplayTargetNotice symbol="IMCC" />);
    expect(notice()).toBeNull();
  });

  it('renders nothing outside Sim, even with a stale replay on the clock', () => {
    mocks.mode = 'paper';
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY' });
    render(<SimReplayTargetNotice symbol="IMCC" />);
    expect(notice()).toBeNull();
  });

  it('names the empty desk and points at the loader, with no dead button', () => {
    setClock({ sim: true, replay_source: 'none' });
    render(<SimReplayTargetNotice symbol="IMCC" />);
    expect(notice()?.textContent).toContain('No replay loaded');
    expect(notice()?.textContent).toContain('archived');
    expect(screen.queryByTestId('sim-replay-target-goto')).toBeNull();
  });

  it('names the replayed symbol and switches to it on click -- the wrong-tab exit', () => {
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY' });
    render(<SimReplayTargetNotice symbol="IMCC" />);
    expect(notice()?.textContent).toContain('SPY is the loaded replay');
    fireEvent.click(screen.getByTestId('sim-replay-target-goto'));
    expect(mocks.openStockView).toHaveBeenCalledWith('SPY');
  });

  it('is silent on the replayed tab itself', () => {
    setClock({ sim: true, replay_source: 'historical', replay_symbol: 'SPY' });
    render(<SimReplayTargetNotice symbol="SPY" />);
    expect(notice()).toBeNull();
  });

  it('shows a failed selection as failed, not as an empty desk', () => {
    setClock({
      sim: true, replay_source: 'none', replay_ok: false, replay_error: 'Capture is empty',
    });
    render(<SimReplayTargetNotice symbol="SPY" />);
    expect(notice()?.textContent).toContain('Capture is empty');
    expect(notice()?.className).toContain('sim-replay-target--failed');
  });
});
