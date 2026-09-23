/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KILL_SWITCH_RESET_LABEL, KILL_SWITCH_TRIP_LABEL } from '../constantGroups/bot';
import { KillSwitchCard } from './KillSwitchCard';
import { parseKillSwitch } from './killSwitchApi';

vi.mock('../ux/appDialogApi', () => ({ confirmApp: vi.fn(async () => true) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubKillSwitch(initial: boolean) {
  let tripped = initial;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (init?.method === 'POST') tripped = !href.endsWith('/reset');
    return { ok: true, json: async () => ({ tripped, reason: null, ts: null }) };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('KillSwitchCard', () => {
  it('trips the latch and then offers the reset', async () => {
    const fetchMock = stubKillSwitch(false);
    render(<KillSwitchCard />);
    await flush();
    expect(screen.getByTestId('bot-kill-switch-state').textContent).toMatch(/Off/);

    fireEvent.click(screen.getByText(KILL_SWITCH_TRIP_LABEL));
    await flush();
    expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).endsWith('/kill-switch') && (init as RequestInit | undefined)?.method === 'POST')).toBe(true);
    expect(screen.getByTestId('bot-kill-switch-state').textContent).toMatch(/TRIPPED/);
    expect(screen.getByText(KILL_SWITCH_RESET_LABEL)).toBeTruthy();
  });

  it('resets a latch that was tripped before the page loaded', async () => {
    const fetchMock = stubKillSwitch(true);
    render(<KillSwitchCard />);
    await flush();
    fireEvent.click(screen.getByText(KILL_SWITCH_RESET_LABEL));
    await flush();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/kill-switch/reset'))).toBe(true);
    expect(screen.getByTestId('bot-kill-switch-state').textContent).toMatch(/Off/);
  });

  it('states an unreadable answer instead of guessing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({}) })));
    render(<KillSwitchCard />);
    await flush();
    expect(screen.getByTestId('bot-kill-switch-state').textContent).toMatch(/Unknown/);
    expect((screen.getByText(KILL_SWITCH_TRIP_LABEL) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('parseKillSwitch', () => {
  it('needs a boolean tripped', () => {
    expect(parseKillSwitch({ tripped: true, reason: 'kill_switch', ts: 1 })).toEqual({
      tripped: true, reason: 'kill_switch', ts: 1,
    });
    expect(parseKillSwitch({})).toBeNull();
    expect(parseKillSwitch(null)).toBeNull();
  });
});
