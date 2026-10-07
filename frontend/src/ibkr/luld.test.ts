import { describe, expect, it } from 'vitest';
import { luldMarkers, luldShows, luldStrip, luldTip, readLuldFrame, type LuldView } from './luld';

const NOW = 1_790_088_000; // epoch seconds

function view(patch: Partial<LuldView> = {}): LuldView {
  return {
    schema_version: 1,
    symbol: 'GRML',
    source: 'live',
    state: 'bands',
    exact: true,
    lower: 14.18,
    upper: 17.33,
    reference: 15.75,
    reference_since: NOW - 20,
    reference_source: 'reopen',
    reference_words: 'the reopening print',
    percent: '10%',
    prev_close: 10.85,
    tier: 2,
    tier_text: 'a $90M company: too small for the Russell 1000 (Tier 2)',
    tier_sure: true,
    spread: null,
    limit: null,
    straddle: null,
    anchor: { kind: 'reopen', ts: NOW - 20, price: 15.75 },
    halted_since: null,
    watching_since: NOW - 3600,
    warm_until: null,
    gap: null,
    last: 15.6,
    distance: { down_pct: -0.091, up_pct: 0.111 },
    near: null,
    reason: null,
    history: [],
    note: "Nova's calculation from the published Limit Up-Limit Down rules",
    rules: 'The reference is the average trade price of the last 5 minutes...',
    track: { source: 'Massive', measured: '2026-10-06', days: 10, touches: 600, exact: 500, within_1c: 540,
      text: 'matched the SIP to the cent on 83% of 600 band touches' },
    as_of: NOW,
    text: 'LULD 14.18 - 17.33',
    watching: true,
    ...patch,
  };
}

describe('readLuldFrame', () => {
  it('takes a version-1 view of the symbol only', () => {
    expect(readLuldFrame(view(), 'grml')?.upper).toBe(17.33);
    expect(readLuldFrame({ ...view(), schema_version: 2 }, 'GRML')).toBeNull();
    expect(readLuldFrame(view(), 'ABC')).toBeNull();
    expect(readLuldFrame(null, 'GRML')).toBeNull();
  });
});

describe('luldMarkers', () => {
  it('puts the lower band with the bids and the upper with the asks, whatever the book', () => {
    const m = luldMarkers(view());
    expect(m.bid.map(x => [x.id, x.price, x.label, x.rests, x.variant])).toEqual([['luld-lower', 14.18, 'LULD 14.18', 'bid', 'luld']]);
    expect(m.ask.map(x => [x.id, x.price, x.label])).toEqual([['luld-upper', 17.33, 'LULD 17.33']]);
  });

  it('marks an approximate band and lights the side the price is near or pinned on', () => {
    const m = luldMarkers(view({ exact: false, near: 'down' }));
    expect(m.bid[0].label).toBe('LULD ≈14.18');
    expect(m.bid[0].hot).toBe(true);
    expect(m.ask[0].hot).toBe(false);
    const lim = luldMarkers(view({ state: 'limit', limit: { side: 'up', since: NOW - 3, band: 17.33, pause_at: NOW + 12, overdue: false } }));
    expect(lim.ask[0].hot).toBe(true);
  });

  it('marks a band whose tier is Nova\'s assumption', () => {
    expect(luldMarkers(view({ tier_sure: false })).ask[0].label).toBe('LULD ≈17.33');
  });

  it('draws nothing while the bands are off, unknown or paused', () => {
    for (const state of ['off', 'unknown', 'warming', 'paused'] as const) {
      expect(luldMarkers(view({ state }))).toEqual({ bid: [], ask: [] });
      expect(luldShows(view({ state }))).toBe(false);
    }
  });
});

describe('luldStrip', () => {
  it('shows each band over its column with its distance', () => {
    const s = luldStrip(view(), NOW * 1000)!;
    expect(s.tone).toBe('calm');
    expect(s.bid).toEqual({ text: '▼ 14.18', pct: '−9.1%', near: false });
    expect(s.ask).toEqual({ text: '▲ 17.33', pct: '+11.1%', near: false });
  });

  it('counts a limit state down to the pause', () => {
    const s = luldStrip(view({ state: 'limit', limit: { side: 'down', since: NOW - 6, band: 14.18, pause_at: NOW + 9, overdue: false } }), NOW * 1000)!;
    expect(s.tone).toBe('limit');
    expect(s.center).toBe('LIMIT DOWN 14.18 · PAUSE IN 9s');
    expect(s.countdown).toBeCloseTo(0.6);
  });

  it('says a pause is due, a pause, and a warm-up', () => {
    expect(luldStrip(view({ state: 'pause_due', limit: { side: 'up', since: NOW - 16, band: 17.33, pause_at: NOW - 1, overdue: true } }), NOW * 1000)!.center)
      .toBe('PAUSE DUE · LIMIT UP 17.33');
    expect(luldStrip(view({ state: 'paused' }), NOW * 1000)!.tone).toBe('pause');
    expect(luldStrip(view({ state: 'warming', warm_until: NOW + 192 }), NOW * 1000)!.center).toBe('LULD in 3:12');
  });

  it('is gone outside the bands\' hours', () => {
    expect(luldStrip(view({ state: 'off' }), NOW * 1000)).toBeNull();
    expect(luldStrip(null, NOW * 1000)).toBeNull();
  });
});

describe('luldTip', () => {
  it('says whose bands they are, how Nova knows and the measured record', () => {
    const tip = luldTip(view());
    expect(tip).toContain('Reference 15.7500 -- the reopening print');
    expect(tip).toContain('Band 10% (previous close 10.85)');
    expect(tip).toContain("Nova's calculation");
    expect(tip).toContain('Measured: matched the SIP');
  });

  it('explains an approximate band', () => {
    expect(luldTip(view({ exact: false, spread: 0.17 }))).toContain('within 0.17 of theirs');
  });
});
