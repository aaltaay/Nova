/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOT_BP_BUDGET_HARD_MAX_USD, BOT_BP_BUDGET_MIN_USD, BOT_BP_BUDGET_STEP_USD } from '../constantGroups/bot';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { writeTicketSessionUnlocked } from '../ibkr/ticketUnlock';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { StrategyTab } from './StrategyTab';
import type { BotAuditEntry, BotGate, BotProposal, BotSession } from './types';

const ibkrStatus = {
  connected: true,
  spend_status: 'paper_armed',
  spend_locked_reason: null as string | null,
  trading_allowed: true as boolean,
  trading_allowed_reason: null as string | null,
};
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ibkrStatus }));
const openStockView = vi.fn();
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => ({ openStockView }) }));

beforeEach(() => {
  sessionStorage.clear();
  writeTicketSessionUnlocked(true);
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
  openStockView.mockReset();
});

const CLOSED_READOUT = {
  state: 'collecting', passed: false, reason: '12 of 50 go setups triggered',
  go: { triggered: 12, scored: 12, win_pct: 58, avg_net_r: 0.31 },
  control: { triggered: 40, scored: 40, win_pct: 27, avg_net_r: -0.18 },
  rules: { kind: 'first_pullback', min_go: 50, fail_go: 100, min_net_r: 0.2 },
};

function gates(overrides: Partial<Record<string, Partial<BotGate>>> = {}): BotGate[] {
  const base: BotGate[] = [
    { id: 'level', ok: false, stage: 'activate', detail: { level: 1 } },
    { id: 'allowlist', ok: true, stage: 'activate', detail: { count: 2 } },
    { id: 'desk_armed', ok: true, stage: 'activate', detail: {} },
    { id: 'depth_lines', ok: false, stage: 'fire', detail: { held: ['GRML'], missing: ['IMCC'] } },
    { id: 'readout', ok: false, stage: 'activate', detail: { state: 'collecting', go_triggered: 12, min_go: 50 } },
    { id: 'bot_trip', ok: true, stage: 'activate', detail: {} },
    { id: 'day_lock', ok: true, stage: 'fire', detail: {} },
    { id: 'kill_switch', ok: true, stage: 'fire', detail: {} },
    { id: 'window', ok: true, stage: 'fire', detail: { start: '07:00', end: '10:00', entries_today: 0, max_entries: 1 } },
  ];
  return base.map(g => ({ ...g, ...(overrides[g.id] ?? {}) }));
}

function session(partial: Partial<BotSession> = {}): BotSession {
  return {
    level: 1, armed: false, has_desk_arm: false, strategy: null,
    setup: 'first_pullback',
    setups: [
      { id: 'first_pullback', scanner: true }, { id: 'gap_and_go', scanner: false },
      { id: 'flat_top_breakout', scanner: false }, { id: 'red_to_green', scanner: false },
      { id: 'micro_pullback', scanner: false },
    ],
    readout: CLOSED_READOUT,
    gates: gates(),
    symbol_allowlist: ['GRML', 'IMCC'],
    brain_session_id: null, brain_alive: false, live_fire_ready: false,
    caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: [] },
    advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
    soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
    focus: [], trader_live: [], working: [],
    ...partial,
  };
}

interface MockOpts {
  session?: BotSession;
  proposals?: BotProposal[];
  audit?: BotAuditEntry[];
  onPatch?: (body: Record<string, unknown>) => BotSession | { ok: false; status: number; json: () => Promise<unknown> };
  onArm?: () => BotSession;
  onDisarm?: () => BotSession;
  onAllowlist?: (body: { symbol: string; op: string }) => BotSession;
}

