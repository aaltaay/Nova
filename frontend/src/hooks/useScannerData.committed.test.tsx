// @vitest-environment jsdom
import { createElement, startTransition, StrictMode, Suspense, useLayoutEffect, useState } from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useScannerData } from './useScannerData';
import type { ScannerRosterHandlers } from './useScannerPriceStream';

const callbacks = vi.hoisted(() => ({ stream: null as ScannerRosterHandlers | null,
  envelope: null as null | ((data: Record<string, unknown>) => void) }));
vi.mock('./useScannerPriceStream', () => ({
  useScannerPriceStream: (handlers: ScannerRosterHandlers) => {
    callbacks.stream = handlers;
    return { pricesStale: false, flashSymbols: {}, lastPriceTs: 0, rowQuoteTs: {}, subscriptionError: null };
  },
}));
vi.mock('../scanner/useScannerEnvelopePoll', () => ({
  // The real poll also publishes its latest callback ref during render.
  useScannerEnvelopePoll: (opts: { onEnvelope: typeof callbacks.envelope }) => { callbacks.envelope = opts.onEnvelope; },
}));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function envelope(price = 4.3) {
  return { dates: ['2026-09-23'], gappers: [{ symbol: 'PFSA', price, halted: false }],
    gainers: [], losers: [], afterhours: [], large_cap: [], catalysts: [],
    table_state: 'frozen', last_scan: 100, data_feed: 'ibkr' };
}

function pendingBody() {
  let release!: (value: unknown) => void;
  const body = new Promise<unknown>(resolve => { release = resolve; });
  const response = new Response('{}', { status: 200 });
  const read = vi.spyOn(response, 'json').mockImplementation(() => body);
  return { response, read, release };
}

type Choice = { provider: string; persistent: boolean; suspend: boolean; feed: (value: string) => void };

function harness(strict = false) {
  let choose!: (patch: Partial<Choice>) => void;
  let committed!: ReturnType<typeof useScannerData>;
  let previews = 0;
  const feed = vi.fn();
  const never = new Promise<void>(() => {});

  function Scanner({ provider, persistent, suspend, feed }: Choice) {
    const data = useScannerData({ discoveryProvider: provider, scannerPersistentAuthoritative: persistent, onActiveFeed: feed });
    useLayoutEffect(() => { committed = data; });
    if (suspend) { previews += 1; throw never; }
    return createElement('output', { 'data-testid': 'scanner' },
      `${provider}/${data.historyDate ?? 'Live'}/${data.gappers[0]?.price ?? 'pending'}/${data.gappers[0]?.halted ? 'HALTED' : 'TRADING'}`);
  }
  function App() {
    const [choice, setChoice] = useState<Choice>({ provider: 'ibkr', persistent: true, suspend: false, feed });
    choose = patch => setChoice(previous => ({ ...previous, ...patch }));
    return createElement(Suspense, { fallback: createElement('div', null, 'fallback') }, createElement(Scanner, choice));
  }
  const view = render(strict ? createElement(StrictMode, null, createElement(App)) : createElement(App));
  return { row: view.getByTestId('scanner'), feed, unmount: view.unmount, committed: () => committed,
    choose: (patch: Partial<Choice>) => choose(patch), previews: () => previews,
    discard: () => choose({ provider: 'ibkr', persistent: true, suspend: false, feed }) };
}

async function preview(h: ReturnType<typeof harness>, patch: Partial<Choice>) {
  await act(async () => { startTransition(() => h.choose({ ...patch, suspend: true })); });
  await waitFor(() => expect(h.previews()).toBeGreaterThan(0));
}

