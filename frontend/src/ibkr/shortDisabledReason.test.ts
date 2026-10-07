/**
 * The ticket's Short lock (ADR 009, ADR 048): Paper and Sim short with no Live key; Live needs
 * IBKR_SHORT_ENABLED, then the Live short proof (step 6), then a fresh, shortable listing. A proof the status
 * does not carry, or could not read, is not known -- never complete.
 */
import { describe, expect, it } from 'vitest';
import {
  SHORTABILITY_NOT_SHORTABLE,
  SHORTABILITY_PROOF_INCOMPLETE,
  SHORTABILITY_PROOF_UNKNOWN,
  SHORTABILITY_SHORT_DISABLED,
  SHORTABILITY_STALE,
} from '../constantGroups/shortability';
import { shortDisabledReason } from './shortDisabledReason';
import type { IbkrListingFlags } from '../types/ticker';

const listing: IbkrListingFlags = { source: 'ibkr', state: 'shortable_est', stale: false, orderable: true };
const complete = { complete: true, done: 7, total: 7, error: null };

describe('shortDisabledReason', () => {
  it('leaves Paper and Sim open with no Live key and no proof', () => {
    expect(shortDisabledReason(false, null, 'paper', null)).toBeNull();
    expect(shortDisabledReason(false, null, 'sim', undefined)).toBeNull();
  });

  it('locks Live while IBKR_SHORT_ENABLED is off, before anything else', () => {
    expect(shortDisabledReason(false, listing, 'live', complete)).toBe(SHORTABILITY_SHORT_DISABLED);
  });

  it('reads a proof the status does not carry, or could not read, as not known', () => {
    expect(shortDisabledReason(true, listing, 'live', undefined)).toBe(SHORTABILITY_PROOF_UNKNOWN);
    expect(shortDisabledReason(true, listing, 'live', null)).toBe(SHORTABILITY_PROOF_UNKNOWN);
    expect(shortDisabledReason(true, listing, 'live', { complete: true, done: 7, total: 7, error: 'disk' }))
      .toBe(SHORTABILITY_PROOF_UNKNOWN);
  });

  it('locks Live while the proof is incomplete, and counts what is done', () => {
    const why = shortDisabledReason(true, listing, 'live', { complete: false, done: 3, total: 7, error: null });
    expect(why).toBe(SHORTABILITY_PROOF_INCOMPLETE(3, 7));
    expect(why).toContain('(3 of 7 days and drills)');
  });

  it('opens Live only with the proof complete and a fresh, shortable listing', () => {
    expect(shortDisabledReason(true, listing, 'live', complete)).toBeNull();
    expect(shortDisabledReason(true, null, 'live', complete)).toBe(SHORTABILITY_NOT_SHORTABLE);
    expect(shortDisabledReason(true, { ...listing, stale: true }, 'live', complete)).toBe(SHORTABILITY_STALE);
    expect(shortDisabledReason(true, { ...listing, state: 'thin' }, 'live', complete)).toBe(SHORTABILITY_NOT_SHORTABLE);
  });
});
