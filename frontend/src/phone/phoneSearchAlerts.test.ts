/**
 * The phone's Search, its HOD Momo list and its notification settings (mockup v1, 2026-11-18): the pure
 * parts. The matching, the alert folding and the sending rules are the desk's and the PC's, tested where
 * they live; these are the words and the arithmetic the phone adds.
 */
import { describe, expect, it } from 'vitest';
import type { AlertObject } from '../hod_momo/types';
import {
  anyKindOn,
  daysText,
  lastSentText,
  notifySummary,
  parseNotifyView,
  stepHours,
  toggleDay,
  type NotifySettings,
  type NotifyView,
} from './notify/phoneNotify';
import { keyBytes } from './notify/pushClient';
import { hodRowIsNew, hodShortName, phoneHodRows } from './phoneHod';
import { parseRoute, routeHash, tabOf } from './phoneRoute';
import { hotOptions, searchFootText, searchRows, searchTag, shortCompanyName, type SearchTagSources } from './phoneSearch';

const NOWHERE: SearchTagSources = { hodAt: new Map(), boards: [], hot: new Set() };

describe('search rows', () => {
  it('cuts the share class off a company name and keeps the company', () => {
    expect(shortCompanyName('Global Mofy AI Limited Class A Ordinary Shares')).toBe('Global Mofy AI Limited');
    expect(shortCompanyName('Highway Holdings Limited Common Stock')).toBe('Highway Holdings Limited');
    expect(shortCompanyName('SaverOne 2014 Ltd. American Depositary Shares')).toBe('SaverOne 2014 Ltd.');
    expect(shortCompanyName('GameStop Corp. Class A')).toBe('GameStop Corp.');
    expect(shortCompanyName('Genmab A/S ADS')).toBe('Genmab A/S');
    expect(shortCompanyName('Tradr 2X Long NBIS Daily ETF')).toBe('Tradr 2X Long NBIS Daily ETF');
    // A name that is nothing but a share class is kept whole, never emptied.
    expect(shortCompanyName('Common Stock')).toBe('Common Stock');
  });

  it('says where a stock is on the desk: HOD Momo first, then its place on a board, then the hot list', () => {
    const src: SearchTagSources = {
      hodAt: new Map([['GMM', '07:43']]),
      boards: [{ name: 'Gainers', symbols: ['NBIG', 'GMM'] }, { name: 'Gappers', symbols: ['GP'] }],
      hot: new Set(['GP', 'HIHO']),
    };
    expect(searchTag('GMM', src)).toBe('HOD Momo 07:43');
    expect(searchTag('NBIG', src)).toBe('Gainers #1');
    expect(searchTag('GP', src)).toBe('Gappers #1');
    expect(searchTag('HIHO', src)).toBe('Hot list');
    expect(searchTag('GME', src)).toBeNull();
  });

  it('keeps the desk\'s order and its typed-first row, and never invents a move', () => {
    const rows = searchRows([
      { symbol: 'GMX', suggestion: null },
      { symbol: 'GMM', suggestion: { symbol: 'GMM', source: 'gainers', movePct: 21.6, name: 'Global Mofy AI Limited Class A Ordinary Shares', exchange: 'NASDAQ', symbolMatch: [0, 2], nameMatch: null } },
      { symbol: 'GME', suggestion: { symbol: 'GME', source: 'listed', movePct: null, name: 'GameStop Corp. Class A', exchange: 'NYSE', symbolMatch: [0, 2], nameMatch: null } },
    ], NOWHERE);
    expect(rows.map((r) => r.symbol)).toEqual(['GMX', 'GMM', 'GME']);
    expect(rows[0]).toMatchObject({ typed: true, name: null, movePct: null });
    expect(rows[1]).toMatchObject({ typed: false, name: 'Global Mofy AI Limited', movePct: 21.6, match: [0, 2] });
    expect(rows[2].movePct).toBeNull();
  });

  it('lists today\'s hot list with the change the list holds, as percent points', () => {
    const options = hotOptions(
      [{ symbol: 'NBIG', change_pct: 0.1277 }, { symbol: 'GP', change_pct: null }],
      ['NBIG', 'GP', 'ZZZZ'],
      { bySymbol: new Map([['NBIG', { name: 'Leverage Shares 2X Long NBIS Daily ETF', exchange: 'NASDAQ' }]]) },
    );
    expect(options[0].suggestion).toMatchObject({ movePct: expect.closeTo(12.77, 6), name: 'Leverage Shares 2X Long NBIS Daily ETF', exchange: 'NASDAQ' });
    expect(options[1].suggestion).toMatchObject({ movePct: null, name: null });
    expect(options[2].suggestion?.movePct).toBeNull();
  });

  it('says how many matches there are beyond the rows that fit', () => {
    expect(searchFootText(7, 32, null)).toBe('7 of 32 matches · keep typing to narrow');
    expect(searchFootText(3, 3, null)).toBe('3 matches');
    expect(searchFootText(1, 1, null)).toBe('1 match');
    expect(searchFootText(0, 0, 'No symbol or company matches')).toBe('No symbol or company matches');
  });
});

