/**
 * @vitest-environment jsdom
 *
 * Who trades the stock on the Trader tab (ADR 037): the row above Level 2, the chip on the chart and its
 * four choices, the plan card's buttons per mode, the plan in the Level 2 book and the ping's mute --
 * against a fake backend that answers the stock read and the stock's view.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import { ChartLegend } from './ChartLegend';
import { STOCK_MODE_SOUND_KEY } from './constants';
import { StockReadProvider, useStockReadContext } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';
import type { StockModeName } from './types';
import { sleeveSessionWire } from './whoTradesFixtures';
import { useLevel2Markers, WhoTradesRow } from './WhoTradesRow';
import { resetStockReadSoundForTests } from './whoTradesSound';

type Json = Record<string, unknown>;
interface Call {
  url: string;
  method: string;
  body: Json | null;
  key: string | null;
}

let calls: Call[] = [];
let view: Json;
let clock = 1_790_000_000;
let refuse: { status: number; body: Json } | null = null;
let modeFound = true;

const SIDES: Record<StockModeName, [string, string]> = {
  signal: ['you', 'you'],
  approve: ['you', 'nova'],
  auto_entry: ['nova', 'you'],
  bot: ['nova', 'nova'],
};

function modeWire(mode: StockModeName, over: Json = {}): Json {
  clock += 1;
  const [buy, sell] = SIDES[mode];
  return {
    schema_version: 1, symbol: 'APUS', generated_at: clock, venue: 'paper', mode, buy, sell,
    risk_usd: mode === 'auto_entry' ? 20 : null, set_at: null, locks: { buy: null, sell: null }, notes: [],
    approval: null, trade: null, nova_entries_today: 0, last_event: null, bot: null, ...over,
  };
}

function modeFor(buy: string, sell: string): StockModeName {
  if (buy === 'nova') return sell === 'nova' ? 'bot' : 'auto_entry';
  return sell === 'nova' ? 'approve' : 'signal';
}

function answer(body: Json, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  resetStockReadSoundForTests();
  _resetSleeveForTests();
  calls = [];
  refuse = null;
  modeFound = true;
  view = modeWire('signal');
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Json) : null;
    calls.push({ url, method, body, key: new Headers(init?.headers).get(NOVA_API_KEY_HEADER) });
    if (/\/api\/stock-read\/APUS(\?|$)/.test(url)) return answer(apusReadWire);
    if (/\/api\/bot\/session$/.test(url)) return answer(sleeveSessionWire(20));
    if (/\/api\/stock-mode\/APUS(\/take-over)?$/.test(url)) {
      if (!modeFound) return answer({ detail: 'Not Found' }, 404);
      if (method === 'PUT') {
        if (refuse) return answer(refuse.body, refuse.status);
        view = modeWire(modeFor(String(body?.buy), String(body?.sell)));
      }
      if (method === 'POST') view = modeWire('signal', { last_event: { ts: clock, tone: 'info',
        text: 'You took over the exit: Nova no longer sells it' } });
      return answer(view);
    }
    return answer({}, 404);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Legend() {
  const ctx = useStockReadContext();
  return ctx?.read.data ? <ChartLegend ctx={ctx} read={ctx.read.data} onFrame={() => undefined} /> : null;
}

function Markers() {
  const markers = useLevel2Markers();
  return (
    <div data-testid="markers">
      {(markers ?? []).map(m => `${m.label}:${m.working ? 'solid' : 'dashed'}`).join('|')}
    </div>
  );
}

function renderTab(opts: { replay?: boolean } = {}) {
  return render(
    <StockReadProvider symbol="APUS" active replay={opts.replay ?? false}
      topOfBook={{ symbol: 'APUS', bid: 5.36, ask: 5.39, depthSubscribed: true } as never}>
      <StockReadRail />
      <WhoTradesRow />
      <Legend />
      <Markers />
    </StockReadProvider>,
  );
}

const writes = () => calls.filter(c => c.method !== 'GET');

describe('who trades APUS, above Level 2', () => {
  it('starts at Signal only and hands the buy to Nova with the desk key, sending no risk per trade', async () => {
    renderTab();
    const row = await screen.findByTestId('who-trades');
    expect(row.querySelector('.sr-who__kicker')?.textContent).toBe('Who trades APUS');
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only'));
    expect(screen.getByTestId('who-trades-buy-you').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('who-trades-buy-nova'));
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Auto-entry'));
    // Nova sizes by the venue's sleeve: the switch carries no risk per trade (the backend ignores one).
    expect(writes()).toEqual([expect.objectContaining({
      method: 'PUT', body: { buy: 'nova', sell: 'you' }, key: 'desk-key',
    })]);
    expect(screen.getByTestId('stock-read-action-auto-off').textContent).toBe('Auto-entry on · turn off');
    expect(screen.getByTestId('stock-read-plan-note').textContent).toBe('The bot enters APUS at a go trigger of a '
      + "strategy at On, by the bot's rules, while the bot is on: the strategy decides long or short. Every exit is yours.");
  });

  it('shows every note, toned, the day\'s shared count and the last event -- none hidden behind the first', async () => {
    view = modeWire('bot', {
      notes: [
        { id: 'not_active', tone: 'warn', text: 'The bot is not active: press Activate on the Bots page.' },
        { id: 'window', tone: 'warn', text: "The bull flag's bot window is closed (07:00-10:00 ET)." },
        { id: 'sim_waits', tone: 'info', text: 'A Sim trade waits while the desk shows another venue.' },
      ],
      entries_today: { count: 1, cap: 1 },
      last_event: { ts: 1_790_000_100, tone: 'warn', text: 'The bot skipped APUS: the bot is not active' },
      bot: { on_list: true, playing: false, reason: 'the bot is not active', setup_at_strategy: true, active: false },
    });
    renderTab();
    const notes = await screen.findByTestId('who-trades-notes');
    expect(within(notes).getAllByRole('listitem').map(li => li.className)).toEqual([
      'sr-who__note sr-who__note--warn', 'sr-who__note sr-who__note--warn', 'sr-who__note sr-who__note--info',
    ]);
    expect(screen.getByTestId('who-trades-note-window').getAttribute('data-tip')).toMatch(/bot window is closed/);
    expect(screen.getByTestId('who-trades-mode').textContent).toContain('Bot');
    const entries = screen.getByTestId('who-trades-entries');
    expect(entries.textContent).toBe("Nova's automatic trades today: 1 of 1");
    expect(entries.className).toContain('--warn');
    expect(screen.getByTestId('who-trades-event').textContent).toMatch(/The bot skipped APUS: the bot is not active$/);
  });

  it('says on the plan the size Nova sends in a Nova mode, beside your own', async () => {
    view = modeWire('auto_entry', { size: { qty: 10, by_risk: 181, capped_by: 'max_shares',
      text: '$20 risk over 0.11 a share is 181 shares; the Paper sleeve caps a buy at 10' } });
    renderTab();
    const line = await screen.findByTestId('stock-read-nova-size');
    expect(line.textContent).toBe("Nova sends 10 (181 by risk, capped by the sleeve's max shares)");
    expect(line.getAttribute('data-tip')).toMatch(/caps a buy at 10/);
    expect(screen.getByTestId('stock-read-size').textContent).toBe('181 sh');      // your own Stage: no sleeve caps
  });

  it('takes over with the symbol alone: Entry stays on You, never Auto-entry', async () => {
    view = modeWire('bot', { trade: { kind: 'bot', state: 'holding', qty: 10, entry: 5.44, stop: 5.33, target: 5.66,
      fill_price: 5.44, filled_at: clock, exits: 'nova', entry_order_id: 7, target_order_id: 8, stop_order_id: 9 },
      bot: { on_list: true, playing: true, reason: null, setup_at_strategy: true, active: true } });
    renderTab();
    const take = await screen.findByTestId('stock-read-action-take-over');
    expect(take.getAttribute('data-tip')).toMatch(/Entry stays on You: the bot enters nothing more on APUS/);
    fireEvent.click(take);
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only'));
    const post = writes().find(c => c.url.endsWith('/take-over'));
    expect(post).toMatchObject({ method: 'POST', body: null, key: 'desk-key' });
  });

  it('locks Nova on Live, and each lock says why', async () => {
    view = modeWire('signal', { venue: 'live', locks: {
      buy: 'On Live, Nova never buys by itself.', sell: 'Approve on Live waits on #604.' } });
    renderTab();
    // The button is disabled while the view loads too ("Reading who trades APUS…"): wait for the lock's own reason.
    await waitFor(() => expect(screen.getByTestId('who-trades-buy-nova').getAttribute('data-why')).toMatch(/never buys by itself/));
    const buyNova = screen.getByTestId('who-trades-buy-nova');
    expect(buyNova.hasAttribute('disabled')).toBe(true);
    expect(buyNova.textContent).toBe('🔒 Bot');
    expect(screen.getByTestId('who-trades-sell-nova').getAttribute('data-why')).toMatch(/#604/);
    expect(screen.getByTestId('who-trades-buy-you').hasAttribute('disabled')).toBe(false);
  });

  it("says a refusal in the backend's own words", async () => {
    refuse = { status: 409, body: { detail: { reason: 'STOCK_MODE_HELD', error: 'You hold APUS: Nova exits only a trade it entered' } } };
    renderTab();
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only'));
    fireEvent.click(screen.getByTestId('who-trades-sell-nova'));
    await waitFor(() => expect(screen.getByTestId('who-trades-note').textContent).toMatch(/You hold APUS/));
    expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only');
  });

  it('an older backend cannot say who trades, and the row says so', async () => {
    modeFound = false;
    renderTab();
    await waitFor(() => expect(screen.getByTestId('who-trades-note').textContent).toMatch(/older than the desk/));
    expect(screen.getByTestId('who-trades-buy-nova').getAttribute('data-why')).toMatch(/Reload the backend/);
  });

  it('reads nothing and shows nothing on a replay desk', () => {
    renderTab({ replay: true });
    expect(screen.queryByTestId('who-trades')).toBeNull();
    expect(calls.filter(c => c.url.includes('/api/stock-mode'))).toEqual([]);
  });
});

describe('on the 1-minute chart', () => {
  it('the chip opens the four choices, and Approve is one click', async () => {
    renderTab();
    const chip = await screen.findByTestId('who-trades-chip');
    await waitFor(() => expect(chip.textContent).toContain('Signal only'));
    fireEvent.click(chip);
    const menu = screen.getByTestId('who-trades-menu');
    expect(within(menu).getAllByRole('menuitemradio').map(b => b.textContent)).toEqual([
      'Signal only ✓you enter · you exit',
      'Approveyou approve · bot exits',
      'Auto-entrybot enters · you exit',
      'Botbot enters · bot exits',
    ]);
    fireEvent.click(screen.getByTestId('who-trades-menu-approve'));
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Approve'));
    expect(writes()[0].body).toEqual({ buy: 'you', sell: 'nova' });
    expect(screen.queryByTestId('who-trades-menu')).toBeNull();
    // APUS's flag is still forming: nothing is armed to approve, and the button says so.
    const approve = screen.getByTestId('stock-read-action-approve');
    expect(approve.hasAttribute('disabled')).toBe(true);
    expect(approve.getAttribute('data-why')).toMatch(/has not armed/);
  });

  it('carries the track under the badge, and the bell mutes the ping on every tab', async () => {
    renderTab();
    const track = await screen.findByTestId('moment-track');
    expect(within(track).getByText('Forming').getAttribute('data-state')).toBe('now');
    expect(screen.getByTestId('stock-read-badge').textContent).toBe('BULL FLAG · FORMING 1 OF 2');
    fireEvent.click(screen.getByTestId('moment-bell'));
    expect(screen.getByTestId('moment-bell').getAttribute('aria-pressed')).toBe('false');
    expect(JSON.parse(localStorage.getItem(STOCK_MODE_SOUND_KEY) ?? '{}')).toEqual({ schema_version: 1, value: false });
  });
});

describe('the plan in Level 2', () => {
  it('draws ENTRY, STOP and TARGET dashed while they are only a plan', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByTestId('markers').textContent)
      .toBe('ENTRY 5.44:dashed|STOP 5.33:dashed|TARGET 5.66:dashed'));
  });
});
