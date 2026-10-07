/**
 * @vitest-environment jsdom
 *
 * Holding a short (ADR 048, #778 step 3), against a fake backend: the "This trade" card, mirrored -- Shorted at,
 * Buy stop, Next, At the stop and Cover 2R, the ladder running downward, "Lower stop to X", Stage cover (a buy at
 * the ask) and "Nova takes the cover" (a buy stop that only moves down) -- the buy stop resting at the broker as
 * the card's stop, and Who trades saying the bot enters nothing while you hold it short.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { subscribeOrderTicketPrefill } from '../ibkr/orderTicketPrefill';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import { rdynShortWire } from './heldFixtures';
import { StockReadProvider } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';
import { sleeveSessionWire } from './whoTradesFixtures';
import { HELD_LIVE_COVER_WHY } from './whoTradesModel';
import { WhoTradesRow } from './WhoTradesRow';

type Json = Record<string, unknown>;
let calls: { url: string; method: string; body: Json | null }[] = [];
let view: Json;
let clock = 1_791_383_000;

function modeWire(over: Json = {}): Json {
  clock += 1;
  return {
    schema_version: 1, symbol: 'RDYN', generated_at: clock, venue: 'paper', mode: 'signal', buy: 'you', sell: 'you',
    entry: 'you', exit: 'you', risk_usd: null, set_at: null, locks: { buy: null, sell: null }, notes: [],
    approval: null, trade: null, nova_entries_today: 0, last_event: null, bot: null, ...over,
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
    if (/\/api\/stock-read\/RDYN(\?|$)/.test(url)) {
      return answer({ ...apusReadWire, symbol: 'RDYN', price: 5.46, plan: null,
        held: /held_qty=/.test(url) ? rdynShortWire : null });
    }
    if (/\/api\/bot\/session$/.test(url)) return answer(sleeveSessionWire(20));
    if (/\/api\/stock-mode\/RDYN\/take-exit$/.test(url)) {
      view = modeWire({ sell: 'nova', exit: 'nova', trade: { kind: 'exit', side: 'short', state: 'holding',
        exits: 'nova', venue: 'paper', qty: 416, entry: 5.77, fill_price: 5.77, stop: body?.stop, target: null,
        trail: body?.trail, raised: [], stop_order_id: 51, target_order_id: null, entry_order_id: null,
        filled_at: clock, sent_at: clock } });
      return answer(view);
    }
    if (/\/api\/stock-mode\/RDYN$/.test(url)) return answer(view);
    return answer({}, 404);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderTab(venue = 'paper', workingStop: number | null = null) {
  return render(
    <StockReadProvider symbol="RDYN" active replay={false} venue={venue}
      position={{ qty: -416, avgCost: 5.77, workingStop }}
      topOfBook={{ symbol: 'RDYN', bid: 5.45, ask: 5.47 }}>
      <StockReadRail />
      <WhoTradesRow />
    </StockReadProvider>,
  );
}

const reads = () => calls.filter(c => /\/api\/stock-read\/RDYN\?/.test(c.url)).map(c => c.url);

describe('the This trade card while you hold RDYN short', () => {
  it('is the card mirrored: SHORT, Shorted at, Buy stop, Cover 2R, and the ladder running downward', async () => {
    renderTab();
    const card = await screen.findByTestId('held-card');
    expect(within(card).getByTestId('held-short-tag').textContent).toBe('SHORT');
    expect(within(card).getByTestId('held-badge').textContent).toBe('BROKE $5.50');
    expect([...card.querySelectorAll('.sr-num__k')].map(k => k.textContent))
      .toEqual(['Shorted at', 'Buy stop', 'Next', 'At the stop', 'Cover 2R']);
    // At the stop: the short loses (5.89 - 5.77) x 416.
    expect(card.querySelector('.sr-num--risk .sr-num__v')?.textContent).toBe('-$49.92');
    const ladder = within(card).getByTestId('held-ladder');
    expect(within(ladder).getAllByRole('listitem').map(li => li.querySelector('.sr-ladder__c')?.textContent))
      .toEqual(['STOP', 'COST', 'BROKE', 'NOW', 'NEXT', 'THEN']);
    expect(within(card).getByTestId('held-note').textContent).toBe('your buy stop and cover: no order is working');
    // The read is asked about the short.
    expect(reads().some(u => /held_qty=416&held_avg=5.77/.test(u) && /held_side=short/.test(u))).toBe(true);
  });

  it('Lower stop sets your buy stop for the trade and asks the read again with it -- never an order', async () => {
    renderTab();
    fireEvent.click(await screen.findByTestId('held-lower'));
    await waitFor(() => expect(reads().some(u => /held_stop=5.55/.test(u))).toBe(true));
    expect(screen.queryByTestId('held-raise')).toBeNull();
    expect(calls.filter(c => c.method !== 'GET')).toEqual([]);
  });

  it('Stage cover fills the ticket with a buy at the ask, and never sends', async () => {
    renderTab();
    const heard = vi.fn();
    let off: () => void = () => undefined;
    act(() => {
      off = subscribeOrderTicketPrefill('RDYN', heard);
    });
    const stage = await screen.findByTestId('held-stage-cover');
    await waitFor(() => expect((stage as HTMLButtonElement).disabled).toBe(false));
    expect(stage.textContent).toBe('Stage cover 416');
    fireEvent.click(stage);
    expect(heard).toHaveBeenCalledWith(expect.objectContaining({
      symbol: 'RDYN', side: 'BUY', orderType: 'LMT', quantityValue: '416', limitPrice: '5.47',
    }));
    expect(calls.filter(c => c.method !== 'GET')).toEqual([]);
    off();
  });

  it('hands Nova the cover from the sheet: a buy stop, lowered as levels break', async () => {
    renderTab();
    const btn = await screen.findByTestId('held-nova-exit');
    expect(btn.textContent).toBe('Nova takes the cover ›');
    fireEvent.click(btn);
    const sheet = await screen.findByTestId('exit-sheet');
    expect(sheet.querySelector('.sr-exit__title')?.textContent).toBe('Nova takes the cover on 416 RDYN short');
    expect(within(sheet).getByTestId('exit-target').getAttribute('data-why')).toMatch(/#681/);
    expect(within(sheet).queryByTestId('exit-flush')).toBeNull();
    expect(within(sheet).getByTestId('exit-sends').textContent)
      .toMatch(/BUY 416 RDYN STP 5.55, replaced at each broken level/);
    fireEvent.click(within(sheet).getByTestId('exit-send'));
    await waitFor(() => expect(calls.find(c => c.method === 'POST')).toMatchObject({
      body: { stop: 5.55, trail: true },
    }));
    expect(calls.find(c => c.method === 'POST')?.url).toMatch(/\/api\/stock-mode\/RDYN\/take-exit$/);
    await waitFor(() => expect(screen.getByTestId('held-nova-status').textContent)
      .toBe('Nova holds the cover · buy stop 5.55 · lowered as levels break'));
  });

  it('judges the trade by the buy stop resting at the broker until you set one', async () => {
    renderTab('paper', 5.89);
    const card = await screen.findByTestId('held-card');
    await waitFor(() => expect(reads().some(u => /held_stop=5.89/.test(u))).toBe(true));
    await waitFor(() => expect(within(card).getByTestId('held-note').textContent)
      .toBe('your buy stop 5.89 is working at the broker'));
    expect(card.querySelector('.sr-num--stop .sr-num__s')?.textContent).toBe('resting at the broker');
  });

  it('says the bot enters nothing on RDYN while you hold it short', async () => {
    renderTab();
    await waitFor(() => expect(screen.getByTestId('who-trades-answer').textContent)
      .toBe('You hold RDYN short: the bot enters nothing on RDYN while you do'));
  });

  it('on Live, Nova takes no cover and says why', async () => {
    view = modeWire({ venue: 'live', locks: { buy: 'On Live, Nova never buys by itself.', sell: '#604' } });
    renderTab('live');
    const btn = await screen.findByTestId('held-nova-exit');
    await waitFor(() => expect(btn.getAttribute('data-why')).toBe(HELD_LIVE_COVER_WHY));
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });
});