function alert(over: Partial<AlertObject>): AlertObject {
  return {
    id: `${over.ticker}-${over.timestamp}-${over.strategy_id}`, timestamp: '2026-11-18T12:43:55.000Z', ticker: 'GMM',
    strategy_id: 11, strategy_name: 'Squeeze Alert - Up 5% in 5min', price: 1.7089, change_pct: 21.6, rvol: 92.59,
    float_shares: 559949, gap_pct: null, volume: 13039956, momentum_pct: null, rvol_source: null,
    consolidation_count: 1, consolidated_ids: [], ...over,
  };
}

describe('the HOD Momo list', () => {
  // Newest first, as the feed sends them.
  const feed = [
    alert({ ticker: 'DUKR', strategy_id: 12, strategy_name: 'Running Up Alert', timestamp: '2026-11-18T12:51:59.000Z' }),
    alert({ ticker: 'HIHO', timestamp: '2026-11-18T12:47:58.000Z', price: 1.44, change_pct: 16.3 }),
    alert({ ticker: 'GMM', timestamp: '2026-11-18T12:43:55.000Z' }),
    alert({ ticker: 'GMM', strategy_id: 12, strategy_name: 'Running Up Alert', timestamp: '2026-11-18T12:40:00.000Z' }),
    alert({ ticker: 'GMM', strategy_id: 10, strategy_name: 'Squeeze Alert - Up 10% in 10min', timestamp: '2026-11-18T11:02:10.000Z', price: 1.2, change_pct: null }),
  ];

  it('is one row per stock from the desk\'s split, at the time of its first alert, with its newest numbers', () => {
    const rows = phoneHodRows(feed, 'hod_momo');
    expect(rows.map((r) => r.symbol)).toEqual(['HIHO', 'GMM']);
    expect(rows[1]).toMatchObject({ at: '06:02', strategy: 'Up 5% / 5m', count: 2, price: 1.7089, change: expect.closeTo(0.216, 6), volume: 13039956 });
    expect(rows[0]).toMatchObject({ at: '07:47', count: 1, change: expect.closeTo(0.163, 6) });
  });

  it('keeps Running Up as its own list and leaves the feed\'s own rows untouched', () => {
    const before = JSON.stringify(feed);
    expect(phoneHodRows(feed, 'running_up').map((r) => [r.symbol, r.strategy, r.count])).toEqual([
      ['DUKR', 'Running up', 1], ['GMM', 'Running up', 1],
    ]);
    expect(JSON.stringify(feed)).toBe(before);
  });

  it('a change the alert did not carry stays unknown, and an unlisted strategy keeps the desk\'s name', () => {
    const [row] = phoneHodRows([alert({ change_pct: null })], 'hod_momo');
    expect(row.change).toBeNull();
    expect(hodShortName(99, 'A new strategy')).toBe('A new strategy');
  });

  it('marks a stock that first alerted in the last two minutes', () => {
    const atMs = Date.parse('2026-11-18T12:47:58.000Z');
    expect(hodRowIsNew({ atMs }, atMs + 60_000)).toBe(true);
    expect(hodRowIsNew({ atMs }, atMs + 121_000)).toBe(false);
    expect(hodRowIsNew({ atMs: null }, atMs)).toBe(false);
  });
});

const SETTINGS: NotifySettings = {
  schema_version: 1, hod_momo: 'stars', setups: true, new_leader: false, fills: true, loss_limit: true,
  days: [0, 1, 2, 3, 4], start: '07:00', end: '11:00',
};
const VIEW: NotifyView = {
  schema_version: 1, available: true, why_unavailable: null, public_key: 'BKey', settings: SETTINGS,
  device_ids: ['0123456789abcdef'], last_sent: null,
};

