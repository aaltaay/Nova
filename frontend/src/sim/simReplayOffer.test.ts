import { describe, expect, it } from 'vitest';
import {
  gatewayReachable, offerCopy, offerDateLabel, offerWindow, replayOffer, type ReplayOffer,
} from './simReplayOffer';
import { simTabOfferNotAnswering, simTabOfferNotAnsweringGaveUp } from './simConstants';
import type { HistoricalJob, HistoricalWindow } from './historicalTypes';

// Sunday 2026-09-20 22:00 ET -- Friday's 04:00-20:00 session is finished.
const SUNDAY = new Date('2026-09-21T02:00:00Z');
// Monday 2026-09-21 11:00 ET -- today's session is still open.
const MONDAY_MIDDAY = new Date('2026-09-21T15:00:00Z');

const W: HistoricalWindow = { symbol: 'IMCC', date: '2026-09-18', start: '09:15', end: '11:30' };
const job = (over: Partial<HistoricalJob> = {}): HistoricalJob => ({
  id: 'j', kind: 'trades', status: 'running', count: 0, pages: 0, error: null, ...W, ...over,
});

describe('offerWindow', () => {
  it('offers the date on the desk when that session has finished', () => {
    expect(offerWindow(' imcc ', { sim: true, session_date: '2026-09-18' }, { jobs: [], default_date: '2026-09-17' }, SUNDAY))
      .toEqual(W);
  });

  it('falls back to the panel default when the desk date is still trading', () => {
    // The backend refuses an unfinished window, so offering today would only fail.
    expect(offerWindow('IMCC', { sim: true, session_date: '2026-09-21' }, { jobs: [], default_date: '2026-09-18' }, MONDAY_MIDDAY))
      .toEqual(W);
  });

  it('bounds the one-click window to the open -- download cost is prints, not hours', () => {
    const window = offerWindow('IMCC', { sim: true, session_date: '2026-09-18' }, null, SUNDAY);
    expect(window).toMatchObject({ start: '09:15', end: '11:30' });
  });

  it('offers nothing rather than invent a date', () => {
    expect(offerWindow('IMCC', { sim: true }, { jobs: [] }, SUNDAY)).toBeNull();
    expect(offerWindow('IMCC', null, null, SUNDAY)).toBeNull();
  });
});

describe('offerWindow around the playhead (ADR 023)', () => {
  const at = (time: string, extra: Record<string, unknown> = {}) =>
    ({ sim: true, session_date: '2026-09-18', live_edge: false, sim_time_et: `2026-09-18T${time}:10-04:00`, ...extra });

  it('a board clicked at 07:42 offers a window that holds 07:42', () => {
    expect(offerWindow('GRML', at('07:42'), null, SUNDAY)).toEqual({ symbol: 'GRML', date: '2026-09-18', start: '07:15', end: '09:30' });
  });

  it('keeps the default window when the playhead is inside it, at the live edge, or unknown', () => {
    expect(offerWindow('GRML', at('10:05'), null, SUNDAY)).toMatchObject({ start: '09:15', end: '11:30' });
    expect(offerWindow('GRML', at('07:42', { live_edge: true }), null, SUNDAY)).toMatchObject({ start: '09:15', end: '11:30' });
    expect(offerWindow('GRML', { sim: true, session_date: '2026-09-18' }, null, SUNDAY)).toMatchObject({ start: '09:15' });
  });

  it('stays inside the 04:00-20:00 session', () => {
    expect(offerWindow('GRML', at('04:05'), null, SUNDAY)).toMatchObject({ start: '04:00', end: '06:15' });
    expect(offerWindow('GRML', at('19:50'), null, SUNDAY)).toMatchObject({ start: '17:45', end: '20:00' });
  });
});

