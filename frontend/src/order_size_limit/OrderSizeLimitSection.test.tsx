/**
 * @vitest-environment jsdom
 *
 * Settings > Loss limits, under the daily loss limit (ADR 064): Max shares and Max risk at stop for Paper and
 * Sim, every box empty until typed, each saved on its own.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderSizeLimitPatch, OrderSizeLimitSettings, OrderSizeLimitView } from './orderSizeLimitApi';
import { OrderSizeLimitSection, parseLimit } from './OrderSizeLimitSection';

const api = vi.hoisted(() => ({
  fetchOrderSizeLimit: vi.fn(),
  saveOrderSizeLimit: vi.fn(),
}));
vi.mock('./orderSizeLimitApi', () => api);

const OFF = { max_shares: null, max_risk_usd: null };
const RULES = { venues: ['paper', 'sim'] as ('paper' | 'sim')[], min_shares: 1, max_shares: 1_000_000, min_risk_usd: 1, max_risk_usd: 1_000_000 };

let saved: OrderSizeLimitSettings;

function view(settings: OrderSizeLimitSettings): OrderSizeLimitView {
  return { schema_version: 1, settings, rules: RULES };
}

async function mount() {
  await act(async () => {
    render(<OrderSizeLimitSection />);
  });
  await act(async () => { await Promise.resolve(); });
}

function box(name: string): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

async function type(name: string, value: string, how: 'enter' | 'blur' = 'enter') {
  const input = box(name);
  fireEvent.change(input, { target: { value } });
  await act(async () => {
    if (how === 'enter') fireEvent.keyDown(input, { key: 'Enter' });
    else fireEvent.blur(input);
  });
}

beforeEach(() => {
  saved = { venues: { paper: { ...OFF }, sim: { ...OFF } }, set_at: null, source: 'default', error: null };
  api.fetchOrderSizeLimit.mockImplementation(async () => view(saved));
  api.saveOrderSizeLimit.mockImplementation(async (patch: OrderSizeLimitPatch) => {
    saved = {
      ...saved, source: 'operator', error: null,
      venues: {
        paper: { ...saved.venues.paper, ...patch.paper },
        sim: { ...saved.venues.sim, ...patch.sim },
      },
    };
    return view(saved);
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('parseLimit', () => {
  it('reads empty as no limit and whole numbers in range as themselves', () => {
    expect(parseLimit('')).toBeNull();
    expect(parseLimit('  ')).toBeNull();
    expect(parseLimit('100')).toBe(100);
    expect(parseLimit('$1,000')).toBe(1000);
    for (const bad of ['0', '12.5', '-3', 'abc', '1000001']) expect(parseLimit(bad)).toBeUndefined();
  });
});

describe('OrderSizeLimitSection', () => {
  it('ships with every box empty, under its title, Paper and Sim side by side', async () => {
    await mount();
    expect(screen.getByText('Order size limit')).toBeTruthy();
    expect(screen.getByText('Paper')).toBeTruthy();
    expect(screen.getByText('Sim')).toBeTruthy();
    expect(screen.getByText('empty box = no limit')).toBeTruthy();
    for (const name of ['Paper Max shares', 'Sim Max shares', 'Paper Max risk at stop', 'Sim Max risk at stop']) {
      expect(box(name).value).toBe('');
    }
  });

  it('saves one box at a time, with only its own venue and field', async () => {
    await mount();
    await type('Paper Max shares', '100');
    expect(api.saveOrderSizeLimit).toHaveBeenLastCalledWith({ paper: { max_shares: 100 } });
    await type('Sim Max risk at stop', '20', 'blur');
    expect(api.saveOrderSizeLimit).toHaveBeenLastCalledWith({ sim: { max_risk_usd: 20 } });
    expect(box('Paper Max shares').value).toBe('100');
    expect(box('Sim Max risk at stop').value).toBe('20');
    expect(box('Paper Max risk at stop').value).toBe('');
  });

  it('clears a limit when its box is emptied, and saves nothing for a box left as it was', async () => {
    saved = { ...saved, source: 'operator', venues: { paper: { max_shares: 100, max_risk_usd: 20 }, sim: { ...OFF } } };
    await mount();
    await type('Paper Max risk at stop', '20');
    expect(api.saveOrderSizeLimit).not.toHaveBeenCalled();
    await type('Paper Max risk at stop', '');
    expect(api.saveOrderSizeLimit).toHaveBeenCalledWith({ paper: { max_risk_usd: null } });
    expect(box('Paper Max shares').value).toBe('100');
  });

  it('refuses a number out of its rule, says the rule, and saves nothing', async () => {
    await mount();
    await type('Paper Max shares', '12.5');
    expect(screen.getByRole('alert').textContent).toBe('Whole shares, 1 to 1,000,000, or empty for no limit');
    await type('Sim Max risk at stop', '0');
    expect(screen.getByRole('alert').textContent).toBe('Whole dollars, $1 to $1,000,000, or empty for no limit');
    expect(api.saveOrderSizeLimit).not.toHaveBeenCalled();
  });

  it('says a saved file Nova cannot use, and any save replaces it', async () => {
    saved = { ...saved, source: 'unreadable', error: 'Nova could not read the saved order size limit (JSONDecodeError)' };
    await mount();
    expect(screen.getByRole('alert').textContent).toBe(
      'Nova could not read the saved order size limit (JSONDecodeError). ' +
        'Paper and Sim refuse your new orders until a box here is saved.',
    );
    await type('Paper Max shares', '');
    expect(api.saveOrderSizeLimit).toHaveBeenCalledWith({ paper: { max_shares: null } });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('says why a save failed and puts the box back', async () => {
    await mount();
    api.saveOrderSizeLimit.mockRejectedValueOnce(new Error('Max shares is 1 to 1,000,000, or empty for no limit'));
    await type('Paper Max shares', '100');
    expect(screen.getByRole('alert').textContent).toBe(
      'The order size limit was not saved: Max shares is 1 to 1,000,000, or empty for no limit',
    );
    expect(box('Paper Max shares').value).toBe('');
  });
});
