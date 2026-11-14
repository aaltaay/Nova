/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  GLOBAL_BAR_FREEZE_TIP,
  GLOBAL_BAR_FREEZE_TIP_TITLE,
  GLOBAL_BAR_FROZEN_LABEL,
  GLOBAL_BAR_FROZEN_TIP,
} from '../constantGroups/global_bar';
import type { KillSwitchControl } from './useKillSwitch';

const control: { current: KillSwitchControl } = {
  current: { status: null, error: null, busy: false, sweep: null, act: vi.fn(async () => true) },
};
vi.mock('./useKillSwitch', () => ({ useKillSwitch: () => control.current }));

import { FreezeOrdersButton } from './FreezeOrdersButton';

function set(patch: Partial<KillSwitchControl>) {
  control.current = { ...control.current, ...patch };
}

describe('FreezeOrdersButton (ADR 072: right of KILL)', () => {
  afterEach(cleanup);

  beforeEach(() => {
    control.current = { status: null, error: null, busy: false, sweep: null, act: vi.fn(async () => true) };
  });

  it('says on hover exactly what a click does', () => {
    set({ status: { tripped: false, reason: null, ts: null } });
    render(<FreezeOrdersButton />);
    const btn = screen.getByTestId('global-bar-freeze');
    expect(btn.textContent).toContain('Freeze');
    expect(btn.getAttribute('data-tip')).toBe(GLOBAL_BAR_FREEZE_TIP);
    expect(btn.getAttribute('data-tip-title')).toBe(GLOBAL_BAR_FREEZE_TIP_TITLE);
    expect(GLOBAL_BAR_FREEZE_TIP).toMatch(/Cancels every working order on Live, Paper and Sim/);
    expect(GLOBAL_BAR_FREEZE_TIP).toMatch(/a stop that protects a position/);
    expect(GLOBAL_BAR_FREEZE_TIP).toMatch(/refuses every new order, a sell included, until you unfreeze/);
    expect(GLOBAL_BAR_FREEZE_TIP).toMatch(/It sells nothing/);
  });

  it('freezes on click (the hook confirms first)', () => {
    set({ status: { tripped: false, reason: null, ts: null } });
    render(<FreezeOrdersButton />);
    fireEvent.click(screen.getByTestId('global-bar-freeze'));
    expect(control.current.act).toHaveBeenCalledWith(true);
  });

  it('reads Frozen · Unfreeze while frozen, and a click unfreezes', () => {
    set({ status: { tripped: true, reason: 'operator', ts: 1 } });
    render(<FreezeOrdersButton />);
    const btn = screen.getByTestId('global-bar-freeze');
    expect(btn.textContent).toContain(GLOBAL_BAR_FROZEN_LABEL);
    expect(btn.getAttribute('data-frozen')).toBe('true');
    expect(btn.getAttribute('data-tip')).toBe(GLOBAL_BAR_FROZEN_TIP);
    fireEvent.click(btn);
    expect(control.current.act).toHaveBeenCalledWith(false);
  });

  it('is locked with its reason until Nova says whether orders are frozen', () => {
    render(<FreezeOrdersButton />);
    const btn = screen.getByTestId('global-bar-freeze');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(btn.getAttribute('data-why')).toMatch(/has not said yet/);
  });

  it('opens what it did on each venue under it, and closes it', () => {
    set({ status: { tripped: false, reason: null, ts: null } });
    const view = render(<FreezeOrdersButton />);
    set({
      status: { tripped: true, reason: 'operator', ts: 1 },
      sweep: [
        { venue: 'paper', cancelled: [7009, 7010], failed: [], kept: [7011], error: null },
        { venue: 'live', cancelled: [], failed: [], kept: [], error: null },
      ],
    });
    view.rerender(<FreezeOrdersButton />);
    const card = screen.getByTestId('global-bar-freeze-did');
    expect(screen.getByTestId('global-bar-freeze-did-paper').textContent)
      .toBe('Paper: cancelled 2 orders (#7009, #7010) · kept 1 protective stop resting (#7011)');
    expect(screen.getByTestId('global-bar-freeze-did-live').textContent).toContain('Live: nothing was working');
    expect(card.textContent).toContain('Unfreeze lets new orders through again.');
    act(() => {
      fireEvent.click(screen.getByTestId('global-bar-freeze-did-close'));
    });
    expect(screen.queryByTestId('global-bar-freeze-did')).toBeNull();
  });

  it('shows a refused press in its own words', () => {
    set({ status: { tripped: false, reason: null, ts: null } });
    const view = render(<FreezeOrdersButton />);
    set({ error: 'Sample data: nothing is sent' });
    view.rerender(<FreezeOrdersButton />);
    expect(screen.getByTestId('global-bar-freeze-error').textContent).toContain('Sample data: nothing is sent');
  });
});
