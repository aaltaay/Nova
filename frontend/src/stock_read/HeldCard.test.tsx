/**
 * @vitest-environment jsdom
 *
 * The plan box while you hold the stock (ADR 036 / 037 amendment 2026-10-01), against a fake backend:
 * the box keeps its look and becomes the trade's, Raise stop asks the read again with your stop, the Sell
 * switch and "Nova takes the exit" open the sheet, the sheet hands Nova the stop, and Live is locked.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { orderSentBy } from '../ibkr/orderSentBy';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import { apusHeldWire } from './heldFixtures';
import { StockReadProvider } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';
import { sleeveSessionWire } from './whoTradesFixtures';
import { WhoTradesRow } from './WhoTradesRow';

type Json = Record<string, unknown>;
let calls: { url: string; method: string; body: Json | null }[] = [];
let view: Json;
let clock = 1_790_000_000;

function modeWire(over: Json = {}): Json {
  clock += 1;
  return {
    schema_version: 1, symbol: 'APUS', generated_at: clock, venue: 'paper', mode: 'signal', buy: 'you', sell: 'you',
    risk_usd: null, set_at: null, locks: { buy: null, sell: null }, notes: [], approval: null, trade: null,
    nova_entries_today: 0, last_event: null, bot: null, ...over,
  };
}

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  _resetSleeveForTests();
  calls = [];
  view = modeWire();
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Json) : null;
    calls.push({ url, method, body });
    if (/\/api\/stock-read\/APUS\/flush$/.test(url)) return answer({ schema_version: 1, symbol: 'APUS', at: 1, score: 0.1, label: 'neutral', window_sec: 30 });
    if (/\/api\/stock-read\/APUS(\?|$)/.test(url)) {
      return answer({ ...apusReadWire, price: 6.64, held: /held_qty=/.test(url) ? apusHeldWire : null });
    }
    if (/\/api\/bot\/session$/.test(url)) return answer(sleeveSessionWire(20));
    if (/\/api\/stock-mode\/APUS\/take-exit$/.test(url)) {
      view = modeWire({ sell: 'nova', trade: { kind: 'exit', state: 'holding', exits: 'nova', venue: 'paper', qty: 100,
        entry: 5.075, fill_price: 5.075, stop: body?.stop, target: null, trail: body?.trail, raised: [],
        stop_order_id: 41, target_order_id: null, entry_order_id: null, filled_at: clock, sent_at: clock } });
      return answer(view);
    }
    if (/\/api\/stock-mode\/APUS$/.test(url)) return answer(view);
    return answer({}, 404);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderTab(venue = 'paper') {
  return render(
    <StockReadProvider symbol="APUS" active replay={false} venue={venue} position={{ qty: 100, avgCost: 5.075 }}
      lastPrice={6.64} topOfBook={{ symbol: 'APUS', bid: 6.61, ask: 6.64, depthSubscribed: true } as never}>
      <StockReadRail />
      <WhoTradesRow />
    </StockReadProvider>,
  );
}

const reads = () => calls.filter(c => /\/api\/stock-read\/APUS\?/.test(c.url)).map(c => c.url);

describe('the plan box while you hold APUS', () => {
  it('is the box you know, about your trade: numbers, ruler, the ladder, the rows and the checks', async () => {
    renderTab();
    const card = await screen.findByTestId('held-card');
    expect(card.className).toContain('sr-plan');
    expect(within(card).getByTestId('held-badge').textContent).toBe('BROKE $6.00');
    expect(card.querySelector('.sr-plan__nums')).not.toBeNull();
    expect(within(card).getByTestId('held-ruler')).toBeTruthy();
    const ladder = within(card).getByTestId('held-ladder');
    expect(within(ladder).getAllByRole('listitem').map(li => li.querySelector('.sr-ladder__c')?.textContent))
      .toEqual(['THEN', 'NEXT', 'NOW', 'THROUGH', 'BROKE', 'BROKE', 'STOP', 'COST']);
    expect(card.querySelector('.sr-levels')?.textContent).toContain('0.7R to HOD 6.97, from the price');
    expect(card.querySelector('.sr-checks')?.textContent).toContain('1-min MACD histogram +0.062');
    // The read is asked about the position.
    expect(reads().some(u => /held_qty=100&held_avg=5.075/.test(u))).toBe(true);
  });

  it('Raise stop sets your stop for the trade and asks the read again with it -- never an order', async () => {
    renderTab();
    fireEvent.click(await screen.findByTestId('held-raise'));
    await waitFor(() => expect(reads().some(u => /held_stop=5.95/.test(u))).toBe(true));
    expect(calls.filter(c => c.method !== 'GET')).toEqual([]);
  });

  it('hands Nova the exit from the sheet: a stop, raised as levels break', async () => {
    renderTab();
    fireEvent.click(await screen.findByTestId('held-nova-exit'));
    const sheet = await screen.findByTestId('exit-sheet');
    expect(within(sheet).getByTestId('exit-target').getAttribute('data-why')).toMatch(/#681/);
    expect(within(sheet).getByTestId('exit-flush').getAttribute('data-why')).toMatch(/trial T1/);
    expect(within(sheet).getByTestId('exit-sends').textContent).toMatch(/SELL 100 APUS STP 5.95, replaced at each broken level/);
    fireEvent.click(within(sheet).getByTestId('exit-send'));
    await waitFor(() => expect(calls.find(c => c.method === 'POST')).toMatchObject({
      body: { stop: 5.95, trail: true },
    }));
    expect(calls.find(c => c.method === 'POST')?.url).toMatch(/\/api\/stock-mode\/APUS\/take-exit$/);
    await waitFor(() => expect(screen.queryByTestId('exit-sheet')).toBeNull());
  });

  it('Sell: Nova on the switch opens the sheet instead of a refused switch', async () => {
    renderTab();
    await screen.findByTestId('held-card');
    await waitFor(() => expect(screen.getByTestId('who-trades-mode').textContent).toContain('Signal only'));
    fireEvent.click(screen.getByTestId('who-trades-sell-nova'));
    expect(await screen.findByTestId('exit-sheet')).toBeTruthy();
    expect(calls.filter(c => c.method === 'PUT')).toEqual([]);
  });

  it('on Live, Nova takes no exit and says why', async () => {
    view = modeWire({ venue: 'live', locks: { buy: 'On Live, Nova never buys by itself.', sell: '#604' } });
    renderTab('live');
    const btn = await screen.findByTestId('held-nova-exit');
    await waitFor(() => expect(btn.getAttribute('data-why')).toMatch(/never moves a Live order by itself/));
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('names the sender of Nova exit orders', () => {
    expect(orderSentBy({ order_source: 'manual', order_origin: 'nova_exit' } as never).label).toBe('Nova exit');
  });
});
