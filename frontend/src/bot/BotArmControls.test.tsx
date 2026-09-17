/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BotArmControls } from './BotArmControls';
import type { BotSession } from './types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 0,
    armed: false,
    has_desk_arm: false,
    strategy: null,
    active_pack: 'halt-luld',
    packs: [
      { id: 'halt-luld', label: 'Halt / LULD resume', status: 'live' },
      { id: 'quote-spike', label: 'Quote spike (stub)', status: 'stub' },
      { id: 'volume', label: 'Volume boost (stub)', status: 'stub' },
    ],
    symbol_allowlist: [],
    brain_session_id: null,
    brain_alive: false,
    live_fire_ready: false,
    caps: {
      max_shares: 1,
      bp_budget_usd: 50,
      working_ttl_sec: 3,
      extended_hours: false,
      allowlist: [],
    },
    advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
    soft_breaker_fired: false,
    hard_lock_until_date: null,
    day_lock_active: false,
    focus: [],
    trader_live: [],
    working: [],
    ...partial,
  };
}

function mockFetch(handler: (url: string, init?: RequestInit) => BotSession | Record<string, unknown>) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/bot/proposals')) return { ok: true, json: async () => ({ proposals: [] }) };
    if (href.includes('/bot/audit')) return { ok: true, json: async () => ({ entries: [] }) };
    return { ok: true, json: async () => handler(href, init) };
  }));
}

describe('BotArmControls', () => {
  it('Activate then L2 stores the desk token and patches with the arm header', async () => {
    mockFetch((href, init) => {
      if (href.includes('/session/arm')) {
        return session({ armed: true, has_desk_arm: true, desk_arm_token: 'desk-token-1' });
      }
      if (href.includes('/bot/session') && init?.method === 'PATCH') {
        return session({ level: 2, armed: true, has_desk_arm: true, strategy: 'small-cap' });
      }
      return session();
    });

    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-arm-activate'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(localStorage.getItem('nova_bot_desk_arm')).toBe('desk-token-1');

    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-arm-level'), { target: { value: '2' } });
      await Promise.resolve();
      await Promise.resolve();
    });

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    expect(patchCall).toBeTruthy();
    const headers = new Headers((patchCall?.[1] as RequestInit).headers);
    expect(headers.get('X-Nova-Desk-Arm')).toBe('desk-token-1');
    expect(String((patchCall?.[1] as RequestInit).body)).toContain('"level":2');
  });

  it('flashes live-fire ready when L2 + Activate + heartbeat', async () => {
    mockFetch(() => session({
      level: 2,
      armed: true,
      has_desk_arm: true,
      strategy: 'small-cap',
      brain_session_id: 'nova-brain',
      brain_alive: true,
      live_fire_ready: true,
    }));

    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByTestId('bot-arm-controls').className).toContain('bot-arm--live');
    expect(screen.getByTestId('bot-arm-status').textContent).toMatch(/L2 live/);
  });
});
