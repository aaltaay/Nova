import { describe, expect, it, vi } from 'vitest';
import answerError from './__fixtures__/answer_error.json';
import answerNotEnoughBars from './__fixtures__/answer_not_enough_bars.json';
import answerNotSetUp from './__fixtures__/answer_not_set_up.json';
import answerOffline from './__fixtures__/answer_offline.json';
import answerPending from './__fixtures__/answer_pending.json';
import answerQuiet from './__fixtures__/answer_quiet.json';
import answerReady from './__fixtures__/answer_ready.json';
import answerWarming from './__fixtures__/answer_warming.json';
import statusNotConfigured from './__fixtures__/status_not_configured.json';
import statusReady from './__fixtures__/status_ready.json';
import { fetchAhead, fetchAheadStatus, normalizeAnswer, normalizeStatus } from './aheadApi';
import { AHEAD_WORDS } from './aheadConstants';

const novaFetch = vi.fn();
vi.mock('../api/novaFetch', () => ({ novaFetch: (...a: unknown[]) => novaFetch(...a) }));

const ANSWERS = {
  ready: answerReady, pending: answerPending, warming: answerWarming, quiet: answerQuiet, error: answerError,
  not_set_up: answerNotSetUp, offline: answerOffline, not_enough_bars: answerNotEnoughBars,
};

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
/** A fixture opened up for breaking one field at a time. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Raw = any;

function brokenReady(edit: (a: Raw) => void) {
  const a = clone(answerReady) as Raw;
  edit(a);
  return normalizeAnswer(a, 'XYZ');
}

describe('the forecast wire, read strictly', () => {
  it.each(Object.entries(ANSWERS))('reads the %s fixture as itself', (state, raw) => {
    const a = normalizeAnswer(raw, 'XYZ');
    expect(a.ai.state).toBe(state);
    expect(a).toEqual(raw);
  });

  it('carries no AI number on any state but ready', () => {
    for (const [state, raw] of Object.entries(ANSWERS)) {
      if (state === 'ready') continue;
      const a = normalizeAnswer(raw, 'XYZ');
      expect([a.ai.close, a.ai.volume, a.ai.paths, a.ai.levels, a.ai.volume_15, a.ai.range_15]).toEqual(
        [null, null, null, null, null, null],
      );
    }
  });

  it('turns a missing or bad field into an error that names it, with nothing filled in', () => {
    const missing = brokenReady((a) => delete a.ai.close);
    expect(missing.ai.state).toBe('error');
    expect(missing.ai.reason).toBe(AHEAD_WORDS.malformed('ai.close'));
    expect(missing.ai.close).toBeNull();
    expect(missing.ai.paths).toBeNull();
    expect(missing.price).toBeNull();
    expect(brokenReady((a) => { a.ai.levels = [0.05, 0.25, 0.5, 0.75, 0.95]; }).ai.reason).toContain('ai.levels');
    expect(brokenReady((a) => { a.ai.close[3] = [4.7, 4.6, 4.62, 4.65, 4.7]; }).ai.reason).toContain('ai.close[3]');
    expect(brokenReady((a) => { a.ai.close[0][0] = -1; }).ai.reason).toContain('ai.close[0]');
    expect(brokenReady((a) => { a.ai.volume[0][0] = -5; }).ai.reason).toContain('ai.volume[0]');
    expect(brokenReady((a) => { a.ai.paths.n = 8; }).ai.reason).toContain('ai.paths.n');
    expect(brokenReady((a) => { a.ai.paths.close[2].pop(); }).ai.reason).toContain('ai.paths.close[2]');
    expect(brokenReady((a) => { a.ai.paths.close[1][4] = 0; }).ai.reason).toContain('ai.paths.close[1][4]');
    expect(brokenReady((a) => { a.ai.range_15 = [0.04, 0.03, 0.02, 0.01, 0.0]; }).ai.reason).toContain('ai.range_15');
    expect(brokenReady((a) => { a.ai.exam_passed = 'yes'; }).ai.reason).toContain('ai.exam_passed');
    expect(brokenReady((a) => { a.ai.exam.volume.baseline.name = 3; }).ai.reason).toContain('ai.exam.volume.baseline.name');
    expect(brokenReady((a) => { a.venue = 'cloud'; }).ai.reason).toContain('venue');
    expect(brokenReady((a) => { a.as_of = a.bar_t + 120; }).ai.reason).toContain('as_of');
    expect(brokenReady((a) => { a.generated_at = a.as_of - 1; }).ai.reason).toContain('generated_at');
    expect(brokenReady((a) => { a.schema_version = 2; }).ai.reason).toContain('schema_version');
    expect(brokenReady((a) => { a.ai.horizon_min = 10; }).ai.reason).toContain('ai.horizon_min');
  });

  it('refuses a non-ready answer that carries AI numbers', () => {
    const raw = clone(answerPending) as Raw;
    raw.ai.close = clone(answerReady.ai.close);
    const a = normalizeAnswer(raw, 'XYZ');
    expect(a.ai.state).toBe('error');
    expect(a.ai.reason).toContain('ai.close');
  });

  it('refuses an answer for another symbol, and a body that is not an object', () => {
    expect(normalizeAnswer(answerReady, 'ABC').ai.reason).toContain('symbol');
    expect(normalizeAnswer('nope', 'XYZ').ai.state).toBe('error');
    expect(normalizeAnswer(undefined, 'XYZ').symbol).toBe('XYZ');
  });

  it('reads an exam without a scope as a stated null', () => {
    const raw = clone(answerReady) as Raw;
    delete raw.ai.exam.scope;
    expect(normalizeAnswer(raw, 'XYZ').ai.exam?.scope).toBeNull();
  });
});

describe('the status wire', () => {
  it('reads both fixtures as themselves', () => {
    expect(normalizeStatus(statusReady)).toEqual(statusReady);
    expect(normalizeStatus(statusNotConfigured)).toEqual(statusNotConfigured);
  });

  it('names a bad field', () => {
    const raw = clone(statusReady) as Raw;
    raw.health.live.scored = null;
    expect(normalizeStatus(raw)).toEqual({ problem: AHEAD_WORDS.malformed('health.live.scored') });
  });
});

describe('asking Nova for Ahead', () => {
  const signal = () => new AbortController().signal;

  it('asks the forecast route for the symbol', async () => {
    novaFetch.mockResolvedValueOnce(new Response(JSON.stringify(answerReady)));
    const res = await fetchAhead('XYZ', signal());
    expect(String(novaFetch.mock.calls.at(-1)?.[0])).toContain('/api/ahead/forecast/XYZ');
    expect(res.problem).toBeNull();
    expect(res.answer?.ai.state).toBe('ready');
  });

  it('says the API needs a restart on a 404 and that it could not reach it on a network failure', async () => {
    novaFetch.mockResolvedValueOnce(new Response('{}', { status: 404 }));
    expect(await fetchAhead('XYZ', signal())).toEqual({ answer: null, problem: AHEAD_WORDS.apiMissing });
    novaFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(await fetchAhead('XYZ', signal())).toEqual({ answer: null, problem: AHEAD_WORDS.apiUnreachable });
    novaFetch.mockResolvedValueOnce(new Response('{}', { status: 422 }));
    expect((await fetchAhead('X!', signal())).problem).toBe(AHEAD_WORDS.apiStatus(422));
    warn.mockRestore();
  });

  it('rejects only when the caller aborted', async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    novaFetch.mockRejectedValueOnce(new DOMException('aborted', 'AbortError'));
    await expect(fetchAhead('XYZ', ctrl.signal)).rejects.toThrow();
  });

  it('reads a body that is not JSON as an error answer', async () => {
    novaFetch.mockResolvedValueOnce(new Response('<html>'));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const res = await fetchAhead('XYZ', signal());
    expect(res.answer?.ai.state).toBe('error');
    warn.mockRestore();
  });

  it('reads the status route', async () => {
    novaFetch.mockResolvedValueOnce(new Response(JSON.stringify(statusReady)));
    const res = await fetchAheadStatus(signal());
    expect(String(novaFetch.mock.calls.at(-1)?.[0])).toContain('/api/ahead/status');
    expect(res.status?.health?.live.range_spearman).toBeNull();
  });
});
