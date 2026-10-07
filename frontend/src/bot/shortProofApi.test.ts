/**
 * `GET /api/short-proof` read on arrival (ADR 048 step 6): an unknown shape is an error, never a proof that
 * reads done, and a step's `ok` is done only when it is exactly true.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BOTS_PROOF_OLD_BACKEND } from '../constantGroups/bots_page';
import { fetchShortProof, parseShortProof } from './shortProofApi';
import { shortProofView } from './shortProofFixtures';

afterEach(() => vi.unstubAllGlobals());

describe('parseShortProof', () => {
  it('reads the backend\'s view, the steps in order', () => {
    const view = parseShortProof(shortProofView());
    expect(view?.complete).toBe(false);
    expect(view?.done).toBe(0);
    expect(view?.total).toBe(7);
    expect(view?.steps.map(s => s.id)).toEqual(['margin_account', 'practice_reset', 'short_tests', 'paper_days',
      'drill_freeze', 'drill_flatten', 'drill_day_cover', 'drill_gateway_drop', 'live_key']);
    expect(view?.steps[3].seen).toBe('operator');
    expect(view?.days).toEqual([{ date: '2026-10-07', shorts: 2, symbols: ['RDYN'] }]);
    expect(view?.review.open).toBe(false);
  });

  it('refuses another version, a missing step list, or a step it cannot name', () => {
    expect(parseShortProof(shortProofView({ schema_version: 2 }))).toBeNull();
    expect(parseShortProof(shortProofView({ steps: undefined }))).toBeNull();
    expect(parseShortProof(shortProofView({ steps: [{ label: 'no id' }] }))).toBeNull();
    expect(parseShortProof(null)).toBeNull();
    expect(parseShortProof([])).toBeNull();
  });

  it('never reads a step as done unless it says true, nor the proof as complete', () => {
    const view = parseShortProof(shortProofView({
      complete: 'yes',
      steps: [{ id: 'drill_freeze', label: 'Freeze', ok: 'true' }, { id: 'live_key', label: 'Key', ok: 1 }],
    }));
    expect(view?.complete).toBe(false);
    expect(view?.steps.map(s => s.ok)).toEqual([null, null]);
  });
});

describe('fetchShortProof', () => {
  const answer = (status: number, body: unknown) =>
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: status < 400, status, json: async () => body })));

  it('says an old backend has no proof yet', async () => {
    answer(404, { detail: 'Not Found' });
    await expect(fetchShortProof()).rejects.toThrow(BOTS_PROOF_OLD_BACKEND);
  });

  it('turns a refusal or a shape it does not read into an error', async () => {
    answer(503, {});
    await expect(fetchShortProof()).rejects.toThrow('answered 503');
    answer(200, { schema_version: 9 });
    await expect(fetchShortProof()).rejects.toThrow('shape this desk does not read');
  });

  it('answers the view', async () => {
    answer(200, shortProofView({ done: 2 }));
    expect((await fetchShortProof()).done).toBe(2);
  });
});