describe('notification settings', () => {
  it('steps the hours by half hours, inside the desk\'s day, the start before the end', () => {
    expect(stepHours(SETTINGS, 'start', -1)).toEqual({ start: '06:30', end: '11:00' });
    expect(stepHours(SETTINGS, 'end', 1)).toEqual({ start: '07:00', end: '11:30' });
    expect(stepHours({ start: '04:00', end: '11:00' }, 'start', -1)).toBeNull();
    expect(stepHours({ start: '07:00', end: '20:00' }, 'end', 1)).toBeNull();
    expect(stepHours({ start: '10:30', end: '11:00' }, 'start', 1)).toBeNull();
    expect(stepHours({ start: '10:30', end: '11:00' }, 'end', -1)).toBeNull();
    expect(stepHours({ start: 'soon', end: '11:00' }, 'end', 1)).toBeNull();
  });

  it('words the days and the summary row', () => {
    expect(daysText([0, 1, 2, 3, 4])).toBe('Mon to Fri');
    expect(daysText([0, 1, 2, 3, 4, 5, 6])).toBe('Every day');
    expect(daysText([4, 0, 2])).toBe('Mon, Wed, Fri');
    expect(daysText([5, 6])).toBe('Sat, Sun');
    expect(daysText([])).toBe('No day');
    expect(toggleDay([0, 1], 1)).toEqual([0]);
    expect(toggleDay([4, 0], 2)).toEqual([0, 2, 4]);

    expect(notifySummary(VIEW, 'on')).toBe('On · Mon to Fri · 07:00 to 11:00');
    expect(notifySummary(VIEW, 'on', 'short')).toBe('On · 07:00 to 11:00');
    expect(notifySummary(VIEW, 'off')).toBe('Off');
    expect(notifySummary(VIEW, 'blocked', 'short')).toBe('Blocked');
    expect(notifySummary(null, 'unknown')).toBe('…');
    const nothing = { ...VIEW, settings: { ...SETTINGS, hod_momo: 'off' as const, setups: false, fills: false, loss_limit: false } };
    expect(anyKindOn(nothing.settings)).toBe(false);
    expect(notifySummary(nothing, 'on')).toBe('On · nothing chosen yet');
  });

  it('says the last one sent in New York time, or why it did not go', () => {
    const at = Date.parse('2026-11-18T12:43:00.000Z') / 1000;
    expect(lastSentText(null)).toBe('Nothing sent yet');
    expect(lastSentText({ at, title: 'GMM hit HOD Momo', ok: true, error: null })).toBe('Last sent 07:43 · GMM hit HOD Momo');
    expect(lastSentText({ at, title: 'x', ok: false, error: 'the push service answered 500' })).toBe('Not delivered 07:43 · the push service answered 500');
  });

  it('reads the PC\'s answer and refuses a shape it does not know', () => {
    expect(parseNotifyView(JSON.parse(JSON.stringify(VIEW)))).toEqual(VIEW);
    expect(parseNotifyView({ ...VIEW, schema_version: 2 })).toBeNull();
    expect(parseNotifyView({ ...VIEW, settings: { ...SETTINGS, hod_momo: 'loud' } })).toBeNull();
    expect(parseNotifyView({ ...VIEW, settings: { ...SETTINGS, start: '7' } })).toBeNull();
    expect(parseNotifyView(null)).toBeNull();
  });

  it('turns the PC\'s public key into the bytes the browser subscribes with', () => {
    expect([...keyBytes('AQID-_8')]).toEqual([1, 2, 3, 251, 255]);
  });
});

describe('the new screens\' routes', () => {
  it('names Search and Notifications in the hash; Search lights the Scan tab', () => {
    expect(parseRoute('#/search')).toEqual({ screen: 'search' });
    expect(parseRoute('#/notify')).toEqual({ screen: 'notify' });
    expect(routeHash({ screen: 'search' })).toBe('#/search');
    expect(tabOf({ screen: 'search' })).toBe('scan');
    expect(tabOf({ screen: 'notify' })).toBeNull();
    // What a tapped notification names.
    expect(parseRoute('#/trade/GMM')).toEqual({ screen: 'trade', symbol: 'GMM' });
  });
});
