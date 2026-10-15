/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { FOLLOWED_TOAST_POLL_MS } from './constants';
import { day, trade, T } from './followedTestData';
import { resetFollowedStoresForTests, setFollowedAlerts, useFollowedProofRequest } from './followedStores';
import { FollowedToasts } from './FollowedToasts';
import type { FollowedDay } from './types';

const gate = vi.hoisted(() => ({ on: true }));
vi.mock('./enabledStore', () => ({ useFollowedTradersEnabled: () => gate.on }));

let lastRequest: unknown = null;
function Probe() {
  lastRequest = useFollowedProofRequest();
  return null;
}

describe('FollowedToasts', () => {
  let container: HTMLDivElement;
  let root: Root;
  let answers: FollowedDay[];
  let asked: string[];

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    resetFollowedStoresForTests();
    resetNavRailStoreForTests();
    gate.on = true;
    asked = [];
    answers = [day()];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      asked.push(String(input));
      const body = answers.length > 1 ? answers.shift()! : answers[0];
      return new Response(JSON.stringify(body));
    }));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  async function tick(ms: number) {
    await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
  }
  const q = (sel: string) => container.querySelector(sel) as HTMLElement | null;

  it('raises nothing for what was there, then a toast for a new trade, read without prices', async () => {
    const next = day();
    next.traders[0].open.push(trade({ id: 'n1', symbol: 'NEW',
      entry: { first_price: 3.1, avg_price: 3.1, ts: T + 620, since_ts: null, known: true } }));
    answers = [day(), next];
    const onOpenPage = vi.fn();
    await act(async () => { root.render(<><FollowedToasts onOpenPage={onOpenPage} /><Probe /></>); });
    await tick(0);
    expect(q('[data-testid="ft-toasts"]')).toBeNull();
    expect(asked[0]).toContain('/api/followed-traders/day?quotes=0');
    await tick(FOLLOWED_TOAST_POLL_MS);
    const toast = q('[data-testid="ft-toast-n1|in"]')!;
    expect(toast.textContent).toContain('ALPHA opened LONG NEW @ 3.10');
    await act(async () => { (toast.querySelector('.ft-link') as HTMLElement).click(); });
    expect(onOpenPage).toHaveBeenCalled();
    expect(getNavPage()).toBe('followed');
    expect(lastRequest).toEqual({ date: '2026-10-13', tradeId: 'n1' });
    expect(q('[data-testid="ft-toast-n1|in"]')).toBeNull();
  });

  it('opens the TraderTV LIVE page on today on a click anywhere on the toast, its padding too', async () => {
    const next = day();
    next.traders[0].open.push(trade({ id: 'n2', symbol: 'NEW',
      entry: { first_price: 3.1, avg_price: 3.1, ts: T + 620, since_ts: null, known: true } }));
    answers = [day(), next];
    const onOpenPage = vi.fn();
    await act(async () => { root.render(<><FollowedToasts onOpenPage={onOpenPage} /><Probe /></>); });
    await tick(0);
    await tick(FOLLOWED_TOAST_POLL_MS);
    const toast = q('[data-testid="ft-toast-n2|in"]')!;
    await act(async () => { toast.click(); });
    expect(onOpenPage).toHaveBeenCalledTimes(1);
    expect(getNavPage()).toBe('followed');
    expect(lastRequest).toEqual({ date: null, tradeId: null });
    expect(q('[data-testid="ft-toast-n2|in"]')).toBeNull();
  });

  it('asks nothing while Alerts are off or no feed is configured', async () => {
    setFollowedAlerts(false);
    await act(async () => { root.render(<FollowedToasts />); });
    await tick(FOLLOWED_TOAST_POLL_MS * 2);
    expect(asked).toEqual([]);
    gate.on = false;
    setFollowedAlerts(true);
    await act(async () => { root.render(<FollowedToasts />); });
    await tick(FOLLOWED_TOAST_POLL_MS * 2);
    expect(asked).toEqual([]);
  });
});
