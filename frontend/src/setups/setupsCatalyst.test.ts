import { describe, expect, it } from 'vitest';
import { catalystTitle } from './setupsFormat';
import type { SetupCatalyst } from './types';

const base: SetupCatalyst = {
  verdict: 'catalyst', category: 'fda_regulatory', strength: 'strong', title: 'Acme Receives FDA Approval',
  source: 'alpaca', published_ts: 1, url: null, negative_too: false, rules_version: 'v1',
};
const pillars = (catalyst: SetupCatalyst | null) => ({
  price: 4, change_pct: 40, rvol: 9, float: 5e6, news: catalyst ? catalyst.verdict === 'catalyst' : null,
  headline: catalyst?.title ?? null, catalyst,
});

describe('catalystTitle', () => {
  it('names the class, strength and headline a News pass rested on', () => {
    expect(catalystTitle(pillars(base))).toBe('Catalyst: FDA / regulatory (strong)\nAcme Receives FDA Approval');
  });

  it('flags dilution beside a catalyst', () => {
    expect(catalystTitle(pillars({ ...base, negative_too: true }))).toContain('offering / dilution');
  });

  it('says a movers list is no catalyst, and an unread moment is unknown rather than failed', () => {
    expect(catalystTitle(pillars({ ...base, verdict: 'noise_only', category: 'movers_list', strength: null })))
      .toBe('Only movers lists, law firms or opinion -- no catalyst');
    expect(catalystTitle(pillars(null))).toContain('unknown, not a fail');
  });
});
