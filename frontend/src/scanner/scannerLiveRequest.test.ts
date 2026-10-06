import type { SetStateAction } from 'react';
import { expect, it, vi } from 'vitest';
import { SCANNER_LIVE_REQUEST_HALT_MAX_SYMBOLS } from '../constantGroups/scanner_board';
import type { ScannerRow } from '../types/scanner';
import type { ScannerRestSink } from './scannerRestApply';
import { createScannerLiveRequestScope } from './scannerLiveRequest';

function harness() {
  let rows: ScannerRow[] = [{ symbol: 'PFSA', price: 4.3, halted: false }];
  const queued: SetStateAction<ScannerRow[]>[] = [];
  const meta = vi.fn();
  const sink: ScannerRestSink = {
    applyEnvelope: meta, setGappers: action => queued.push(action),
    setGainers: vi.fn(), setLosers: vi.fn(), setAfterhours: vi.fn(), setLargeCap: vi.fn(),
    setLastGood: vi.fn(), setTableMeta: vi.fn(), setScanAges: vi.fn(),
  };
  const scope = createScannerLiveRequestScope();
  scope.setView(null, 'ibkr', true);
  return { scope, sink, rows: () => rows, meta, queued,
    flush() { for (const action of queued.splice(0)) rows = typeof action === 'function' ? action(rows) : action; } };
}

it.each([true, false, null])('keeps a queued %s receipt snapshot after request disposal and changes only halt', halted => {
  const h = harness();
  const request = h.scope.begin(h.sink, new AbortController().signal);
  h.scope.recordHalt([{ symbol: 'pfsa', halted }, { symbol: 'EXTRA', halted: true }]);
  const incoming = [{ symbol: 'PFSA', price: 5, halted: halted === false, quote_ts: 10 },
    { symbol: 'OTHER', price: 6, halted: null }];
  request.sink.setGappers(() => incoming);
  request.finish();
  h.flush();
  expect(h.rows()).toEqual([{ ...incoming[0], halted }, incoming[1]]);
  expect(h.rows()[1]).toBe(incoming[1]);
  const fresh = h.scope.begin(h.sink, new AbortController().signal);
  fresh.sink.setGappers(incoming);
  fresh.finish();
  h.flush();
  expect(h.rows()).toBe(incoming);
});

it('uses the latest receipt and preserves roster order without admitting a patch-only symbol', () => {
  const h = harness();
  const request = h.scope.begin(h.sink, new AbortController().signal);
  h.scope.recordHalt([{ symbol: 'PFSA', halted: true }]);
  h.scope.recordHalt([{ symbol: 'PFSA', halted: null }, { symbol: 'EXTRA', halted: false }]);
  request.sink.setGappers([{ symbol: 'OTHER', halted: false }, { symbol: 'PFSA', halted: true }]);
  request.finish();
  h.flush();
  expect(h.rows()).toEqual([{ symbol: 'OTHER', halted: false }, { symbol: 'PFSA', halted: null }]);
});

it('fences already queued state through a history round trip and rejects old envelope writes', () => {
  const h = harness();
  const request = h.scope.begin(h.sink, new AbortController().signal);
  request.sink.setGappers([{ symbol: 'OLD', halted: true }]);
  const oldScope = h.scope.capture();
  h.scope.setView('2026-09-23', 'ibkr', true);
  h.scope.setView(null, 'ibkr', true);
  expect(h.scope.isScope(oldScope)).toBe(false);
  request.sink.applyEnvelope({ mode: 'old' });
  h.flush();
  expect(h.rows()[0].symbol).toBe('PFSA');
  expect(h.meta).not.toHaveBeenCalled();
  expect(request.isCurrent()).toBe(false);
});

it('invalidates queued writes on timeout, supersession and unmount', () => {
  const h = harness();
  for (const cause of ['timeout', 'supersession', 'unmount']) {
    const controller = new AbortController();
    const request = h.scope.begin(h.sink, controller.signal);
    request.sink.setGappers([{ symbol: cause, halted: true }]);
    if (cause === 'timeout') controller.abort();
    else if (cause === 'supersession') h.scope.begin(h.sink, new AbortController().signal).finish();
    else h.scope.invalidate();
    h.flush();
    expect(h.rows()[0].symbol).toBe('PFSA');
    expect(request.isCurrent()).toBe(cause === 'timeout');
    request.finish();
  }
});

it('rejects incomplete older snapshots when bounded receipt retention overflows, then permits a fresh request', () => {
  const h = harness();
  const request = h.scope.begin(h.sink, new AbortController().signal);
  const rows = Array.from({ length: SCANNER_LIVE_REQUEST_HALT_MAX_SYMBOLS }, (_, i) => ({ symbol: `S${i}`, halted: true }));
  h.scope.recordHalt(rows);
  h.scope.recordHalt([{ symbol: 'S0', halted: false }]);
  expect(request.overflowed()).toBe(false);
  request.sink.setGappers([{ symbol: 'OLD', halted: false }]);
  h.scope.recordHalt([{ symbol: 'OVERFLOW', halted: null }]);
  expect(request.overflowed()).toBe(true);
  request.sink.applyEnvelope({ mode: 'old' });
  request.finish();
  h.flush();
  expect(h.rows()[0].symbol).toBe('PFSA');
  expect(h.meta).not.toHaveBeenCalled();
  const fresh = h.scope.begin(h.sink, new AbortController().signal);
  fresh.sink.setGappers([{ symbol: 'FRESH', halted: null }]);
  fresh.finish();
  h.flush();
  expect(h.rows()[0].symbol).toBe('FRESH');
});
