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
import { ChartLegend } from './ChartLegend';
import { STOCK_MODE_SOUND_KEY } from './constants';
import { StockReadProvider, useStockReadContext } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';
import type { StockModeName } from './types';
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
    if (/\/api\/stock-mode\/APUS$/.test(url)) {
      if (!modeFound) return answer({ detail: 'Not Found' }, 404);
      if (method === 'PUT') {
        if (refuse) return answer(refuse.body, refuse.status);
        view = modeWire(modeFor(String(body?.buy), String(body?.sell)));
      }
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
  it('starts at Signal only and hands the buy to Nova with the risk per trade and the desk key', async () => {
    renderTab();
    const row = await screen.findByTestId('who-trades');
    expect(row.querySelector('.sr-who__kicker')?.textContent).toBe('Who trades APUS');
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only'));
    expect(screen.getByTestId('who-trades-buy-you').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('who-trades-buy-nova'));
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Auto-entry'));
    expect(writes()).toEqual([expect.objectContaining({
      method: 'PUT', body: { buy: 'nova', sell: 'you', risk_usd: 20 }, key: 'desk-key',
    })]);
    expect(screen.getByTestId('stock-read-action-auto-off').textContent).toBe('Auto-entry on · turn off');
    expect(screen.getByTestId('stock-read-plan-note').textContent).toBe('Nova buys APUS once, at the trigger. Every sell is yours.');
  });

  it('locks Nova on Live, and each lock says why', async () => {
    view = modeWire('signal', { venue: 'live', locks: {
      buy: 'On Live, Nova never buys by itself.', sell: 'Approve on Live waits on #604.' } });
    renderTab();
    await waitFor(() => expect(screen.getByTestId('who-trades-buy-nova').hasAttribute('disabled')).toBe(true));
    const buyNova = screen.getByTestId('who-trades-buy-nova');
    expect(buyNova.getAttribute('data-why')).toMatch(/never buys by itself/);
    expect(buyNova.textContent).toBe('🔒 Nova');
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
      'Signal only ✓you buy · you sell',
      'Approveyou approve · Nova sells',
      'Auto-entryNova buys · you sell',
      'Bot at StrategyNova buys · Nova sells',
    ]);
    fireEvent.click(screen.getByTestId('who-trades-menu-approve'));
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Approve'));
    expect(writes()[0].body).toEqual({ buy: 'you', sell: 'nova', risk_usd: 20 });
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
