import { describe, expect, it } from 'vitest';
import type { WhyCheck, WhyMovingRead, WhyStep } from '../types/whyMoving';
import { catalystFace } from './catalystCause';

const NOW = Date.parse('2026-10-12T20:49:00-04:00');

function check(id: string, state: WhyCheck['state'], value: string | null): WhyCheck {
  return { id, label: id, state, value, detail: null, source: 'test', as_of: null };
}

function read(kind: string, checks: WhyCheck[], opts: Partial<{ confidence: 'likely' | 'possible'; steps: WhyStep[];
  catalyst: WhyMovingRead['facts'] extends infer F ? F extends { catalyst: infer C } ? C : never : never }> = {}): WhyMovingRead {
  return {
    schema_version: 1, symbol: 'X', generated_at: NOW / 1000, rules_version: 'move-rules-v5', replay: false,
    likely: { kind, label: kind, detail: null, confidence: opts.confidence ?? 'likely', steps: opts.steps ?? [] },
    checks,
    facts: { board: 'gappers', priced_by: 'board_row', price: 2.59, change_pct: 2.047, last_trade: null,
      catalyst: opts.catalyst ?? null },
  };
}

const MNDR = [check('news', 'no', 'Only movers lists and market wraps'), check('float', 'yes', '398K? shares -- low float'),
  check('short_interest', 'no', '10% of float · 0.3 days to cover (Yahoo ratio)'), check('borrow', 'yes', 'Nothing to lend'),
  check('volume', 'yes', 'RVOL 242x'), check('reverse_split', 'no', '1-for-6, 106 days ago')];

describe('catalystFace', () => {
  it('names low-float momentum with its borrow, from the checks', () => {
    const face = catalystFace(read('low_float_momentum', MNDR), null, NOW);
    expect(face).toMatchObject({ mark: 'lowfloat', word: 'Low float', detail: 'no news · nothing to lend', possible: false });
  });

  it('a possible cause goes hollow and says so; unread news is said', () => {
    const face = catalystFace(read('low_float_momentum', MNDR, { confidence: 'possible' }), null, NOW);
    expect(face).toMatchObject({ word: 'Low float?', detail: 'news not read yet · nothing to lend', possible: true });
  });

  it('a squeeze names the share short and the borrow', () => {
    const checks = [check('short_interest', 'yes', '29% of float · under 0.1 days to cover (Yahoo ratio)'),
      check('borrow', 'yes', 'Fee 104.9%/yr · 2K shares to lend')];
    expect(catalystFace(read('short_squeeze', checks), null, NOW))
      .toMatchObject({ mark: 'squeeze', word: 'Squeeze', detail: '29% of float short · fee 104.9%/yr' });
  });

  it('news keeps the News column mark and says the class, strength and headline', () => {
    const catalyst = { verdict: 'catalyst' as const, category: 'contract_partnership', strength: 'weak' as const,
      title: 'Euro Tech Holdings Company Limited Announces a 50/50 Joint Venture', source: 'globenewswire',
      published_ts: NOW / 1000 - 14 * 3600, url: null, negative_too: false, rules_version: 'v9' };
    const steps: WhyStep[] = [{ kind: 'short_squeeze', name: 'Short squeeze', fits: true, why: '' }];
    const face = catalystFace(read('news', [], { catalyst, steps }), null, NOW);
    expect(face).toMatchObject({ mark: 'flame', ageClass: 'flame-cool', word: 'Contract', squeezePip: true });
    expect(face.detail).toBe('weak · Euro Tech Holdings Company Limited Announces a 50/50 Joint Venture');
    const unplaced = catalystFace(read('news', [], { catalyst: { ...catalyst, category: 'company_news' } }), null, NOW);
    expect(unplaced).toMatchObject({ mark: 'ring', word: 'Headline', squeezePip: false });
  });

  it('a dash for not moving and not read; reading while the read is in flight', () => {
    expect(catalystFace(read('not_moving', []), null, NOW).mark).toBe('none');
    expect(catalystFace(read('not_read', []), null, NOW).mark).toBe('none');
    expect(catalystFace(null, null, NOW, true).mark).toBe('reading');
    expect(catalystFace(null, null, NOW, false).mark).toBe('none');
  });

  it('a row with no price claims no cause: the news mark if there is news, else a dash', () => {
    const noPrice: WhyStep[] = [{ kind: 'move', name: 'A real move', fits: null, why: 'No price change on record' }];
    expect(catalystFace(read('unexplained', [], { steps: noPrice }), null, NOW)).toMatchObject({ mark: 'none', kind: 'no_price' });
    const catalyst = { verdict: 'catalyst' as const, category: 'merger_acquisition', strength: 'weak' as const, title: 'Vivakor Signs LOI',
      source: 'edgar', published_ts: NOW / 1000 - 3600, url: null, negative_too: false, rules_version: 'v9' };
    expect(catalystFace(read('unexplained', [], { steps: noPrice, catalyst }), null, NOW))
      .toMatchObject({ mark: 'flame', word: 'M&A', kind: 'news' });
  });

  it('thin and unexplained say what they rest on', () => {
    expect(catalystFace(read('thin_trading', [check('volume', 'no', 'RVOL 0.4x')]), null, NOW))
      .toMatchObject({ mark: 'thin', word: 'Thin', detail: 'RVOL 0.4x' });
    expect(catalystFace(read('unexplained', []), null, NOW))
      .toMatchObject({ mark: 'unexplained', word: 'Unexplained', detail: 'nothing on file explains it' });
  });
});
