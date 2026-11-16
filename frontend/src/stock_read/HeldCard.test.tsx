/**
 * @vitest-environment jsdom
 *
 * The plan box while you hold the stock (ADR 036 / 037 amendment 2026-10-01), against a fake backend:
 * the box keeps its look and becomes the trade's, Raise stop asks the read again with your stop, and the sell is
 * yours alone -- Nova takes no exit (ADR 072).
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { resetTickerStreamsForTests } from '../hooks/tickerStore';
import { orderSentBy } from '../ibkr/orderSentBy';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import { apusHeldWire } from './heldFixtures';
import { StockReadProvider } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';
import { sleeveSessionWire } from './momentFixtures';

type Json = Record<string, unknown>;
let calls: { url: string; method: string; body: Json | null }[] = [];
let heldWire: Json = apusHeldWire;

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  _resetSleeveForTests();
  calls = [];
  heldWire = apusHeldWire;
  vi.stubGlobal('fetch', vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Json) : null;
    calls.push({ url, method, body });
    if (/\/api\/stock-read\/APUS\/flush$/.test(url)) return answer({ schema_version: 1, symbol: 'APUS', at: 1, score: 0.1, label: 'neutral', window_sec: 30 });
    if (/\/api\/stock-read\/APUS(\?|$)/.test(url)) {
      return answer({ ...apusReadWire, price: 6.64, held: /held_qty=/.test(url) ? heldWire : null });
    }
    if (/\/api\/bot\/session$/.test(url)) return answer(sleeveSessionWire(20));
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
    // The target menu's two targets off your average (#845), each with its share and rule -- never "Target 2R".
    expect([...card.querySelectorAll('.sr-num__k')].map(k => k.textContent))
      .toEqual(['Average', 'Stop', 'Next', 'At the stop', 'Target 1 · 50%', 'Target 2 · 50%']);
    expect(within(card).getByTestId('held-target').textContent).toBe('5.28');
    expect(within(card).getByTestId('held-target2').textContent).toBe('6.96');
    expect(card.querySelector('.sr-plan__nums')?.textContent).toContain('traded: you are past it');
    expect(card.querySelector('.sr-plan__nums')?.textContent).toContain('1c under HOD 6.97');
    // The level rows say each target once, under its own name.
    expect(within(card).getByTestId('stock-read-level-target').textContent).toBe('Target 1' + '5.28 traded at 08:56: you are past it');
    expect(within(card).getByTestId('stock-read-level-target2').textContent).toBe('Target 2' + '6.96 is 32c above');
    expect(card.textContent).not.toMatch(/(?<![\d.])2R\b/);
    expect(card.querySelector('.sr-checks')?.textContent).toContain('1-min MACD histogram +0.062');
    // The read is asked about the position.
    expect(reads().some(u => /held_qty=100&held_avg=5.075/.test(u))).toBe(true);
  });

  // Operator report 2026-10-13: the ruler's price tick moved once a read, every 5 s -- "way too delayed".
  it('follows the tape between reads: the price tick, the open P&L and the NOW row', async () => {
    const sockets: { url: string; onmessage: ((ev: { data: string }) => void) | null }[] = [];
    vi.stubGlobal('WebSocket', class {
      url: string;
      readyState = 0;
      onopen = null;
      onclose = null;
      onerror = null;
      onmessage: ((ev: { data: string }) => void) | null = null;
      constructor(url: string) {
        this.url = url;
        sockets.push(this);
      }
      close() {}
      send() {}
    });
    resetTickerStreamsForTests();
    renderTab();
    const card = await screen.findByTestId('held-card');
    const tick = () => card.querySelector<HTMLElement>('.sr-ruler__track')?.style.transform;
    const atRead = tick();
    const asked = reads().length;
    const tape = sockets.find(s => /\/ticker\/APUS$/.test(s.url))!;
    act(() => {
      tape.onmessage?.({ data: JSON.stringify({ type: 'initial', symbol: 'APUS', snapshot: { latest_trade: { price: 6.64 } } }) });
      tape.onmessage?.({ data: JSON.stringify({ type: 'trade_update', symbol: 'APUS', price: 6.8 }) });
    });
    await waitFor(() => expect(card.querySelector('.sr-plan__rr b')?.textContent).toBe('+$172.50'));
    expect(card.querySelector('.sr-plan__rr-k')?.textContent).toBe(' +3.9R open');
    expect(tick()).not.toBe(atRead);
    const now = card.querySelector('.sr-ladder__row--now')!;
    expect(now.textContent).toContain('+172.50 open');
    expect(now.querySelector('.sr-ladder__r')?.textContent).toBe('+$172.50 · +3.9R');
    expect(reads()).toHaveLength(asked);
    resetTickerStreamsForTests();
  });

  it('Raise stop sets your stop for the trade and asks the read again with it -- never an order', async () => {
    renderTab();
    fireEvent.click(await screen.findByTestId('held-raise'));
    await waitFor(() => expect(reads().some(u => /held_stop=5.95/.test(u))).toBe(true));
    expect(calls.filter(c => c.method !== 'GET')).toEqual([]);
  });

  it('the sell is yours alone: Stage sell, and no "Nova takes the exit" (ADR 072)', async () => {
    renderTab();
    const card = await screen.findByTestId('held-card');
    expect(within(card).getByTestId('held-stage-sell').textContent).toBe('Stage sell 100');
    expect(within(card).queryByTestId('held-nova-exit')).toBeNull();
    expect(screen.queryByTestId('exit-sheet')).toBeNull();
    expect(within(card).getByTestId('held-note').textContent).toBe('your stop and targets: no order is working');
    expect(calls.some(c => c.url.includes('/api/stock-mode'))).toBe(false);
  });

  it('names the sender of Nova exit orders', () => {
    expect(orderSentBy({ order_source: 'manual', order_origin: 'nova_exit' } as never).label).toBe('Nova exit');
  });
});
