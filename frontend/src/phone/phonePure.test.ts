import { describe, expect, it } from 'vitest';
import type { CatalystVerdict } from '../types/catalystVerdict';
import type { CatalystFace } from '../utils/catalystCause';
import type { LossLimitView } from '../loss_limit/lossLimitApi';
import { catalystLine, phoneCatalyst } from './phoneCatalyst';
import { LANDSCAPE, PORTRAIT, fitFor } from './phoneFit';
import { agoShort, compact, pct1, px, rvolShort, shares, signedMoney, toneOf } from './phoneFormat';
import { cleanSymbol, parseRoute, routeHash, tabOf } from './phoneRoute';
import { lossLimitFor } from './usePhoneLossLimit';
import { rowsThatFit } from './useRowsThatFit';

describe('where the phone is', () => {
  it('names every screen in the hash and reads it back', () => {
    for (const route of [
      { screen: 'home' }, { screen: 'scan' }, { screen: 'top9' }, { screen: 'account' }, { screen: 'settings' },
      { screen: 'trade', symbol: null }, { screen: 'trade', symbol: 'ABCD' },
      { screen: 'stock', symbol: 'BRK.B' }, { screen: 'chart', symbol: 'ABCD' },
    ] as const) {
      expect(parseRoute(routeHash(route))).toEqual(route);
    }
    expect(routeHash({ screen: 'stock', symbol: 'ABCD' })).toBe('#/stock/ABCD');
  });

  it('opens Home on a hash it does not know, never a blank page', () => {
    expect(parseRoute('')).toEqual({ screen: 'home' });
    expect(parseRoute('#/nowhere')).toEqual({ screen: 'home' });
    // A stock page with no stock, or with something that is not a ticker.
    expect(parseRoute('#/stock')).toEqual({ screen: 'home' });
    expect(parseRoute('#/chart/%3Cscript%3E')).toEqual({ screen: 'home' });
    expect(parseRoute('#/trade/not a ticker')).toEqual({ screen: 'trade', symbol: null });
  });

  it('writes a ticker as the desk does', () => {
    expect(cleanSymbol(' abcd ')).toBe('ABCD');
    expect(cleanSymbol('')).toBeNull();
    expect(cleanSymbol('TOOLONGTOBEATICKER')).toBeNull();
  });

  it('lights a bottom-bar tab only for a screen the bar reaches', () => {
    expect(tabOf({ screen: 'top9' })).toBe('top9');
    expect(tabOf({ screen: 'trade', symbol: 'ABCD' })).toBe('trade');
    expect(tabOf({ screen: 'stock', symbol: 'ABCD' })).toBeNull();
    expect(tabOf({ screen: 'settings' })).toBeNull();
  });
});

describe('a number in a narrow column', () => {
  it('drops the dollar sign from a price and keeps the sub-penny digits', () => {
    expect(px(4.82)).toBe('4.82');
    expect(px(0.6999)).toBe('0.6999');
    expect(px(1204.5)).toBe('1,204.50');
    expect(px(null)).toBe('—');
  });

  it('writes a percent with one decimal and no sign on a flat move', () => {
    expect(pct1(0.382)).toBe('+38.2%');
    expect(pct1(-0.0241)).toBe('-2.4%');
    expect(pct1(0.0003)).toBe('0.0%');
    expect(pct1(-0.0003)).toBe('0.0%');
    expect(pct1(8.115)).toBe('+811.5%');
    expect(pct1(125)).toBe('+12,500%');
    expect(pct1(null)).toBe('—');
  });

  it('holds a count to five characters, and never writes 1000 of a unit', () => {
    expect(compact(876_100)).toBe('876K');
    expect(compact(5_000_000)).toBe('5.0M');
    expect(compact(26_300_000)).toBe('26.3M');
    expect(compact(194_500_000)).toBe('195M');
    expect(compact(999_960)).toBe('1.0M');
    expect(compact(999_600_000)).toBe('1.0B');
    expect(compact(1_230_000_000)).toBe('1.2B');
    expect(compact(950)).toBe('950');
    expect(compact(null)).toBe('—');
  });

  it('never shows a missing fact as zero', () => {
    expect(signedMoney(null)).toBe('—');
    expect(shares(undefined)).toBe('—');
    expect(rvolShort(null)).toBe('');
  });

  it('signs profit and loss, and leaves a flat figure plain', () => {
    expect(signedMoney(412.6)).toBe('+$412.60');
    expect(signedMoney(-5)).toBe('-$5.00');
    expect(signedMoney(0)).toBe('$0.00');
    expect(signedMoney(-0.004)).toBe('$0.00');
    expect(toneOf(0.004)).toBe('');
    expect(toneOf(1)).toBe('good');
    expect(toneOf(-1)).toBe('bad');
  });

  it('writes relative volume and an age short', () => {
    expect(rvolShort(14.24)).toBe('14.2x');
    expect(rvolShort(3.61)).toBe('3.61x');
    expect(rvolShort(150.2)).toBe('150x');
    expect(rvolShort(0.001)).toBe('<0.01x');
    expect(agoShort(20_000)).toBe('now');
    expect(agoShort(9 * 60_000)).toBe('9m ago');
    expect(agoShort(2 * 3_600_000)).toBe('2 h ago');
    expect(agoShort(49 * 3_600_000)).toBe('2 d ago');
    // A clock that runs behind the news never writes a negative age.
    expect(agoShort(-5_000)).toBe('now');
  });
});