describe('replayOffer', () => {
  it('offers Download when nothing exists for the window', () => {
    expect(replayOffer(W, [])).toEqual({ kind: 'download', window: W });
  });

  it('offers Load for a finished download, even while another job runs', () => {
    expect(replayOffer(W, [job({ status: 'complete' }), job({ id: 'spy', symbol: 'SPY' })]))
      .toEqual({ kind: 'ready', window: W });
  });

  it('reports progress for this window, not for a bars job of the same window', () => {
    expect(replayOffer(W, [job({ kind: 'bars', status: 'complete' })]).kind).toBe('download');
    expect(replayOffer(W, [job({ progress_pct: 42.4, eta_seconds: 180 })]))
      .toEqual({ kind: 'downloading', window: W, percent: 42.4, etaSeconds: 180, jobId: 'j', hasCoverage: false });
    expect(replayOffer(W, [job({ count: 1000 })])).toMatchObject({ kind: 'downloading', hasCoverage: true });
  });

  it('names the window holding the one download slot, instead of offering a doomed click', () => {
    expect(replayOffer(W, [job({ id: 'old', start: '04:00', end: '20:00' })])).toEqual({
      kind: 'busy', window: W, runningJobId: 'old',
      running: { symbol: 'IMCC', date: '2026-09-18', start: '04:00', end: '20:00' },
    });
  });

  it('treats stalled, paused, interrupted and queued as resumable -- not as progressing', () => {
    for (const over of [{ stale: true }, { status: 'paused' }, { status: 'interrupted' }, { status: 'queued' }]) {
      expect(replayOffer(W, [job({ progress_pct: 30, ...over })]).kind).toBe('stopped');
    }
  });

  it('surfaces a failed download with its reason and the retry throttle', () => {
    expect(replayOffer(W, [job({ status: 'failed', error: 'Ticker could not be uniquely qualified by IBKR', updated: 1000 })]))
      .toEqual({
        kind: 'failed', window: W, error: 'Ticker could not be uniquely qualified by IBKR',
        gatewayUnreachable: false, gatewayNotAnswering: false, retryAt: 1016, failedAt: 1000,
      });
  });

  it('dates a not-answering failure instead of claiming IBKR is silent now (V38)', () => {
    const t = {
      download: () => '', ready: () => '', downloading: () => '', stopped: () => '', failed: () => '',
      busy: () => '', gatewayDown: () => '', gatewayWaiting: () => '', retrying: () => '', duration: () => '',
      notAnswering: simTabOfferNotAnswering,
      notAnsweringGaveUp: simTabOfferNotAnsweringGaveUp,
    };
    const updated = Date.parse('2026-09-22T05:23:00Z') / 1000; // 01:23 ET
    const offer = replayOffer(W, [job({ status: 'failed', error: 'IBKR did not answer within 20s', updated })]);
    expect(offer).toMatchObject({ kind: 'failed', gatewayNotAnswering: true, failedAt: updated });
    const retrying = offerCopy({ ...offer, healing: true, attempt: 2, maxAttempts: 5 } as ReplayOffer, false, t).text;
    expect(retrying).toMatch(/^IBKR didn't answer IB Gateway at 01:23 -- retrying/);
    expect(retrying).not.toMatch(/isn't answering/);
    const gaveUp = offerCopy({ ...offer, healing: false, gaveUp: true } as ReplayOffer, false, t).text;
    expect(gaveUp).toMatch(/\(last try 01:23\), so IMCC .* hasn't downloaded/);
  });

  it('marks a Gateway-unreachable failure as one that heals by itself', () => {
    const refused = 'IB Gateway unreachable (4001: [WinError 1225] refused; 4002: [WinError 1225] refused)';
    const offer = replayOffer(W, [job({ status: 'failed', error: refused, updated: 1000 })]);
    expect(offer).toMatchObject({ kind: 'failed', gatewayUnreachable: true, retryAt: 1016 });
  });

  it('reads "Gateway took the connection but IBKR never answered" as its own, slower heal', () => {
    // Seen live: 4002 open, qualifyContracts silent for 45 s.
    const silent = 'IBKR did not answer within 45s while identifying REFR: IB Gateway accepted the connection';
    expect(replayOffer(W, [job({ status: 'failed', error: silent, updated: 1000 })])).toMatchObject({
      kind: 'failed', gatewayNotAnswering: true, gatewayUnreachable: false, retryAt: 1060,
    });
  });

  it('with both Gateway ports dark, offers to start Gateway instead of a doomed click', () => {
    expect(replayOffer(W, [], false)).toEqual({ kind: 'gateway-down', window: W });
    expect(replayOffer(W, [job({ status: 'failed', error: 'IB Gateway unreachable (x)' })], false).kind)
      .toBe('gateway-down');
    // Loading a finished download never needs Gateway.
    expect(replayOffer(W, [job({ status: 'complete' })], false).kind).toBe('ready');
  });

  it('matches the exact window only -- another date is a different download', () => {
    expect(replayOffer(W, [job({ date: '2026-09-17', status: 'complete' })]).kind).toBe('download');
  });
});

describe('gatewayReachable', () => {
  it('reads only the honest fields -- Sim overlays `connected`, not these', () => {
    expect(gatewayReachable({ connected: true, transport_connected: false,
      preferred_port_reachable: false, alternate_port_reachable: false })).toBe(false);
    expect(gatewayReachable({ transport_connected: false, preferred_port_reachable: false,
      alternate_port_reachable: true })).toBe(true);
    expect(gatewayReachable({ transport_connected: true })).toBe(true);
  });

  it('treats unknown as reachable -- never block a click on a guess', () => {
    expect(gatewayReachable({})).toBe(true);
    expect(gatewayReachable(null)).toBe(true);
  });
});

describe('offerCopy', () => {
  const t = {
    download: (l: string, i: boolean) => `dl ${l}${i ? ' instead' : ''}`,
    ready: (l: string) => `ready ${l}`,
    downloading: (l: string, p: string, c: boolean) => `downloading ${l}${p}${c ? ' loadable' : ''}`,
    stopped: (l: string, p: string) => `stopped ${l}${p}`,
    failed: (l: string, e: string) => `failed ${l} ${e}`,
    busy: (running: string) => `busy ${running}`,
    gatewayDown: (l: string) => `down ${l}`,
    notAnswering: (l: string, a: number, m: number) => `silent ${l} ${a}/${m}`,
    notAnsweringGaveUp: (l: string) => `gave up ${l}`,
    gatewayWaiting: (l: string) => `waiting ${l}`,
    retrying: (l: string) => `retrying ${l}`,
    duration: (s: number) => `${s}s`,
  };
  const at = (offer: ReplayOffer, instead = false) => offerCopy(offer, instead, t);

  it('always states the window, and gives each state at most one action', () => {
    expect(at({ kind: 'download', window: W })).toEqual({ text: 'dl IMCC · Fri, Sep 18 · 09:15–11:30 ET', action: 'download' });
    expect(at({ kind: 'download', window: W }, true).text).toContain('instead');
    expect(at({ kind: 'ready', window: W }).action).toBe('load');
    const running = { kind: 'downloading', window: W, percent: 42.4, etaSeconds: 90, jobId: 'j', hasCoverage: false } as const;
    expect(at(running)).toEqual({ text: 'downloading IMCC · Fri, Sep 18 · 09:15–11:30 ET -- 42%, about 90s left', action: 'stop' });
    expect(at({ ...running, hasCoverage: true }).action).toBe('load');
    expect(at({ kind: 'stopped', window: W, percent: 30 }).action).toBe('resume');
    const failed = { kind: 'failed', window: W, error: 'x', gatewayUnreachable: true, retryAt: null } as const;
    expect(at(failed).action).toBe('retry');
    expect(at({ ...failed, healing: true })).toMatchObject({ text: expect.stringContaining('retrying'), action: null });
    expect(at({ kind: 'gateway-down', window: W }).action).toBe('start-gateway');
    const silent = { ...failed, gatewayUnreachable: false, gatewayNotAnswering: true };
    expect(at({ ...silent, healing: true, attempt: 2, maxAttempts: 5 }))
      .toEqual({ text: 'silent IMCC · Fri, Sep 18 · 09:15–11:30 ET 2/5', action: 'reconnect' });
    expect(at({ ...silent, healing: false, gaveUp: true }))
      .toEqual({ text: 'gave up IMCC · Fri, Sep 18 · 09:15–11:30 ET', action: 'reconnect' });
    expect(at({ kind: 'gateway-down', window: W, waiting: true })).toMatchObject({ text: expect.stringContaining('waiting'), action: null });
    expect(at({ kind: 'busy', window: W, runningJobId: 'old', running: { ...W, start: '04:00', end: '20:00' } }))
      .toEqual({ text: 'busy IMCC · Fri, Sep 18 · 04:00–20:00 ET', action: 'stop-other' });
  });

  it('formats dates like the session bar', () => {
    expect(offerDateLabel('2026-09-18')).toBe('Fri, Sep 18');
    expect(offerDateLabel('not-a-date')).toBe('not-a-date');
  });
});
