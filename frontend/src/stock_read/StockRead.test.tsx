/**
 * @vitest-environment jsdom
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { subscribeOrderTicketPrefill, type OrderTicketPrefill } from '../ibkr/orderTicketPrefill';
import { STOCK_READ_RISK_KEY } from './constants';
import { StockReadSheet } from './ReadSheet';
import { StockReadProvider, useStockReadContext } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { StockReadToolbar } from './StockReadToolbar';
import { apusAt, apusDecisionsWire, apusHistoryWire, apusReadWire } from './stockReadFixtures';

type Json = Record<string, unknown>;
let responses: { match: RegExp; status?: number; body: Json }[] = [];
let calls: string[] = [];

function respond(match: RegExp, body: Json, status = 200) {
  responses.unshift({ match, status, body });
}

beforeEach(() => {
  localStorage.clear();
  calls = [];
  responses = [];
  respond(/\/api\/stock-read\/APUS\/history$/, apusHistoryWire);
  respond(/\/api\/stock-read\/APUS\/decisions$/, apusDecisionsWire);
  respond(/\/api\/stock-read\/APUS(\?|$)/, apusReadWire);
  vi.stubGlobal('fetch', vi.fn(async (input: unknown) => {
    const url = String(input);
    calls.push(url);
    const hit = responses.find(r => r.match.test(url));
    if (!hit) return new Response('{}', { status: 404 });
    return new Response(JSON.stringify(hit.body), { status: hit.status ?? 200 });
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

let lastCtx: ReturnType<typeof useStockReadContext> = null;
function Probe() {
  lastCtx = useStockReadContext();
  return null;
}

function renderRail(opts: { replay?: boolean; ask?: number | null } = {}) {
  const ask = opts.ask === undefined ? 5.39 : opts.ask;
  return render(
    <StockReadProvider symbol="APUS" active replay={opts.replay ?? false}
      topOfBook={{ symbol: 'APUS', bid: 5.36, ask, depthSubscribed: true } as never}>
      <StockReadToolbar />
      <StockReadRail />
      <StockReadSheet />
      <Probe />
    </StockReadProvider>,
  );
}

describe('the plan on the rail', () => {
  it("shows the forming bull flag's plan: entry, stop, 2R target, risk and the size $20 buys", async () => {
    renderRail();
    const plan = await screen.findByTestId('stock-read-plan');
    expect(within(plan).getByText('Bull flag')).toBeTruthy();
    expect(within(plan).getByText('FORMING 1/2')).toBeTruthy();
    expect(screen.getByTestId('stock-read-entry').textContent).toBe('5.44');
    expect(screen.getByTestId('stock-read-stop').textContent).toBe('5.33');
    expect(screen.getByTestId('stock-read-target').textContent).toBe('5.66');
    expect(screen.getByTestId('stock-read-risk').textContent).toBe('0.11');
    expect(screen.getByTestId('stock-read-size').textContent).toBe('181 sh');
    expect(within(plan).getByText('Target 2R')).toBeTruthy();
    expect(screen.getByTestId('stock-read-checks').textContent).toContain('under VWAP 6.09');
    expect(screen.getByTestId('stock-read-plan-note').textContent).toBe('provisional: arms after 1 more red or doji candle');
    expect(calls[0]).toMatch(/\/api\/stock-read\/APUS$/);
  });

  it('locks Stage in ticket with the reason while no ticket listens, then fills the ticket without placing', async () => {
    renderRail();
    const stage = await screen.findByTestId('stock-read-stage');
    expect(stage.hasAttribute('disabled')).toBe(true);
    expect(stage.getAttribute('data-why')).toMatch(/no order ticket open/);
    const got: OrderTicketPrefill[] = [];
    let off = () => {};
    act(() => {
      off = subscribeOrderTicketPrefill('APUS', req => got.push(req));
    });
    await waitFor(() => expect(stage.hasAttribute('disabled')).toBe(false));
    fireEvent.click(stage);
    expect(got).toEqual([{ symbol: 'APUS', side: 'BUY', orderType: 'LMT', quantityValue: '181', limitPrice: '5.44' }]);
    expect(screen.getByTestId('stock-read-plan-note').textContent).toMatch(/Staged BUY 181 LMT 5.44.*no bracket/);
    off();
  });

  it('sizes from the risk per trade the operator sets, and keeps it', async () => {
    renderRail();
    fireEvent.click(await screen.findByTestId('stock-read-risk-usd'));
    const input = screen.getByTestId('stock-read-risk-usd-input');
    fireEvent.change(input, { target: { value: '40' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(screen.getByTestId('stock-read-size').textContent).toBe('363 sh');
    expect(localStorage.getItem(STOCK_READ_RISK_KEY)).toContain('40');
  });

  it('folds to one line, keeps Stage there, and remembers the operator opening it', async () => {
    localStorage.setItem('nova.stockRead.layers',
      JSON.stringify({ schema_version: 1, value: { setups: true, levels: true, hidden: [], plan: 'folded' } }));
    renderRail();
    const line = await screen.findByTestId('stock-read-plan-line');
    expect(line.textContent).toBe('5.44/5.33/5.66 · 181 sh');
    expect(screen.getByText('FLAG 1/2')).toBeTruthy();
    expect(screen.queryByTestId('stock-read-entry')).toBeNull();
    expect(screen.getByTestId('stock-read-stage-line').getAttribute('data-why')).toMatch(/no order ticket open/);
    fireEvent.click(screen.getByTestId('stock-read-plan-fold'));
    expect(screen.getByTestId('stock-read-entry').textContent).toBe('5.44');
    expect(localStorage.getItem('nova.stockRead.layers')).toContain('"plan":"open"');
  });

  it('switches the drawings from the plan and the toolbar alike', async () => {
    renderRail();
    const show = await screen.findByTestId('stock-read-show-on-chart');
    expect(show.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByTestId('stock-read-toggle-setups'));
    expect(show.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByTestId('stock-read-toggle-setups').textContent).toContain('Setups off');
  });

  it('plans a hand trade at the ask when nothing is forming, then asks the backend for it', async () => {
    respond(/\/api\/stock-read\/APUS$/, { ...apusReadWire, plan: null });
    respond(/\/api\/stock-read\/APUS\?entry=/, {
      ...apusReadWire,
      plan: { ...apusReadWire.plan, source: 'manual', setup_type: null, kind: null, state: 'manual', trigger: null,
        entry: 5.39, stop: 5.31, target: 5.55, risk: 0.08, reward: 0.16, rr: 2,
        stop_rule: 'the lowest low of the last 3 closed 1-min candles', entry_rule: 'your entry',
        target_rule: 'entry + 2 x risk', reason: 'no setup is forming: your entry, a 2:1 target' },
    });
    renderRail({ ask: 5.39 });
    fireEvent.click(await screen.findByTestId('stock-read-entry-ask'));
    await waitFor(() => expect(calls.some(u => /\?entry=5\.39$/.test(u))).toBe(true));
    const entry = await screen.findByTestId('stock-read-entry-input');
    await waitFor(() => expect((entry as HTMLInputElement).value).toBe('5.39'));
    expect(screen.getByText('NO SETUP')).toBeTruthy();
    expect(screen.getByTestId('stock-read-size').textContent).toBe('250 sh');
    const stopInput = screen.getByTestId('stock-read-stop-input');
    fireEvent.change(stopInput, { target: { value: '5.30' } });
    fireEvent.blur(stopInput);
    await waitFor(() => expect(calls.some(u => /\?entry=5\.39&stop=5\.3$/.test(u))).toBe(true));
    fireEvent.click(screen.getByTestId('stock-read-clear-manual'));
    expect(lastCtx?.manual).toEqual({ entry: null, stop: null });
  });

  it('says why there is no read: a replay desk, an older backend', async () => {
    renderRail({ replay: true });
    expect(screen.getByTestId('stock-read-rail-note').textContent).toMatch(/replaying another moment/);
    expect(calls).toEqual([]);
    cleanup();
    responses = [];
    renderRail();
    await waitFor(() => expect(screen.getByTestId('stock-read-rail-note').textContent).toMatch(/reload the backend/));
  });
});

describe('the tiles and the sheet', () => {
  it('shows seven tiles and All, a tile opens its rows on focus and the sheet on click', async () => {
    renderRail();
    await screen.findByTestId('stock-read-strip');
    const front = screen.getByTestId('stock-read-tile-front');
    expect(front.textContent).toContain('Mixed');
    expect(front.querySelectorAll('.sr-dot')).toHaveLength(3);
    expect(screen.getByTestId('stock-read-all').textContent).toContain('15'); // every row of the seven groups
    fireEvent.focus(front);
    const pop = await screen.findByTestId('stock-read-popover');
    expect(pop.textContent).toContain('MACD 1-minute');
    expect(pop.textContent).toContain('Is momentum still up, or is it fading?');
    fireEvent.click(front);
    const sheet = await screen.findByTestId('stock-read-sheet');
    expect(within(sheet).getByTestId('stock-read-group-front')).toBeTruthy();
    expect(lastCtx?.sheet).toEqual({ open: true, tab: 'signals', group: 'front' });
  });

  it('filters the signals by what they say', async () => {
    renderRail();
    fireEvent.click(await screen.findByTestId('stock-read-all'));
    fireEvent.click(await screen.findByTestId('stock-read-filter-bad'));
    const groups = screen.getAllByTestId(/stock-read-group-/).map(g => g.getAttribute('data-group'));
    expect(groups).toEqual(['front']);
    fireEvent.click(screen.getByTestId('stock-read-filter-all'));
    fireEvent.change(screen.getByTestId('stock-read-search'), { target: { value: 'borrow' } });
    expect(screen.getAllByTestId(/stock-read-row-/).map(r => r.getAttribute('data-testid'))).toEqual(['stock-read-row-borrow']);
  });

  it("lists the bot's day and frames a decision on the chart", async () => {
    renderRail();
    fireEvent.click(await screen.findByTestId('stock-read-all'));
    fireEvent.click(screen.getByTestId('stock-read-tab-decisions'));
    const events = await screen.findAllByTestId('stock-read-event');
    expect(events).toHaveLength(4);
    expect(events[2].textContent).toContain('Not armed: risk 0.29 is over the 0.20 cap');
    expect(events[2].textContent).toContain('×3 to 09:28');
    expect(screen.getByTestId('stock-read-sources-failed').textContent).toContain('borrow (OSError: locked)');
    fireEvent.click(within(events[1]).getByText('show on chart ›'));
    expect(lastCtx?.focus?.ts).toBe(apusAt(9, 24));
    expect(lastCtx?.sheet.open).toBe(false);
  });

  it('shows the history: the runs, the split and what Nova holds', async () => {
    renderRail();
    fireEvent.click(await screen.findByTestId('stock-read-all'));
    fireEvent.click(screen.getByTestId('stock-read-tab-history'));
    const hist = await screen.findByTestId('stock-read-history');
    await waitFor(() => expect(hist.textContent).toContain('A 1-for-10 reverse split 63 days ago.'));
    expect(screen.getByTestId('stock-read-runs').querySelectorAll('tbody tr')).toHaveLength(2);
    expect(screen.getByTestId('stock-read-daily-chart').querySelectorAll('.sr-daily__run')).toHaveLength(2);
    expect(hist.textContent).toContain('Not kept per symbol yet');
  });

  it('closes on Escape', async () => {
    renderRail();
    fireEvent.click(await screen.findByTestId('stock-read-all'));
    expect(screen.getByTestId('stock-read-sheet')).toBeTruthy();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('stock-read-sheet')).toBeNull();
  });
});
