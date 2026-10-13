/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetFeedImagesForTests } from './FeedImage';
import { resetFollowedStoresForTests } from './followedStores';
import { day, T } from './followedTestData';
import { FollowedTradersPage } from './FollowedTradersPage';
import type { FollowedDay } from './types';

type Route = (url: URL) => Response | undefined;

describe('FollowedTradersPage', () => {
  let container: HTMLDivElement;
  let root: Root;
  let asked: string[];

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    asked = [];
    resetFollowedStoresForTests();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} }));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    resetFeedImagesForTests();
    vi.unstubAllGlobals();
  });

  async function show(dayAnswer: FollowedDay | (() => Response), extra: Route = () => undefined) {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://desk');
      asked.push(url.pathname + url.search);
      const other = extra(url);
      if (other) return other;
      if (url.pathname.endsWith('.jpg')) return new Response(new Blob(['jpeg']), { status: 200 });
      if (url.pathname === '/api/followed-traders/day') {
        return typeof dayAnswer === 'function' ? dayAnswer() : new Response(JSON.stringify(dayAnswer));
      }
      return new Response('', { status: 404 });
    }));
    await act(async () => {
      root.render(<FollowedTradersPage />);
    });
    await flush();
  }
  async function flush() {
    for (let i = 0; i < 4; i += 1) await act(async () => { await Promise.resolve(); });
  }
  const q = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;
  const click = async (el: Element | null) => {
    await act(async () => { (el as HTMLElement).click(); });
    await flush();
  };

  it('says the feed is not configured on a 404, never an empty list', async () => {
    await show(() => new Response('', { status: 404 }));
    expect(q('ft-state')!.textContent).toMatch(/not configured/);
  });

  it('says the feed is down with its reason in the pill', async () => {
    await show(day({ feed: { state: 'unreachable', error: 'timed out after 3 s' }, traders: [], capture: null,
      prices: null, overall: null, dates: [] }));
    expect(q('ft-capture-pill')!.textContent).toBe('The feed is not answering · timed out after 3 s');
    expect(q('ft-trader-ALPHA')).toBeNull();
  });

  it('draws the bar now, each trader, their tables and the activity', async () => {
    await show(day());
    expect(q('ft-capture-pill')!.textContent).toBe('Live · 6s behind the stream · bar read 10:09:54 ET');
    expect(q('ft-slot-ALPHA')!.textContent).toContain('LONG ABCD 2.00');
    expect(q('ft-slot-ALPHA')!.textContent).toContain('SHORT none');
    // No live image for BRAVO: their newest evidence stands in, with its time.
    expect(q('ft-slot-BRAVO')!.textContent).toContain('Their slot at their last change · 09:59:00 ET');
    expect(q('ft-trader-ALPHA')!.textContent).toContain('On air');
    expect(q('ft-record-ALPHA')!.textContent).toContain('1W / 0L · 1 open · Win rate 100%');
    expect(q('ft-row-o1')!.textContent).toContain('2.50');
    expect(q('ft-row-o1')!.textContent).toContain('+0.50');
    expect(q('ft-row-c2')!.textContent).toContain('by 09:40:00');
    expect(q('ft-row-c2')!.textContent).toContain('77.10–77.90 est.');
    expect(q('ft-row-c2')!.textContent).toContain('unscored');
    expect(q('ft-activity')!.textContent).toContain('ALPHA closed');
    expect(asked).toContain('/api/followed-traders/live/ALPHA.jpg');
    expect(asked).toContain('/api/followed-traders/faces/2026-10-13/ALPHA.jpg');
  });

  it('says why open positions are not priced', async () => {
    const d = day({ prices: { state: 'ibkr_down', why: 'IBKR is not connected' } });
    d.traders[0].open[0].now = { state: 'off', price: null, trade_ts: null, why: 'IBKR is not connected' };
    await show(d);
    expect(q('ft-prices')!.textContent).toBe('Prices now: IBKR is not connected');
  });

  it('opens a trade’s proof with what was read and the reads ignored', async () => {
    const reads = {
      schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, date: '2026-10-13', trader: 'ALPHA',
      available: true, why: null, truncated: false,
      reads: [
        { ts: T - 600, until_ts: T - 500, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFGH', price: 2 }] },
        { ts: T - 500, until_ts: T - 498, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFG', price: 12 }] },
        { ts: T - 498, until_ts: T + 300, seen: true, unparsed: [], positions: [{ side: 'long', symbol: 'EFGH', price: 2 }] },
        { ts: T + 300, until_ts: null, seen: true, unparsed: [], positions: [] },
      ],
    };
    await show(day(), (url) => url.pathname === '/api/followed-traders/reads'
      ? new Response(JSON.stringify(reads)) : undefined);
    await click(q('ft-proof-c1'));
    const proof = q('ft-proof')!;
    expect(proof.textContent).toContain('EFGH 2.00 new');
    expect(proof.textContent).toContain('EFGH 2.00 gone');
    expect(proof.textContent).toContain('1 read during this trade differed from what was logged and was ignored');
    expect(proof.textContent).not.toMatch(/drop this trade/i);
    expect(asked.some((a) => a.startsWith('/api/followed-traders/reads?date=2026-10-13&trader=ALPHA'))).toBe(true);
    await click(q('ft-proof-back'));
    expect(q('ft-proof')).toBeNull();
  });

  it('asks the record for Week, and the day’s own for Day', async () => {
    const week = { schema_version: 1, generated_at: T, feed: { state: 'ok', error: null }, range: 'week',
      from: '2026-10-07', to: '2026-10-13', dates: [], pending: 2,
      overall: { wins: 5, losses: 2, scratches: 0, unscored: 1, open: 1, win_rate: 71.4 },
      traders: [{ name: 'ALPHA', record: { wins: 4, losses: 1, scratches: 0, unscored: 0, open: 1, win_rate: 80 } }] };
    await show(day(), (url) => url.pathname === '/api/followed-traders/record' ? new Response(JSON.stringify(week)) : undefined);
    await click(q('ft-range-week'));
    expect(asked).toContain('/api/followed-traders/record?range=week&date=2026-10-13');
    expect(q('ft-record-ALPHA')!.textContent).toContain('4W / 1L · 1 open · Win rate 80%');
    expect(q('ft-record-everyone')!.textContent).toContain('Win rate 71.4%');
    expect(q('ft-records')!.textContent).toContain('2 exits still being read from IBKR');
  });

  it('steps to the previous day and opens the calendar with a preview', async () => {
    await show(day());
    expect((q('ft-next-day') as HTMLButtonElement).disabled).toBe(true);
    expect(q('ft-next-day')!.getAttribute('data-why')).toBeTruthy();
    await click(q('ft-day-button'));
    expect(q('ft-day-picker')).not.toBeNull();
    expect((q('ft-day-2026-10-14') as HTMLButtonElement).disabled).toBe(true);
    await click(q('ft-day-2026-10-09'));
    expect(asked).toContain('/api/followed-traders/day?date=2026-10-09&quotes=0');
    await click(q('ft-prev-day'));
    expect(asked).toContain('/api/followed-traders/day?date=2026-10-09');
  });
});
