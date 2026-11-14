/**
 * @vitest-environment jsdom
 *
 * Holding a short (ADR 048, #778 step 3), against a fake backend: the "This trade" card, mirrored -- Shorted at,
 * Buy stop, Next, At the stop, Cover 1 and Cover 2, the ladder running downward, "Lower stop to X" and Stage cover (a
 * buy at the ask) -- and the buy stop resting at the broker as the card's stop. The cover is yours alone (ADR 072).
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
import { sleeveSessionWire } from './momentFixtures';

type Json = Record<string, unknown>;
let calls: { url: string; method: string; body: Json | null }[] = [];

const answer = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  _resetSleeveForTests();
  calls = [];
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
    </StockReadProvider>,
  );
}

const reads = () => calls.filter(c => /\/api\/stock-read\/RDYN\?/.test(c.url)).map(c => c.url);

describe('the This trade card while you hold RDYN short', () => {
  it('is the card mirrored: SHORT, Shorted at, Buy stop, Cover 1 and Cover 2, and the ladder running downward', async () => {
    renderTab();
    const card = await screen.findByTestId('held-card');
    expect(within(card).getByTestId('held-short-tag').textContent).toBe('SHORT');
    expect(within(card).getByTestId('held-badge').textContent).toBe('BROKE $5.50');
    // The menu's two covers under the average (#845), half at each -- no cover is a multiple of the risk.
    expect([...card.querySelectorAll('.sr-num__k')].map(k => k.textContent))
      .toEqual(['Shorted at', 'Buy stop', 'Next', 'At the stop', 'Cover 1 · 50%', 'Cover 2 · 50%']);
    expect(within(card).getByTestId('held-target').textContent).toBe('5.57');
    expect(within(card).getByTestId('held-target2').textContent).toBe('5.42');
    expect(card.textContent).toContain('1c over LOD 5.41');
    expect(card.textContent).not.toMatch(/(?<![\d.])2R\b/);
    // At the stop: the short loses (5.89 - 5.77) x 416.
    expect(card.querySelector('.sr-num--risk .sr-num__v')?.textContent).toBe('-$49.92');
    const ladder = within(card).getByTestId('held-ladder');
    expect(within(ladder).getAllByRole('listitem').map(li => li.querySelector('.sr-ladder__c')?.textContent))
      .toEqual(['STOP', 'COST', 'BROKE', 'NOW', 'NEXT', 'THEN']);
    expect(within(card).getByTestId('held-note').textContent).toBe('your buy stop and covers: no order is working');
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

  it('the cover is yours alone: no "Nova takes the cover" (ADR 072)', async () => {
    renderTab();
    const card = await screen.findByTestId('held-card');
    expect(within(card).queryByTestId('held-nova-exit')).toBeNull();
    expect(screen.queryByTestId('exit-sheet')).toBeNull();
    expect(calls.some(c => c.url.includes('/api/stock-mode'))).toBe(false);
  });

  it('judges the trade by the buy stop resting at the broker until you set one', async () => {
    renderTab('paper', 5.89);
    const card = await screen.findByTestId('held-card');
    await waitFor(() => expect(reads().some(u => /held_stop=5.89/.test(u))).toBe(true));
    await waitFor(() => expect(within(card).getByTestId('held-note').textContent)
      .toBe('your buy stop 5.89 is working at the broker'));
    expect(card.querySelector('.sr-num--stop .sr-num__s')?.textContent).toBe('resting at the broker');
  });
});
