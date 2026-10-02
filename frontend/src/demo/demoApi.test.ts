/**
 * The demo's backend (ADR 043): what it answers, what it refuses, and the venue it keeps.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { DEMO_REFUSAL, answer, demoVenue, resetDemoState, type DemoResponse } from './demoApi';
import { NOW_S } from './data/market';

const get = (path: string, query = '') => answer({ method: 'GET', path, query: new URLSearchParams(query), body: null }, NOW_S + 30);
const send = (method: string, path: string, body: unknown = null) => answer({ method, path, query: new URLSearchParams(), body });
const bodyOf = <T>(res: DemoResponse | undefined) => res?.body as T;

afterEach(() => resetDemoState());

describe('demo backend reads', () => {
  it('reports a connected desk on Paper', () => {
    expect(bodyOf<{ status: string }>(get('/api/health')).status).toBe('connected');
    const status = bodyOf<{ venue: string; account_id: string; armed: boolean }>(get('/api/ibkr/status'));
    expect(status).toMatchObject({ venue: 'paper', account_id: 'NOVA-PAPER', armed: true });
  });

  it('keeps the scanner fresh by the clock it is given', () => {
    const env = bodyOf<{ gappers: { symbol: string }[]; last_scan: number }>(get('/api/gappers'));
    expect(env.gappers[0].symbol).toBe('SMPL');
    expect(env.last_scan).toBe(NOW_S + 29);
  });

  it("reads each symbol's own numbers", () => {
    const read = bodyOf<{ symbol: string; plan: unknown; groups: { id: string; value: string }[] }>(get('/api/stock-read/GAPX'));
    expect(read.symbol).toBe('GAPX');
    expect(read.plan).toBeNull();
    expect(read.groups.find((g) => g.id === 'float')?.value).toBe('1.8M');
    const smpl = bodyOf<{ plan: { entry: number; stop: number; target: number } }>(get('/api/stock-read/SMPL'));
    expect(smpl.plan).toMatchObject({ entry: 4.39, stop: 4.12, target: 4.93 });
  });

  it('answers nothing it does not know', () => {
    expect(get('/api/no-such-route')).toBeUndefined();
    expect(get('/api/sim/clock')).toBeUndefined(); // only on Sim
  });
});

describe('demo backend writes', () => {
  it('refuses an order, an arm and a setting with the demo reason', () => {
    for (const [method, path] of [['POST', '/api/ibkr/order'], ['POST', '/api/ibkr/arm'], ['PATCH', '/api/bot/session'], ['DELETE', '/api/ibkr/order/7009']]) {
      const res = send(method, path, { symbol: 'SMPL' });
      expect(res?.status).toBe(403);
      expect(bodyOf<{ detail: string }>(res).detail).toBe(DEMO_REFUSAL);
    }
  });

  it("takes the desk's own background reports and keeps nothing", () => {
    for (const path of ['/api/perf/client', '/sensors/focus', '/api/client-errors']) {
      expect(send('POST', path, {})?.status).toBe(200);
    }
  });

  it('switches between Paper and Sim, and never to Live', () => {
    expect(send('POST', '/api/desk/venue', { venue: 'live' })?.status).toBe(409);
    expect(demoVenue()).toBe('paper');
    expect(send('POST', '/api/desk/venue', { venue: 'sim' })?.status).toBe(200);
    expect(bodyOf<{ venue: string }>(get('/api/ibkr/status')).venue).toBe('sim');
    expect(bodyOf<{ replay_symbol: string }>(get('/api/sim/clock')).replay_symbol).toBe('RUNR');
  });

  it("gives Sim the replay's candles, marked as the replay's", () => {
    send('POST', '/api/desk/venue', { venue: 'sim' });
    const runr = bodyOf<{ bars: { c: number }[]; coverage: { replay: boolean } }>(get('/api/ticker/RUNR/bars', 'timeframe=1Min'));
    expect(runr.coverage.replay).toBe(true);
    expect(runr.bars.at(-1)?.c).toBe(5.12);
    expect(bodyOf<{ bars: unknown[] }>(get('/api/ticker/SMPL/bars', 'timeframe=1Min')).bars).toEqual([]);
  });
});