it.each(['provider', 'persistent'] as const)('keeps a committed live bootstrap and its halt receipts through a discarded %s preview', async dimension => {
  const pending = pendingBody();
  const fetcher = vi.fn(async (url: string) => url.endsWith('/gappers') ? pending.response
    : new Response(JSON.stringify(envelope()), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  const h = harness();
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  await preview(h, dimension === 'provider' ? { provider: 'other' } : { persistent: false });
  expect(h.row.textContent).toContain('ibkr/Live/pending');
  act(() => callbacks.stream!.onHaltPatch!([{ symbol: 'PFSA', halted: true }]));
  await act(async () => pending.release(envelope()));
  act(h.discard);
  expect(h.row.textContent).toContain('ibkr/Live/4.3/HALTED');
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/gappers'))).toHaveLength(1);
});

it.each(['provider', 'persistent'] as const)('keeps the committed selected-history request through a discarded %s preview', async dimension => {
  const pending = pendingBody();
  const fetcher = vi.fn(async (url: string) => url.includes('/history/gappers/') ? pending.response
    : new Response(JSON.stringify(envelope()), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  const h = harness();
  await waitFor(() => expect(h.row.textContent).toContain('ibkr/Live/4.3'));
  act(() => h.committed().setHistoryDate('2026-09-23'));
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  await preview(h, dimension === 'provider' ? { provider: 'other' } : { persistent: false });
  expect(h.row.textContent).toContain('ibkr/2026-09-23/4.3');
  await act(async () => pending.release(envelope(4.2)));
  act(h.discard);
  expect(h.row.textContent).toContain('ibkr/2026-09-23/4.2');
  expect(fetcher.mock.calls.filter(([url]) => url.includes('/history/gappers/'))).toHaveLength(1);
});

it('accepts current live halt evidence while a history preview is suspended', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(envelope()), { status: 200 })));
  const h = harness();
  await waitFor(() => expect(h.row.textContent).toContain('ibkr/Live/4.3/TRADING'));
  const halt = callbacks.stream!.onHaltPatch!;
  await act(async () => { startTransition(() => {
    h.committed().setHistoryDate('2026-09-23');
    h.choose({ suspend: true });
  }); });
  await waitFor(() => expect(h.previews()).toBeGreaterThan(0));
  expect(h.row.textContent).toContain('ibkr/Live/4.3/TRADING');
  act(() => halt([{ symbol: 'PFSA', halted: true }]));
  expect(h.row.textContent).toContain('ibkr/Live/4.3/HALTED');
});

it.each(['envelope', 'refresh'] as const)('uses committed feed callbacks for a live %s during a suspended callback preview', async source => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(envelope()), { status: 200 })));
  const h = harness();
  await waitFor(() => expect(h.row.textContent).toContain('ibkr/Live/4.3'));
  h.feed.mockClear();
  const previewFeed = vi.fn();
  await preview(h, { feed: previewFeed });
  if (source === 'envelope') act(() => callbacks.envelope!({ data_feed: 'ibkr' }));
  else await act(async () => h.committed().fetchData());
  expect(h.feed).toHaveBeenCalledWith('ibkr');
  expect(previewFeed).not.toHaveBeenCalled();
});

it.each(['live', 'history'] as const)('retains a pending %s response when Suspense hides then reveals the same committed view', async mode => {
  const pending = pendingBody();
  const pendingRoute = (url: string) => mode === 'live' ? url.endsWith('/gappers') : url.includes('/history/gappers/');
  const fetcher = vi.fn(async (url: string) => pendingRoute(url) ? pending.response
    : new Response(JSON.stringify(envelope()), { status: 200 }));
  vi.stubGlobal('fetch', fetcher);
  const h = harness();
  if (mode === 'history') {
    await waitFor(() => expect(h.row.textContent).toContain('ibkr/Live/4.3'));
    act(() => h.committed().setHistoryDate('2026-09-23'));
  }
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  act(() => h.choose({ suspend: true }));
  expect(document.body.textContent).toContain('fallback');
  await act(async () => pending.release(envelope(mode === 'live' ? 4.3 : 4.2)));
  act(h.discard);
  expect(h.row.textContent).toContain(mode === 'live' ? 'ibkr/Live/4.3' : 'ibkr/2026-09-23/4.2');
  expect(fetcher.mock.calls.filter(([url]) => pendingRoute(url))).toHaveLength(1);
});

it('rejects pending response callbacks after a true unmount', async () => {
  const pending = pendingBody();
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url.endsWith('/gappers') ? pending.response
    : new Response(JSON.stringify(envelope()), { status: 200 })));
  const h = harness();
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  h.unmount();
  await act(async () => pending.release(envelope()));
  expect(h.feed).not.toHaveBeenCalled();
});

it('loads the current StrictMode effect mount and rejects the disposed mount response', async () => {
  const pending = pendingBody();
  let gappersRequests = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.endsWith('/gappers') && ++gappersRequests === 1) return pending.response;
    return new Response(JSON.stringify(envelope()), { status: 200 });
  }));
  const h = harness(true);
  await waitFor(() => expect(h.row.textContent).toContain('ibkr/Live/4.3'));
  expect(gappersRequests).toBe(2);
  await act(async () => pending.release(envelope(9.9)));
  expect(h.row.textContent).toContain('ibkr/Live/4.3');
});