const NOW = 1_794_400_000_000;
const face = (over: Partial<CatalystFace>): CatalystFace => ({
  mark: 'none', ageClass: null, word: '', detail: null, possible: false, squeezePip: false, kind: 'none', ...over,
});
const verdict = (over: Partial<CatalystVerdict>): CatalystVerdict => ({
  verdict: 'catalyst', category: 'company_news', strength: 'strong', title: 'A headline', source: 'globenewswire',
  published_ts: NOW / 1000 - 9 * 60, url: 'https://example.test/a', negative_too: false, rules_version: 'v8', ...over,
});

describe("the desk's Catalyst call in two short lines", () => {
  it("keeps the desk's word and puts the news' age under it", () => {
    const c = phoneCatalyst({ face: face({ mark: 'flame', word: 'News', detail: 'strong · A headline', kind: 'news' }), verdict: verdict({}), halted: false, nowMs: NOW });
    expect(c).toMatchObject({ word: 'News', when: '9m ago', tone: 'news', headline: 'A headline', url: 'https://example.test/a' });
    expect(catalystLine(c)).toBe('News · 9m ago');
  });

  it('reads the release headline out of an EDGAR title', () => {
    const c = phoneCatalyst({
      face: face({ mark: 'flame', word: 'Offering', kind: 'news' }),
      verdict: verdict({ source: 'edgar', title: '8-K: 1.01, 3.02 | Company prices a registered direct offering' }),
      halted: false, nowMs: NOW,
    });
    expect(c.headline).toBe('Company prices a registered direct offering');
  });

  it('says a halt before anything else, with the return time only when the exchange listed one', () => {
    const f = face({ mark: 'flame', word: 'News', kind: 'news' });
    expect(phoneCatalyst({ face: f, verdict: verdict({}), halted: true, nowMs: NOW })).toMatchObject({ word: 'Halted', when: '', tone: 'bad' });
    // 2026-11-11 09:36 ET is 14:36 UTC.
    const resume = Date.UTC(2026, 10, 11, 14, 36) / 1000;
    expect(phoneCatalyst({ face: f, verdict: verdict({}), halted: true, resumeTs: resume, nowMs: NOW }).when).toBe('back 09:36');
  });

  it('marks bad news red and a cause that is not news plain', () => {
    expect(phoneCatalyst({ face: face({ mark: 'negative', word: 'Delisting', kind: 'news' }), verdict: verdict({}), halted: false, nowMs: NOW }).tone).toBe('bad');
    expect(phoneCatalyst({ face: face({ mark: 'squeeze', word: 'Squeeze', detail: '84% of float short', kind: 'short_squeeze' }), verdict: null, halted: false, nowMs: NOW }))
      .toMatchObject({ word: 'Squeeze', when: '84% of float short', tone: 'plain' });
  });

  it("falls back to the row's own news verdict while the cause is not read", () => {
    expect(phoneCatalyst({ face: face({}), verdict: verdict({}), halted: false, nowMs: NOW }))
      .toMatchObject({ word: 'News', when: '9m ago', tone: 'news', headline: 'A headline' });
    expect(phoneCatalyst({ face: face({ mark: 'reading', kind: 'reading' }), verdict: verdict({}), halted: false, nowMs: NOW }).word).toBe('Reading');
    expect(phoneCatalyst({ face: face({}), verdict: verdict({ verdict: 'negative', category: null }), halted: false, nowMs: NOW }))
      .toMatchObject({ word: 'News', tone: 'bad' });
  });

  it('says "No news found" only when the classifier looked and found none', () => {
    expect(phoneCatalyst({ face: face({}), verdict: verdict({ verdict: 'none_found', title: null, url: null }), halted: false, nowMs: NOW }))
      .toMatchObject({ word: 'No news', when: 'found' });
    // Not checked is not "none": a dash.
    expect(phoneCatalyst({ face: face({}), verdict: verdict({ verdict: 'not_checked' }), halted: false, nowMs: NOW }).word).toBe('—');
    expect(phoneCatalyst({ face: face({}), verdict: null, halted: false, nowMs: NOW }).word).toBe('—');
    expect(phoneCatalyst({ face: face({ mark: 'reading', kind: 'reading' }), verdict: null, halted: false, nowMs: NOW }).word).toBe('Reading');
  });
});

