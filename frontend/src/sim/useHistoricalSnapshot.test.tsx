/** @vitest-environment jsdom */
import { StrictMode, type ReactNode } from 'react';
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useHistoricalSnapshot } from './useHistoricalSnapshot';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
const mocks=vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock('../api/novaFetch',()=>({novaFetch:mocks.fetch}));
vi.mock('../ibkr/useIbkrStatus',()=>({useIbkrStatus:()=>({mode:'sim'})}));
afterEach(()=>{cleanup();mocks.fetch.mockReset();vi.useRealTimers();});
it('clears future quote and tape immediately on rewind, then shows errors',async()=>{
  mocks.fetch.mockResolvedValueOnce({ok:true,json:async()=>({active:true,symbol:'IMCC',last:99,volume:900,prints:[{price:99}]})});
  const {result}=renderHook(()=>useHistoricalSnapshot('IMCC',true));
  await act(async()=>{});
  expect(result.current?.last).toBe(99);
  let reject: (reason: Error)=>void=()=>{};
  mocks.fetch.mockImplementationOnce(()=>new Promise((_resolve, fail)=>{reject=fail;}));
  act(()=>window.dispatchEvent(new Event(SIM_CLOCK_SCRUB_EVENT)));
  expect(result.current?.active).toBe(true);
  expect(result.current?.last).toBeNull();
  expect(result.current?.prints).toEqual([]);
  await act(async()=>reject(new Error('offline')));
  expect(result.current?.error).toContain('offline');
  expect(result.current?.last).toBeNull();
});
it('leaves synthetic SIM rendering available when no historical selection exists',async()=>{
 mocks.fetch.mockResolvedValue({ok:true,json:async()=>({active:false})});
 const {result}=renderHook(()=>useHistoricalSnapshot('SIM1',true));
 await act(async()=>{});
 expect(result.current).toBeNull();
});

it('never replaces synthetic SIM panels while no historical selection is known', async () => {
  mocks.fetch.mockRejectedValueOnce(new Error('404 old backend'));
  const { result } = renderHook(() => useHistoricalSnapshot('SIM1', true));
  expect(result.current).toBeNull();
  await act(async () => {});
  expect(result.current).toBeNull();  // an error without a selection stays out of the way
  mocks.fetch.mockImplementation(() => new Promise(() => {}));
  act(() => window.dispatchEvent(new Event(SIM_CLOCK_SCRUB_EVENT)));
  expect(result.current).toBeNull();  // no loading flash on a seek
});

it('switching tickers never shows the previous ticker tape', async () => {
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ active: true, symbol: 'IMCC', last: 2, volume: 5, prints: [{ price: 2 }] }) });
  const { result, rerender } = renderHook(({ symbol }) => useHistoricalSnapshot(symbol, true), { initialProps: { symbol: 'IMCC' } });
  await act(async () => {});
  expect(result.current?.prints).toHaveLength(1);
  mocks.fetch.mockImplementation(() => new Promise(() => {}));
  rerender({ symbol: 'SPY' });
  expect(result.current).toBeNull(); // A different tab must keep its ordinary surface.
});

it('shares one slow request across consumers and cancels on the final unsubscribe', async () => {
  vi.useFakeTimers();
  const signals: AbortSignal[] = [];
  mocks.fetch.mockImplementation((_url: string, init: RequestInit) => {
    signals.push(init.signal as AbortSignal);
    return new Promise(() => {});
  });
  const first = renderHook(() => useHistoricalSnapshot('IMCC', true));
  const second = renderHook(() => useHistoricalSnapshot('IMCC', true));
  await act(async () => vi.advanceTimersByTimeAsync(4000));
  expect(mocks.fetch).toHaveBeenCalledTimes(1);
  first.unmount(); expect(signals[0].aborted).toBe(false);
  second.unmount(); expect(signals[0].aborted).toBe(true);
});
it('retains reached data on a failed poll but clears it immediately on seek', async () => {
  vi.useFakeTimers();
  mocks.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ active: true, symbol: 'IMCC', last: 2, prints: [{ price: 2 }] }) });
  const { result } = renderHook(() => useHistoricalSnapshot('IMCC', true));
  await act(async () => {});
  mocks.fetch.mockRejectedValue(new Error('offline'));
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(result.current?.last).toBe(2); expect(result.current?.prints).toHaveLength(1);
  expect(result.current?.error).toBe('offline');
  act(() => window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT, { detail: { symbol: 'SPY', minute: 1 } })));
  expect(result.current?.last).toBe(2);
  act(() => window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT, { detail: { symbol: 'IMCC', minute: 1 } })));
  expect(result.current?.last).toBeNull(); expect(result.current?.prints).toEqual([]);
});
it('StrictMode subscribers keep one shared resource after effect replay and remount', async () => {
  vi.useFakeTimers();
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ active: true, symbol: 'IMCC', last: 2, prints: [] }) });
  const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;
  const first = renderHook(() => useHistoricalSnapshot('IMCC', true), { wrapper });
  await act(async () => {});
  const second = renderHook(() => useHistoricalSnapshot('IMCC', true), { wrapper });
  await act(async () => {});
  const initial = mocks.fetch.mock.calls.length;
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(mocks.fetch.mock.calls.length - initial).toBe(1);
  expect(first.result.current?.last).toBe(2); expect(second.result.current?.last).toBe(2);
  second.unmount();
  const third = renderHook(() => useHistoricalSnapshot('IMCC', true), { wrapper });
  const before = mocks.fetch.mock.calls.length;
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(mocks.fetch.mock.calls.length - before).toBe(1);
  expect(third.result.current?.last).toBe(2);
});
it('rejects a mismatched selection instead of rendering an empty historical card', async () => {
  mocks.fetch.mockResolvedValue({ ok: true, json: async () => ({ active: true, symbol: 'SPY', selection: { symbol: 'IMCC' }, prints: [] }) });
  const { result } = renderHook(() => useHistoricalSnapshot('SPY', true));
  await act(async () => {}); expect(result.current).toBeNull();
});
