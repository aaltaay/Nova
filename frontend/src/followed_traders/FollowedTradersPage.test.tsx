/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { captureLine, FollowedTradersPage, recordLine, tradeLine } from './FollowedTradersPage';
import type { FollowedCapture, FollowedDay, FollowedTrade } from './types';

const T = Date.UTC(2026, 9, 13, 14, 0, 0) / 1000; // 10:00:00 ET
const RECORD = { wins: 0, losses: 0, scratches: 0, unscored: 0, open: 0, win_rate: null };

function trade(over: Partial<FollowedTrade>): FollowedTrade {
  return {
    id: 'x', trader: 'ALPHA', side: 'long', symbol: 'ABCD', status: 'open',
    entry: { first_price: 2, avg_price: 2, ts: T, since_ts: null, known: true },
    adds: [], now: null, exit: null, pl: null, held: { min_sec: 600, max_sec: 600 }, result: null,
    evidence: { entry: null, exit: null }, ...over,
  };
}

function capture(over: Partial<FollowedCapture> = {}): FollowedCapture {
  return { live: true, clock: '10:10:00', updated_at: T + 598, age_sec: 2, bar_visible: true, title: 'Show',
    traders: ['ALPHA'], problem: null, problem_at: null, ...over };
}

function day(over: Partial<FollowedDay> = {}): FollowedDay {
  return {
    schema_version: 1, generated_at: T + 600, feed: { state: 'ok', error: null },
    date: '2026-10-13', today: '2026-10-13', dates: ['2026-10-13'], capture: capture(),
    prices: { state: 'live', why: null },
    overall: { ...RECORD, wins: 1, open: 1, win_rate: 100 },
    traders: [{
      name: 'ALPHA', record: { ...RECORD, wins: 1, open: 1, win_rate: 100 },
      open: [trade({ id: 'o1', now: { state: 'live', price: 2.5, trade_ts: T + 599, why: null }, pl: { per_share: 0.5, pct: 25 } })],
      closed: [trade({ id: 'c1', symbol: 'EFGH', status: 'closed', result: 'win',
        exit: { state: 'at', price: 2.2, low: null, high: null, from_ts: null, to_ts: T + 300, trade_ts: T + 299,
          source: 'ibkr_trades', why: null },
        pl: { per_share: 0.2, pct: 10 } })],
    }],
    ...over,
  };
}

describe('FollowedTradersPage (placeholder)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  async function show(respond: () => Response) {
    vi.stubGlobal('fetch', vi.fn(async () => respond()));
    await act(async () => {
      root.render(<FollowedTradersPage />);
    });
    await act(async () => {
      await Promise.resolve();
    });
  }
  const q = (id: string) => container.querySelector(`[data-testid="${id}"]`) as HTMLElement | null;

  it('says the feed is not configured on a 404, never an empty list', async () => {
    await show(() => new Response('', { status: 404 }));
    expect(q('ft-state')!.textContent).toMatch(/not configured/);
  });

  it('says the feed is down with its reason', async () => {
    await show(() => new Response(JSON.stringify(day({ feed: { state: 'unreachable', error: 'timed out after 3 s' },
      traders: [], capture: null, prices: null, overall: null, dates: [] }))));
    expect(q('ft-state')!.textContent).toMatch(/did not answer.*timed out after 3 s/);
  });

  it('shows each trader, their record and one line per trade', async () => {
    await show(() => new Response(JSON.stringify(day())));
    expect(q('ft-capture')!.textContent).toBe('Live · read 2s ago · 10:10:00 ET');
    expect(q('ft-trader-ALPHA')!.textContent).toContain('1W / 0L / 1 open');
    expect(q('ft-row-o1')!.textContent).toContain('now 2.50');
    expect(q('ft-row-c1')!.textContent).toContain('exit 2.20 (10:05:00)');
    expect(q('ft-row-c1')!.textContent).toContain('win');
  });

  it('says capture stopped, with the feed’s own reason', () => {
    expect(captureLine(capture({ age_sec: 125, problem: 'the source wants a sign-in' })))
      .toBe('Capture stopped 2m 05s ago: the source wants a sign-in');
    expect(captureLine(capture({ updated_at: null, age_sec: null, problem: 'no stream' }))).toBe('Capture stopped: no stream');
    expect(captureLine(capture({ bar_visible: false }))).toContain('positions hidden');
  });

  it('writes a window exit as estimated and a record without a decided trade as no win rate', () => {
    const line = tradeLine(trade({ status: 'closed', result: 'unscored',
      exit: { state: 'range', price: null, low: 1.7, high: 1.9, from_ts: T + 300, to_ts: T + 600, trade_ts: null,
        source: 'ibkr_trades', why: null },
      pl: { low_per_share: -0.3, high_per_share: -0.1, low_pct: -15, high_pct: -5 } }));
    expect(line).toContain('exit 1.70–1.90 (10:05:00–10:10:00, estimated)');
    expect(line).toContain('unscored');
    expect(recordLine({ ...RECORD, scratches: 1 })).toContain('win rate —');
  });
});
