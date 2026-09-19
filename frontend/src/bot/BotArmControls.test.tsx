/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { botAllowlistStripLabel, packDescription } from '../constantGroups/bot';
import { BotArmControls } from './BotArmControls';
import * as botApi from './api';
import type { BotSession } from './types';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { writeTicketSessionUnlocked } from '../ibkr/ticketUnlock';

const ibkrStatus = {
  connected: true,
  spend_status: 'paper_armed',
  spend_locked_reason: null as string | null,
  trading_allowed: true as boolean,
  trading_allowed_reason: null as string | null,
};

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ibkrStatus,
}));

beforeEach(() => {
  sessionStorage.clear();
  writeTicketSessionUnlocked(true);
  ibkrStatus.connected = true;
  ibkrStatus.spend_status = 'paper_armed';
  ibkrStatus.trading_allowed = true;
  ibkrStatus.trading_allowed_reason = null;
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
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
      { id: 'quote-spike', label: 'Quote spike', status: 'live' },
      { id: 'volume', label: 'Volume boost', status: 'live' },
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

function mockFetch(
  handler: (url: string, init?: RequestInit) => BotSession | Record<string, unknown>,
) {
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/bot/proposals')) {
      return { ok: true, status: 200, json: async () => ({ proposals: [] }) };
    }
    if (href.includes('/bot/audit')) {
      return { ok: true, status: 200, json: async () => ({ entries: [] }) };
    }
    const result = handler(href, init);
    if (result && typeof result === 'object' && 'ok' in result && result.ok === false) {
      return result;
    }
    return { ok: true, status: 200, json: async () => result };
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
    expect(screen.getByTestId('bot-arm-controls').className).not.toContain('bot-arm--idle');
    expect(screen.getByTestId('bot-arm-status').textContent).toBe('Active');
    const box = screen.getByTestId('bot-arm-in-control') as HTMLInputElement;
    expect(box.checked).toBe(true);
    expect(screen.getByTestId('bot-arm-in-control-label').textContent).toMatch(/Bot is in control/);
    expect(screen.queryByTestId('bot-arm-activate')).toBeNull();
    expect(screen.getByTestId('bot-arm-stop').textContent).toBe('Deactivate');
  });

  it('does not call Eyes "Bot off" -- level and Active are separate', async () => {
    mockFetch(() => session({ level: 1, armed: false }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const level = screen.getByTestId('bot-arm-level') as HTMLSelectElement;
    expect(level.value).toBe('1');
    expect(level.selectedOptions[0].textContent).toBe('Eyes');
    expect(screen.getByTestId('bot-arm-status').textContent).toBe('Not active');
    expect(screen.getByTestId('bot-arm-status').textContent).not.toMatch(/Bot off/i);
    expect(screen.getByTestId('bot-arm-activate').textContent).toBe('Activate');
    expect(screen.getByTestId('bot-arm-name').textContent).toBe('Bot Autonomy');
  });

  it('surfaces a failed Eyes patch instead of snapping back silently', async () => {
    mockFetch((_href, init) => {
      if (init?.method === 'PATCH') {
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Invalid or missing X-Nova-Api-Key' }),
        };
      }
      return session({ level: 0, armed: false });
    });
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-arm-level'), { target: { value: '1' } });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect((screen.getByTestId('bot-arm-level') as HTMLSelectElement).value).toBe('0');
    expect(screen.getByTestId('bot-arm-error').textContent).toMatch(/Need Nova API key/i);
    expect(screen.getByTestId('bot-arm-api-key')).toBeTruthy();
  });

  it('selecting Strategy arms first and patches with the desk token', async () => {
    mockFetch((href, init) => {
      if (href.includes('/session/arm')) {
        return session({ armed: true, has_desk_arm: true, desk_arm_token: 'desk-token-l2' });
      }
      if (href.includes('/bot/session') && init?.method === 'PATCH') {
        return session({ level: 2, armed: true, has_desk_arm: true, strategy: 'small-cap' });
      }
      return session({ level: 0, armed: false });
    });
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-arm-level'), { target: { value: '2' } });
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/arm'))).toBe(true);
    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    expect(patchCall).toBeTruthy();
    const headers = new Headers((patchCall?.[1] as RequestInit).headers);
    expect(headers.get('X-Nova-Desk-Arm')).toBe('desk-token-l2');
    expect((screen.getByTestId('bot-arm-level') as HTMLSelectElement).value).toBe('2');
    expect(screen.getByTestId('bot-arm-status').textContent).toBe('Active');
  });

  it('marks L0 inactive chrome as idle so the header row can mute', async () => {
    mockFetch(() => session({ level: 0, armed: false, live_fire_ready: false }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-controls').className).toContain('bot-arm--idle');
    expect(screen.getByTestId('bot-arm-controls').className).not.toContain('bot-arm--live');
  });

  it('hides the in-control checkbox at L0 and L1', async () => {
    mockFetch(() => session({ level: 1 }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByTestId('bot-arm-in-control')).toBeNull();
    expect(screen.getByTestId('bot-arm-activate')).toBeTruthy();
  });

  it('checkbox Stop and Activate use the same arm APIs', async () => {
    mockFetch((href) => {
      if (href.includes('/session/disarm')) {
        return session({ level: 2, armed: false, strategy: 'small-cap' });
      }
      if (href.includes('/session/arm')) {
        return session({
          level: 2,
          armed: true,
          has_desk_arm: true,
          desk_arm_token: 'desk-token-2',
          strategy: 'small-cap',
        });
      }
      return session({ level: 2, armed: true, has_desk_arm: true, strategy: 'small-cap' });
    });

    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-arm-in-control'));
      await Promise.resolve();
      await Promise.resolve();
    });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/disarm'))).toBe(true);

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-arm-in-control'));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/arm'))).toBe(true);
  });

  it('shows the session pack sentence under the picker, not only as a tooltip', async () => {
    mockFetch(() => session({
      packs: [
        { id: 'halt-luld', label: 'Halt / LULD resume', status: 'live', description: 'Halt resume sentence.' },
        { id: 'quote-spike', label: 'Quote spike', status: 'live', description: 'Quote spike sentence.' },
        { id: 'volume', label: 'Volume boost', status: 'live', description: 'Volume boost sentence.' },
        { id: 'llm-decide', label: 'LLM decide', status: 'live', description: 'Live fire needs L2 + Activate.' },
      ],
    }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const pack = screen.getByTestId('bot-arm-pack') as HTMLSelectElement;
    const desc = screen.getByTestId('bot-arm-pack-desc');
    expect(desc.textContent).toBe('Halt resume sentence.');
    expect(desc.compareDocumentPosition(pack) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    expect(pack.getAttribute('aria-describedby')).toBe('bot-arm-pack-desc');
    const sentences: Array<[string, string]> = [
      ['quote-spike', 'Quote spike sentence.'],
      ['volume', 'Volume boost sentence.'],
      ['llm-decide', 'Live fire needs L2 + Activate.'],
    ];
    for (const [id, text] of sentences) {
      await act(async () => {
        fireEvent.change(pack, { target: { value: id } });
        await Promise.resolve();
      });
      expect(screen.getByTestId('bot-arm-pack-desc').textContent).toBe(text);
    }
  });

  it('falls back to packDescription when session packs omit description', async () => {
    mockFetch(() => session({
      packs: [
        { id: 'halt-luld', label: 'Halt / LULD resume', status: 'live' },
        { id: 'quote-spike', label: 'Quote spike', status: 'live' },
        { id: 'volume', label: 'Volume boost', status: 'live' },
        { id: 'llm-decide', label: 'LLM decide', status: 'live' },
      ],
    }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-pack-desc').textContent).toBe(packDescription('halt-luld'));
    const pack = screen.getByTestId('bot-arm-pack') as HTMLSelectElement;
    await act(async () => {
      fireEvent.change(pack, { target: { value: 'quote-spike' } });
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-pack-desc').textContent).toBe(packDescription('quote-spike'));
    await act(async () => {
      fireEvent.change(pack, { target: { value: 'volume' } });
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-pack-desc').textContent).toBe(packDescription('volume'));
    await act(async () => {
      fireEvent.change(pack, { target: { value: 'llm-decide' } });
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-pack-desc').textContent).toBe(packDescription('llm-decide'));
  });

  it('places Allowlist immediately after Pack and before other strip chrome', async () => {
    mockFetch(() => session({
      symbol_allowlist: ['ABCD', 'EFGH', 'IJKL'],
      caps: {
        max_shares: 1,
        bp_budget_usd: 50,
        working_ttl_sec: 3,
        extended_hours: false,
        allowlist: ['buy_market'],
      },
    }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const pack = screen.getByTestId('bot-arm-pack');
    const allow = screen.getByTestId('bot-arm-allowlist');
    const status = screen.getByTestId('bot-arm-status');
    expect(pack.closest('label')?.nextElementSibling).toBe(allow);
    expect(pack.compareDocumentPosition(allow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(allow.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId('bot-arm-allowlist-toggle').textContent).toBe(
      botAllowlistStripLabel(3),
    );
    expect(allow.textContent).not.toMatch(/buy_market/);
  });

  it('keeps Allowlist on the strip when the pack is not halt-luld', async () => {
    mockFetch(() => session({ active_pack: 'quote-spike' }));
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByTestId('bot-arm-allowlist-toggle')).toBeTruthy();
    const pack = screen.getByTestId('bot-arm-pack') as HTMLSelectElement;
    expect(pack.value).toBe('quote-spike');
    expect(pack.closest('label')?.nextElementSibling).toBe(
      screen.getByTestId('bot-arm-allowlist'),
    );
  });

  it('add/remove from the strip popover call postBotAllowlist', async () => {
    const ops: Array<{ symbol: string; op: string }> = [];
    const postSpy = vi.spyOn(botApi, 'postBotAllowlist');
    mockFetch((href, init) => {
      if (href.includes('/bot/allowlist') && init?.method === 'POST') {
        const body = JSON.parse(String(init.body || '{}')) as { symbol: string; op: string };
        ops.push(body);
        return session({
          symbol_allowlist: body.op === 'remove' ? [] : ['ABCD', String(body.symbol).toUpperCase()],
        });
      }
      return session({ symbol_allowlist: ['ABCD'] });
    });

    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-arm-allowlist-toggle'));
    });
    const panel = screen.getByTestId('bot-arm-allowlist-panel');
    expect(panel.textContent).toMatch(/ABCD/);
    expect(panel.textContent).toMatch(/right-click/i);
    expect(panel.textContent).not.toMatch(/buy_market/);

    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-arm-allowlist-input'), {
        target: { value: 'efgh' },
      });
      fireEvent.click(screen.getByTestId('bot-arm-allowlist-add'));
      await Promise.resolve();
    });
    expect(ops).toContainEqual({ symbol: 'efgh', op: 'add' });
    expect(postSpy).toHaveBeenCalledWith('efgh', 'add');

    await act(async () => {
      fireEvent.click(screen.getByTestId('bot-arm-allowlist-remove-ABCD'));
      await Promise.resolve();
    });
    expect(ops).toContainEqual({ symbol: 'ABCD', op: 'remove' });
    expect(postSpy).toHaveBeenCalledWith('ABCD', 'remove');
    postSpy.mockRestore();
  });

  it('does not look Active or allow Activate when places are blocked', async () => {
    writeTicketSessionUnlocked(false);
    mockFetch((href) => {
      if (href.includes('/session/arm')) {
        return session({ armed: true, has_desk_arm: true, desk_arm_token: 'blocked' });
      }
      return session();
    });
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const activate = screen.getByTestId('bot-arm-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(screen.getByTestId('bot-arm-status').textContent).toBe('Not active');
    expect(screen.getByTestId('bot-arm-controls').className).not.toContain('bot-arm--armed');
    await act(async () => {
      fireEvent.click(activate);
      await Promise.resolve();
    });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/arm'))).toBe(false);
  });

  it('disarms and shows why when armed while the padlock is locked', async () => {
    writeTicketSessionUnlocked(false);
    mockFetch((href) => {
      if (href.includes('/session/disarm')) {
        return session({ level: 2, armed: false, strategy: 'small-cap' });
      }
      return session({
        level: 2,
        armed: true,
        has_desk_arm: true,
        strategy: 'small-cap',
        live_fire_ready: true,
      });
    });
    await act(async () => {
      render(<BotArmControls />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    const status = screen.getByTestId('bot-arm-status').textContent || '';
    expect(status).not.toBe('Active');
    expect(screen.getByTestId('bot-arm-controls').className).not.toContain('bot-arm--armed');
    expect(screen.getByTestId('bot-arm-controls').className).not.toContain('bot-arm--live');
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/disarm'))).toBe(true);
  });
});
