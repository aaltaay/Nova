/**
 * @vitest-environment jsdom
 *
 * The trade's moment on the Trader tab (ADR 037): the track under the chart's badge and the ping's mute, the plan in
 * the Level 2 book, and no Who trades switch anywhere -- the strategies only watch, so the tab never asks who trades
 * the stock (ADR 072). Against a fake backend that answers the stock read and the sleeve.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import { DESK_SOUND_KEYS } from '../sound';
import { ChartLegend } from './ChartLegend';
import { sleeveSessionWire } from './momentFixtures';
import { resetStockReadSoundForTests } from './momentSound';
import { StockReadProvider, useLevel2Markers, useStockReadContext } from './StockReadContext';
import { StockReadRail } from './StockReadRail';
import { apusReadWire } from './stockReadFixtures';

let urls: string[] = [];

function answer(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem(NOVA_API_KEY_STORAGE, 'desk-key');
  resetStockReadSoundForTests();
  _resetSleeveForTests();
  urls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: unknown) => {
    const url = String(input);
    urls.push(url);
    if (/\/api\/stock-read\/APUS(\?|$)/.test(url)) return answer(apusReadWire);
    if (/\/api\/bot\/session$/.test(url)) return answer(sleeveSessionWire(20));
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

function renderTab() {
  return render(
    <StockReadProvider symbol="APUS" active replay={false}
      topOfBook={{ symbol: 'APUS', bid: 5.36, ask: 5.39, depthSubscribed: true } as never}>
      <StockReadRail />
      <Legend />
      <Markers />
    </StockReadProvider>,
  );
}

describe('on the 1-minute chart', () => {
  it('carries the track under the badge, and the bell mutes the ping on every tab', async () => {
    renderTab();
    const track = await screen.findByTestId('moment-track');
    expect(within(track).getByText('Forming').getAttribute('data-state')).toBe('now');
    expect(screen.getByTestId('stock-read-badge').textContent).toBe('BULL FLAG · FORMING 1 OF 2');
    fireEvent.click(screen.getByTestId('moment-bell'));
    expect(screen.getByTestId('moment-bell').getAttribute('aria-pressed')).toBe('false');
    expect(JSON.parse(localStorage.getItem(DESK_SOUND_KEYS.calls) ?? '{}')).toEqual({ schema_version: 1, value: false });
  });

  it('has no Who trades chip or row, and never asks who trades the stock (ADR 072)', async () => {
    renderTab();
    await screen.findByTestId('moment-track');
    expect(screen.queryByTestId('who-trades-chip')).toBeNull();
    expect(screen.queryByTestId('who-trades')).toBeNull();
    expect(urls.some(u => u.includes('/api/stock-mode'))).toBe(false);
  });
});

describe('the plan in Level 2', () => {
  it('draws ENTRY, STOP, TARGET and T2 dashed while they are only a plan', async () => {
    renderTab();
    // Target 2 (#845) is marked the same way, labelled T2.
    await waitFor(() => expect(screen.getByTestId('markers').textContent)
      .toBe('ENTRY 5.44:dashed|STOP 5.33:dashed|TARGET 5.49:dashed|T2 5.99:dashed'));
  });

  it('the plan card stages your own ticket and offers nothing of the bot', async () => {
    renderTab();
    await screen.findByTestId('stock-read-plan');
    expect(screen.queryByTestId('stock-read-stage')).not.toBeNull();
    expect(screen.queryByTestId('stock-read-nova-size')).toBeNull();
    expect(document.querySelector('[data-testid^="stock-read-action-"]')).toBeNull();
  });
});
