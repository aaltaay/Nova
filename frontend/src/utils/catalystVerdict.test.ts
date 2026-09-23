import { describe, expect, it } from 'vitest';
import type { CatalystVerdict } from '../types/catalystVerdict';
import {
  catalystHeadline,
  isCompanyNews,
  newsMark,
  normalizeCatalystVerdict,
  verdictTooltip,
} from './catalystVerdict';

const NOW_MS = 1_790_000_000_000;
const base: CatalystVerdict = {
  verdict: 'catalyst', category: 'merger_acquisition', strength: 'weak', rules_version: 'v5',
  title: 'Healthcare Triangle Signs Letter of Intent to Acquire Roboticom', source: 'prnewswire',
  published_ts: NOW_MS / 1000 - 40 * 60, url: null, negative_too: false, sources_answered: ['alpaca', 'prnewswire'],
};

describe('normalizeCatalystVerdict', () => {
  it('reads a verdict and refuses anything else', () => {
    expect(normalizeCatalystVerdict({ ...base, published_ts: 'x', strength: 'huge' })).toMatchObject({
      verdict: 'catalyst', published_ts: null, strength: null,
    });
    expect(normalizeCatalystVerdict({ verdict: 'maybe' })).toBeNull();
    expect(normalizeCatalystVerdict(null)).toBeNull();
  });
});

describe('newsMark', () => {
  it('lights a flame only for a placed catalyst, by its age', () => {
    expect(newsMark(base, NOW_MS)).toMatchObject({ kind: 'flame', ageClass: 'flame-hot' });
    expect(newsMark({ ...base, category: 'company_news' }, NOW_MS).kind).toBe('ring');
    expect(newsMark({ ...base, published_ts: NOW_MS / 1000 - 20 * 3600 }, NOW_MS).ageClass).toBe('flame-cool');
  });
  it('marks bad news, a halt for news and routine items, and gives lists nothing', () => {
    expect(newsMark({ ...base, verdict: 'negative', category: 'delisting_split' }, NOW_MS).kind).toBe('negative');
    expect(newsMark({ ...base, verdict: 'none_found', news_pending: true, halt_code: 'T1' }, NOW_MS).kind).toBe('pending');
    expect(newsMark({ ...base, verdict: 'routine_only' }, NOW_MS).kind).toBe('routine');
    expect(newsMark({ ...base, verdict: 'noise_only' }, NOW_MS).kind).toBe('none');
    expect(newsMark(null, NOW_MS).kind).toBe('none');
  });
});

describe('verdictTooltip', () => {
  it('says what the catalyst is, where from, how old and what was checked', () => {
    const tip = verdictTooltip(base, NOW_MS);
    expect(tip).toContain('Catalyst: Merger / acquisition (weak)');
    expect(tip).toContain('Healthcare Triangle Signs Letter of Intent');
    expect(tip).toContain('PR Newswire · 40m ago');
    expect(tip).toContain('Checked: Alpaca, PR Newswire');
  });
  it('says a market wrap is not news, and an unread verdict is unread', () => {
    expect(verdictTooltip({ ...base, verdict: 'noise_only' }, NOW_MS)).toContain('Only movers lists');
    expect(verdictTooltip(null, NOW_MS)).toBe('News not read yet for this symbol');
  });
});

describe('catalystHeadline / isCompanyNews', () => {
  it('drops the EDGAR form prefix only for EDGAR', () => {
    expect(catalystHeadline('8-K: Regulation FD | Beneficient Announces Strategy', 'edgar')).toBe('Beneficient Announces Strategy');
    expect(catalystHeadline('A | B', 'alpaca')).toBe('A | B');
  });
  it('counts a catalyst, bad news and a halt for news', () => {
    expect(isCompanyNews(base)).toBe(true);
    expect(isCompanyNews({ ...base, verdict: 'negative' })).toBe(true);
    expect(isCompanyNews({ ...base, verdict: 'noise_only' })).toBe(false);
    expect(isCompanyNews(null)).toBe(false);
  });
});