function mockBotFetch(opts: MockOpts = {}) {
  let current = opts.session ?? session();
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
    if (href.includes('/bot/proposals/')) return json({});
    if (href.includes('/bot/proposals')) return json({ proposals: opts.proposals ?? [] });
    if (href.includes('/bot/audit')) return json({ entries: opts.audit ?? [] });
    if (href.includes('/kill-switch')) return json({ tripped: false, reason: null, ts: null });
    if (href.includes('/setups/scoreboard')) {
      return json({ days: 5, date_from: null, row_count: 0, rows: [], summary: {
        all: { armed: 6, triggered: 2 },
        by: { tape_at_trigger: { go: { triggered: 12, win_pct: 58, avg_net_r: 0.31 }, blind: { triggered: 31, win_pct: 27, avg_net_r: -0.24 } } },
      } });
    }
    if (href.includes('/session/arm')) {
      current = opts.onArm?.() ?? { ...current, armed: true, has_desk_arm: true, desk_arm_token: 'desk-token-1' };
      return json(current);
    }
    if (href.includes('/session/disarm')) {
      current = opts.onDisarm?.() ?? { ...current, armed: false, has_desk_arm: false };
      return json(current);
    }
    if (href.includes('/bot/allowlist') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body || '{}')) as { symbol: string; op: string };
      current = opts.onAllowlist?.(body) ?? current;
      return json(current);
    }
    if (href.includes('/bot/session') && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body || '{}')) as Record<string, unknown>;
      const next = opts.onPatch?.(body);
      if (next && 'ok' in next && next.ok === false) return next;
      if (next) current = next as BotSession;
      return json(current);
    }
    if (href.includes('/bot/session')) return json(current);
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function renderPage() {
  await act(async () => {
    render(<StrategyTab />);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function flush() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe('Bots page (ADR 027)', () => {
  it('shows the playbook: first pullback chosen with its rules and read-out, the other setups waiting on scanners', async () => {
    mockBotFetch();
    await renderPage();
    const strats = within(screen.getByTestId('bots-strategies'));
    const chosen = within(screen.getByTestId('bots-setup-first_pullback'));
    expect(chosen.getByText('First pullback')).toBeTruthy();
    expect(chosen.getByText(/Chosen/)).toBeTruthy();
    expect(chosen.getByText(/Leg >= 5% to a new high/)).toBeTruthy();
    expect(screen.getByTestId('bots-readout-count').textContent).toBe('12 / 50');
    expect(screen.getByTestId('bots-readout').textContent).toMatch(/\+0\.31R/);
    for (const id of ['gap_and_go', 'flat_top_breakout', 'red_to_green', 'micro_pullback']) {
      expect(within(screen.getByTestId(`bots-setup-${id}`)).getByText(/No scanner yet/)).toBeTruthy();
    }
    expect(strats.getByTestId('bots-add-setup').textContent).toMatch(/catalogue/);
    // The retired packs are nowhere on the page.
    expect(screen.queryByText(/Halt \/ LULD|Quote spike|Volume boost|LLM decide/)).toBeNull();
  });

  it('lists every gate the backend checks, the closed ones first-class', async () => {
    mockBotFetch({ session: session({ level: 2, gates: gates({ level: { ok: true, detail: { level: 2 } } }) }) });
    await renderPage();
    expect(screen.getByTestId('bots-gate-readout').textContent).toMatch(/Read-out 12 \/ 50/);
    expect(screen.getByTestId('bots-gate-readout').className).toBe('is-closed');
    expect(screen.getByTestId('bots-gate-depth_lines').textContent).toMatch(/1 \/ 2 held -- open IMCC Level 2/);
    expect(screen.getByTestId('bots-gate-window').textContent).toMatch(/07:00-10:00 · 0 \/ 1 trade today/);
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
  });

  it('refuses Activate at Strategy until the read-out passes, and says why', async () => {
    const fetchMock = mockBotFetch({ session: session({ level: 2, gates: gates({ level: { ok: true, detail: { level: 2 } } }) }) });
    await renderPage();
    const activate = screen.getByTestId('bots-activate') as HTMLButtonElement;
    expect(activate.disabled).toBe(true);
    expect(activate.title).toMatch(/12 of 50 go setups triggered/);
    expect(screen.getByTestId('bots-activate-hint').textContent).toMatch(/Clear the 1 closed gate/);
    await act(async () => { fireEvent.click(activate); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/arm'))).toBe(false);
  });

  it('choosing Strategy activates first and patches with the desk token', async () => {
    const fetchMock = mockBotFetch({
      onPatch: body => session({ level: Number(body.level) as 0 | 1 | 2, armed: false }),
    });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-2')); await flush(); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/arm'))).toBe(true);
    const patchCall = fetchMock.mock.calls.find(([, init]) => init && (init as RequestInit).method === 'PATCH');
    const headers = new Headers((patchCall?.[1] as RequestInit).headers);
    expect(headers.get('X-Nova-Desk-Arm')).toBe('desk-token-1');
    expect(String((patchCall?.[1] as RequestInit).body)).toContain('"level":2');
    // The backend lands Strategy not active while the read-out is closed.
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Not active');
    expect(screen.getByTestId('bots-level-2').getAttribute('aria-checked')).toBe('true');
  });

  it('shows a live bot: Active, Stop, in control', async () => {
    mockBotFetch({ session: session({
      level: 2, armed: true, has_desk_arm: true, live_fire_ready: true, brain_alive: true,
      readout: { ...CLOSED_READOUT, state: 'passed', passed: true },
    }) });
    await renderPage();
    expect(screen.getByTestId('bots-hero').className).toContain('bots-hero--live');
    expect(screen.getByTestId('bots-hero-state').textContent).toBe('Active');
    expect((screen.getByTestId('bots-in-control') as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByTestId('bots-activate')).toBeNull();
    expect(screen.getByTestId('bots-stop')).toBeTruthy();
  });

  it('surfaces a failed level change and offers the API key field', async () => {
    mockBotFetch({
      session: session({ level: 0 }),
      onPatch: () => ({ ok: false, status: 401, json: async () => ({ detail: 'Invalid or missing X-Nova-Api-Key' }) }),
    });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-level-1')); await flush(); });
    expect(screen.getByTestId('bots-level-0').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('bots-error').textContent).toMatch(/Need Nova API key/i);
    expect(screen.getByTestId('bots-api-key')).toBeTruthy();
  });

  it('disarms when armed while the padlock is locked', async () => {
    writeTicketSessionUnlocked(false);
    const fetchMock = mockBotFetch({ session: session({ level: 2, armed: true, has_desk_arm: true }) });
    await renderPage();
    await act(async () => { await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/session/disarm'))).toBe(true);
  });

  it('shows the day lock banner', async () => {
    mockBotFetch({ session: session({ day_lock_active: true, hard_lock_until_date: '2026-09-18' }) });
    await renderPage();
    expect(screen.getByRole('alert').textContent).toMatch(/-\$200 day lock/);
  });

  it('PATCHes the sleeve and Advise through /bot/session', async () => {
    const patches: Record<string, unknown>[] = [];
    mockBotFetch({ onPatch: body => { patches.push(body); return session(); } });
    await renderPage();
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-max-shares'), { target: { value: '4' } });
      fireEvent.change(screen.getByTestId('bot-strategy-bp-budget'), { target: { value: '25' } });
      fireEvent.change(screen.getByTestId('bot-strategy-ttl'), { target: { value: '7' } });
      fireEvent.click(screen.getByTestId('bot-strategy-eh'));
      fireEvent.click(screen.getByTestId('bot-strategy-advise-enabled'));
      await flush();
    });
    expect(patches).toEqual(expect.arrayContaining([
      { caps: { max_shares: 4 } },
      { caps: { bp_budget_usd: 25 } },
      { caps: { working_ttl_sec: 7 } },
      { caps: { extended_hours: true } },
      { advise: { enabled: true } },
    ]));
  });

  it('keeps BP budget cents-step so 25 and 50 are HTML-valid', async () => {
    mockBotFetch();
    await renderPage();
    const input = screen.getByTestId('bot-strategy-bp-budget') as HTMLInputElement;
    expect(Number(input.min)).toBe(BOT_BP_BUDGET_MIN_USD);
    expect(Number(input.max)).toBe(BOT_BP_BUDGET_HARD_MAX_USD);
    expect(Number(input.step)).toBe(BOT_BP_BUDGET_STEP_USD);
    for (const dollars of [25, 50]) {
      const steps = (dollars - Number(input.min)) / Number(input.step);
      expect(Math.abs(steps - Math.round(steps))).toBeLessThan(1e-8);
    }
  });

  it('manages the symbols through POST /bot/allowlist and says which lack a Level 2 line', async () => {
    const ops: Array<{ symbol: string; op: string }> = [];
    let list = ['GRML', 'IMCC'];
    mockBotFetch({ onAllowlist: body => {
      ops.push(body);
      const sym = body.symbol.toUpperCase();
      list = body.op === 'remove' ? list.filter(s => s !== sym) : [...list, sym];
      return session({ symbol_allowlist: list });
    } });
    await renderPage();
    expect(within(screen.getByTestId('bots-symbol-GRML')).getByText('Held')).toBeTruthy();
    const open = within(screen.getByTestId('bots-symbol-IMCC')).getByText(/Open L2/);
    fireEvent.click(open);
    expect(openStockView).toHaveBeenCalledWith('IMCC');
    await act(async () => {
      fireEvent.change(screen.getByTestId('bots-symbol-input'), { target: { value: 'efgh' } });
      fireEvent.click(screen.getByTestId('bots-symbol-add'));
      await flush();
    });
    expect(ops).toContainEqual({ symbol: 'efgh', op: 'add' });
    await act(async () => { fireEvent.click(screen.getByTestId('bots-symbol-remove-IMCC')); await flush(); });
    expect(ops).toContainEqual({ symbol: 'IMCC', op: 'remove' });
  });

  it('shows the locked breakers', async () => {
    mockBotFetch();
    await renderPage();
    const breakers = screen.getByTestId('bot-strategy-breakers').textContent ?? '';
    expect(breakers).toMatch(/locked/);
    expect(breakers).toMatch(/−\$200 all-stop/);
    expect(breakers).toMatch(/−\$50 bot trip/);
  });

  it('keeps bot proposals in the inbox; Mark accepted never places', async () => {
    const fetchMock = mockBotFetch({ proposals: [{
      id: 'p1', symbol: 'GRML', side: 'BUY', kind: 'buy_limit_ask_offset', shortcut: 'buy_limit_ask_offset',
      preset_qty: 1, reason: 'first pullback near 8.72, tape go', confidence: null, status: 'pending',
    }] });
    await renderPage();
    const card = within(screen.getByTestId('bots-bot-proposal-p1'));
    expect(card.getByText(/tape go/)).toBeTruthy();
    await act(async () => { fireEvent.click(card.getByText('Mark accepted')); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/proposals/p1/accept'))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/bot/action'))).toBe(false);
  });

  it('draws the activity timeline and filters it', async () => {
    mockBotFetch({ audit: [
      { timestamp: 1_790_000_000, level: 1, strategy: null, brain_session_id: null, action: 'level',
        inputs: { from: 1, to: 2 }, reason: 'Strategy lands not active until the read-out passes', order_id: null,
        advise_spend: null, outcome: '1->2' },
      { timestamp: 1_790_000_100, level: 2, strategy: null, brain_session_id: null, action: 'setup_proposal',
        inputs: { symbol: 'GRML', kind: 'first_pullback' }, reason: null, order_id: null, advise_spend: null,
        outcome: 'proposed' },
    ] });
    await renderPage();
    const activity = within(screen.getByTestId('bots-activity'));
    expect(activity.getByText('Eyes → Strategy')).toBeTruthy();
    expect(activity.getByText('GRML first pullback')).toBeTruthy();
    await act(async () => { fireEvent.click(activity.getByText('Proposals')); });
    expect(activity.queryByText('Eyes → Strategy')).toBeNull();
    expect(activity.getByText('GRML first pullback')).toBeTruthy();
  });
});
