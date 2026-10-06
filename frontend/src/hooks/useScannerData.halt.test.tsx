// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useScannerData } from './useScannerData';
import type { ScannerRosterHandlers } from './useScannerPriceStream';

const stream = vi.hoisted(() => ({ handlers: null as ScannerRosterHandlers | null }));
vi.mock('./useScannerPriceStream', () => ({
  useScannerPriceStream: (handlers: ScannerRosterHandlers) => {
    stream.handlers = handlers;
    return { pricesStale: false, flashSymbols: {}, lastPriceTs: 0, rowQuoteTs: {}, subscriptionError: null };
  },
}));
vi.mock('../scanner/useScannerEnvelopePoll', () => ({ useScannerEnvelopePoll: () => {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('updates halt alone on a frozen served row and rejects queued live evidence after choosing history', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ dates: ['2026-09-23'],
    gappers: [{ symbol: 'PFSA', price: 4.3, halted: false }], gainers: [], losers: [],
    afterhours: [], large_cap: [], catalysts: [], table_state: 'frozen', last_scan: 100,
  }), { status: 200 })));
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const meta = result.current.tableMeta;
  const ages = result.current.scanAges;
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted: true }]));
  expect(result.current.gappers[0].halted).toBe(true);
  expect(result.current.gappers[0].price).toBe(4.3);
  expect(result.current.tableMeta).toBe(meta);
  expect(result.current.scanAges).toBe(ages);
  act(() => result.current.setHistoryDate('2026-09-23'));
  await waitFor(() => expect(result.current.gappers[0].halted).toBe(false));
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted: true }]));
  expect(result.current.gappers[0].halted).toBe(false);
});