describe('no screen scrolls', () => {
  it('leaves a viewport at least as large as the drawing alone', () => {
    expect(fitFor({ width: 360, height: 720 }, PORTRAIT)).toEqual({ zoom: 1, width: 360, height: 720 });
    expect(fitFor({ width: 412, height: 800 }, PORTRAIT)).toEqual({ zoom: 1, width: 412, height: 800 });
  });

  it('shrinks the whole page by one factor when the viewport is smaller, on whichever side is short', () => {
    // A browser tab with its address bar showing.
    const tab = fitFor({ width: 360, height: 648 }, PORTRAIT);
    expect(tab.zoom).toBeCloseTo(0.9);
    expect(tab.width).toBeCloseTo(400);
    expect(tab.height).toBeCloseTo(720);
    const side = fitFor({ width: 666, height: 320 }, LANDSCAPE);
    expect(side.zoom).toBeCloseTo(0.9);
    expect(side.height * side.zoom).toBeCloseTo(320);
  });

  it('shows as many rows as fit and never none', () => {
    expect(rowsThatFit(516, 42)).toBe(12);
    expect(rowsThatFit(503.6, 42)).toBe(12);
    expect(rowsThatFit(503, 42)).toBe(11);
    expect(rowsThatFit(10, 42)).toBe(1);
    expect(rowsThatFit(0, 42)).toBe(1);
  });
});

describe('the loss limit of the venue on screen', () => {
  const view = (over: Partial<LossLimitView> = {}): LossLimitView => ({
    schema_version: 1,
    settings: { limit_usd: 300, you_usd: null, bots_usd: null, warn: true, no_new_buys: true, auto_sell: false, set_at: null, source: 'operator', error: null },
    day: '2026-11-11',
    until: 0,
    accounts: {
      paper: {
        name: 'Paper', counted_at: 1, pnl: -120, loss: 120, unknown: null,
        lines: { account: { on: true, pnl: -120, loss: 120, warned_at: null, warned_loss: null, tripped_at: null, tripped_loss: null, limit_usd: null, sold: null, sell_error: null, no_new_buys: null } },
      },
    },
    error: null,
    ...over,
  });

  it("reads the Account line's loss against the limit", () => {
    expect(lossLimitFor(view(), 'paper')).toEqual({ used: 120, limit: 300, stopped: null, warned: false, error: null });
  });

  it('shows a profit as nothing used, and an uncounted account as unknown, not zero', () => {
    const gain = view();
    gain.accounts.paper!.lines.account!.loss = -40;
    expect(lossLimitFor(gain, 'paper').used).toBe(0);
    expect(lossLimitFor(view(), 'live')).toMatchObject({ used: null, limit: 300 });
    expect(lossLimitFor(null, 'paper')).toMatchObject({ used: null, limit: null });
  });

  it("says a trip in the desk's own words", () => {
    const tripped = view();
    tripped.accounts.paper!.lines.account!.no_new_buys = { text: 'No new buys until 04:00 ET', until: 5 };
    tripped.accounts.paper!.lines.account!.warned_at = 3;
    expect(lossLimitFor(tripped, 'paper')).toMatchObject({ stopped: 'No new buys until 04:00 ET', warned: true });
  });
});
