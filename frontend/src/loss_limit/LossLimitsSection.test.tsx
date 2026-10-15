/**
 * @vitest-environment jsdom
 *
 * Settings > Loss limits (ADR 056): the dollar field and three checkboxes, each saved at once.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { LossLimitPatch, LossLimitSettings, LossLimitView } from './lossLimitApi';
import { LossLimitsSection } from './LossLimitsSection';

const api = vi.hoisted(() => ({
  fetchLossLimit: vi.fn(),
  saveLossLimit: vi.fn(),
}));
vi.mock('./lossLimitApi', () => api);

const SETTINGS: LossLimitSettings = {
  limit_usd: 2000, warn: true, no_new_buys: true, auto_sell: false, set_at: null, source: 'default', error: null,
};

function view(settings: Partial<LossLimitSettings> = {}): LossLimitView {
  return { schema_version: 1, settings: { ...SETTINGS, ...settings }, day: '2026-10-15', until: 0, accounts: {}, error: null };
}

async function mount() {
  await act(async () => {
    render(<LossLimitsSection />);
  });
  await act(async () => { await Promise.resolve(); });
}

beforeEach(() => {
  api.fetchLossLimit.mockResolvedValue(view());
  api.saveLossLimit.mockImplementation(async (patch: LossLimitPatch) => view(patch));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('LossLimitsSection', () => {
  it('shows the limit and the three checkboxes as saved', async () => {
    await mount();
    expect((screen.getByLabelText(/Daily loss limit/) as HTMLInputElement).value).toBe('2000');
    const warn = document.getElementById('loss-limit-warn') as HTMLInputElement;
    const noNewBuys = document.getElementById('loss-limit-no_new_buys') as HTMLInputElement;
    const autoSell = document.getElementById('loss-limit-auto_sell') as HTMLInputElement;
    expect([warn.checked, noNewBuys.checked, autoSell.checked]).toEqual([true, true, false]);
    expect(screen.getByText('Warn me')).toBeTruthy();
    expect(screen.getByText('No new buys')).toBeTruthy();
    expect(screen.getByText('Auto sell')).toBeTruthy();
  });

  it('saves a checkbox at once, with only its own key', async () => {
    await mount();
    const autoSell = document.getElementById('loss-limit-auto_sell') as HTMLInputElement;
    await act(async () => {
      fireEvent.click(autoSell);
    });
    expect(api.saveLossLimit).toHaveBeenCalledTimes(1);
    expect(api.saveLossLimit).toHaveBeenCalledWith({ auto_sell: true });
    expect((document.getElementById('loss-limit-auto_sell') as HTMLInputElement).checked).toBe(true);
  });

  it('refuses a limit that is not whole dollars in range, says why, and saves nothing', async () => {
    await mount();
    const input = screen.getByLabelText(/Daily loss limit/) as HTMLInputElement;
    for (const bad of ['12.50', '5', 'abc']) {
      fireEvent.change(input, { target: { value: bad } });
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' });
      });
      expect(screen.getByRole('alert').textContent).toBe('Whole dollars, $10 to $1,000,000');
    }
    expect(api.saveLossLimit).not.toHaveBeenCalled();
  });

  it('saves a new limit on Enter', async () => {
    await mount();
    const input = screen.getByLabelText(/Daily loss limit/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '$1,500' } });
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    expect(api.saveLossLimit).toHaveBeenCalledWith({ limit_usd: 1500 });
  });
});
