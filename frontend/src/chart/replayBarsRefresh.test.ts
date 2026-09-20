import { afterEach, expect, it, vi } from 'vitest';
import { clearBarsStoreForTests, ensureBars, getBarsEntry, setBars } from './barsStore';
import { invalidateReplayBars, subscribeReplayBarsRefresh } from './replayBarsRefresh';
import { SIM_CHART_REFRESH_MS } from '../sim/simClockEvents';
vi.mock('../ibkr/ibkrStatusPoller', () => ({getIbkrStatusSnapshot: () => ({mode: 'sim'})}));
afterEach(() => {clearBarsStoreForTests(); vi.unstubAllGlobals(); vi.useRealTimers();});
const reply = {ok: true, json: async () => ({bars: [], coverage: {replay: true}})} as Response;

it('chart and VWAP sharing a seek keep the replacement request instead of discarding it', async () => {
  const fetcher = vi.fn().mockResolvedValue(reply); vi.stubGlobal('fetch', fetcher);
  const event = new Event('seek');
  setBars('IMCC', '1Min', [{t:'2026-09-18T19:00:00Z',o:10,h:20,l:9,c:15,v:10}], {replay:true,filling:false,asOf:null,completeThrough:null});
  invalidateReplayBars(event, 'IMCC', '1Min');
  const chart = ensureBars('IMCC', '1Min');
  invalidateReplayBars(event, 'imcc', '1Min');
  const vwap = ensureBars('IMCC', '1Min');
  await expect(Promise.all([chart,vwap])).resolves.toEqual([[],[]]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(getBarsEntry('IMCC','1Min')?.bars).toEqual([]);
});

it('shares periodic reads and stops only after the last consumer leaves', async () => {
  vi.useFakeTimers(); const fetcher=vi.fn().mockResolvedValue(reply); vi.stubGlobal('fetch',fetcher);
  const a=subscribeReplayBarsRefresh('IMCC','1Min',()=>{void ensureBars('IMCC','1Min');});
  const b=subscribeReplayBarsRefresh('IMCC','1Min',()=>{void ensureBars('IMCC','1Min');});
  await vi.advanceTimersByTimeAsync(SIM_CHART_REFRESH_MS);
  expect(fetcher).toHaveBeenCalledTimes(1);
  a(); await vi.advanceTimersByTimeAsync(SIM_CHART_REFRESH_MS);
  expect(fetcher).toHaveBeenCalledTimes(2);
  b(); await vi.advanceTimersByTimeAsync(SIM_CHART_REFRESH_MS*2);
  expect(fetcher).toHaveBeenCalledTimes(2);
});
