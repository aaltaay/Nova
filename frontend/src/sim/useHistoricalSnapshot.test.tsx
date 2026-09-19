/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useHistoricalSnapshot } from './useHistoricalSnapshot';
import { SIM_CLOCK_SCRUB_EVENT } from './simClockEvents';
const mocks=vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock('../api/novaFetch',()=>({novaFetch:mocks.fetch}));
vi.mock('../ibkr/useIbkrStatus',()=>({useIbkrStatus:()=>({mode:'sim'})}));
afterEach(()=>{cleanup();mocks.fetch.mockReset();});
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
  expect(result.current?.symbol).toBe('SPY');
  expect(result.current?.prints).toEqual([]);
});
