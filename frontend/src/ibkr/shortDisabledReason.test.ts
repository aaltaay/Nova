/**
 * The ticket's Short lock (ADR 009, ADR 048): Paper and Sim short with no Live key; Live needs
 * IBKR_SHORT_ENABLED, then the Live short proof (step 6), then a fresh, shortable listing. A proof the status
 * does not carry, or could not read, is not known -- never complete.
 */
import { describe, expect, it } from 'vitest';
import {
  SHORTABILITY_NO_BORROW,
  SHORTABILITY_NOT_SHORTABLE,
  SHORTABILITY_SHORT_DISABLED,
  SHORTABILITY_STALE,
} from '../constantGroups/shortability';
import { shortDisabledReason } from './shortDisabledReason';
import type { IbkrListingFlags } from '../types/ticker';

const listing: IbkrListingFlags = { source: 'ibkr', state: 'shortable_est', stale: false, orderable: true };

describe('shortDisabledReason', () => {
  it('leaves Paper and Sim open with no Live key and no proof', () => {
    expect(shortDisabledReason(false, null, 'paper')).toBeNull();
    expect(shortDisabledReason(false, null, 'sim')).toBeNull();
  });

  it('locks Live while IBKR_SHORT_ENABLED is off, before anything else', () => {
    expect(shortDisabledReason(false, listing, 'live')).toBe(SHORTABILITY_SHORT_DISABLED);
  });

  it('opens Live with its explicit key and fresh borrow, without a proof', () => {
    expect(shortDisabledReason(true, listing, 'live')).toBeNull();
    expect(shortDisabledReason(true, null, 'live')).toBe(SHORTABILITY_NOT_SHORTABLE);
    expect(shortDisabledReason(true, { ...listing, stale: true }, 'live')).toBe(SHORTABILITY_STALE);
    expect(shortDisabledReason(true, { ...listing, state: 'thin' }, 'live')).toBe(SHORTABILITY_NOT_SHORTABLE);
  });

  it('greys Short on Paper and Live when IBKR has nothing to lend or needs a locate (BIYA, 2026-10-07)', () => {
    const borrow = (term: 'NSS' | 'LOCATE' | 'HTB' | 'UNKNOWN') => ({
      schema_version: 1 as const, term, chip: term, tone: 'bad' as const, text: `${term}: why`, source: 'live' as const,
      shares: null, level: 1, fee_rate: null, list: null, list_age_sec: null, list_note: null,
    });
    const nss = { ...listing, state: 'unknown', borrow: borrow('NSS') };
    expect(shortDisabledReason(false, nss, 'paper')).toBe(SHORTABILITY_NO_BORROW('NSS: why'));
    expect(shortDisabledReason(false, { ...nss, borrow: borrow('LOCATE') }, 'paper')).toBe(SHORTABILITY_NO_BORROW('LOCATE: why'));
    expect(shortDisabledReason(true, nss, 'live')).toBe(SHORTABILITY_NO_BORROW('NSS: why'));
    // Less certain words leave it pressable: the SHORT CHECK box says why the door would refuse.
    expect(shortDisabledReason(false, { ...nss, borrow: borrow('HTB') }, 'paper')).toBeNull();
    expect(shortDisabledReason(false, { ...nss, borrow: borrow('UNKNOWN') }, 'paper')).toBeNull();
    expect(shortDisabledReason(false, { ...nss, stale: true }, 'paper')).toBeNull();
    expect(shortDisabledReason(false, nss, 'sim')).toBeNull();
  });
});
