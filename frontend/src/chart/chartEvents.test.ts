import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { dayWords, eventCard, moneyWords, normalizeChartEvents, placeEvents, type ChartEvent } from './chartEvents';

// MNDR as the desk reads it (Webull's marks: 03/12/2026 "2026 H1", revenue 3.95M USD; 06/29/2026 1 for 6).
const MNDR = {
  symbol: 'MNDR', status: 'read',
  earnings: {
    status: 'read', releases_known_since: '2024-09-12', foreign_6k: true,
    scan: { since: '2024-09-12', listed: 38, pending: 0, failed: 0 },
    events: [{
      id: 'earnings:0001493152-26-009765', kind: 'earnings', day: '2026-03-12',
      release: { form: '6-K', accession: '0001493152-26-009765', day: '2026-03-12', filed: '2026-03-12' },
      other_releases: [],
      report: null, report_pending: true,
      said: 'Mobile-health Network Solutions Announces Unaudited Interim 2026 Financial Results',
      period_label: '2026 H1', period_end: '2025-12-31', period_months: 6,
      revenue: { value: 3948768, unit: 'USD', form: 'F-1/A', filed: '2026-04-17' },
      net_income: null, eps: { value: -0.51, unit: 'USD/shares', form: 'F-1/A', filed: '2026-04-17' },
    }, { id: 'earnings:bad', kind: 'earnings', day: 'not a day' }],
  },
  splits: {
    status: 'read', lists: { massive: { status: 'read' }, sec_confirmed: { status: 'absent' }, yahoo: { status: 'read' } },
    events: [{ id: 'split:2026-06-29', kind: 'split', day: '2026-06-29', ratio: 1 / 6, new_shares: 1, old_shares: 6,
      reverse: true, sources: ['massive', 'yahoo'], disagreement: null }],
  },
};

describe('normalizeChartEvents', () => {
  it('keeps the events, drops a malformed one, and says how far back 6-K results are read', () => {
    const read = normalizeChartEvents(MNDR, 'MNDR');
    expect(read.events.map((e) => e.id)).toEqual(['earnings:0001493152-26-009765', 'split:2026-06-29']);
    expect(read.busy).toBe(false);
    expect(read.notes).toEqual([]);
    expect(read.coverage).toContain('Sep 12, 2024');
  });

  it('is busy while 6-Ks are being read and names a list it could not read', () => {
    const raw = {
      ...MNDR,
      earnings: { ...MNDR.earnings, scan: { ...MNDR.earnings.scan, pending: 12 } },
      splits: { ...MNDR.splits, lists: { yahoo: { status: 'error', error: 'TimeoutError' } } },
    };
    const read = normalizeChartEvents(raw, 'MNDR');
    expect(read.busy).toBe(true);
    expect(read.notes).toEqual(['Yahoo split list could not be read (TimeoutError).']);
  });

  it('says a symbol SEC does not list, and a desk still reading', () => {
    expect(normalizeChartEvents({ status: 'read', earnings: { status: 'no_cik', events: [] } }, 'X').notes[0])
      .toContain('SEC lists no registrant');
    expect(normalizeChartEvents({ status: 'reading' }, 'X').busy).toBe(true);
  });
});

describe('placeEvents', () => {
  const days = ['2026-03-11', '2026-03-12', '2026-03-13', '2026-03-16', '2026-06-26', '2026-06-29'] as Time[];
  const ev = (day: string): ChartEvent => normalizeChartEvents({
    status: 'read', splits: { events: [{ id: `split:${day}`, kind: 'split', day, ratio: 2, new_shares: 2, old_shares: 1 }] },
  }, 'X').events[0];

  it('puts a daily mark on its own candle, or the next one after a weekend', () => {
    expect(placeEvents([ev('2026-03-12')], days, '1Day')[0].time).toBe('2026-03-12');
    expect(placeEvents([ev('2026-03-14')], days, '1Day')[0].time).toBe('2026-03-16');
  });

  it('draws nothing past the newest candle, nor on a candle more than a week later', () => {
    expect(placeEvents([ev('2026-06-30')], days, '1Day')).toEqual([]);
    expect(placeEvents([ev('2026-04-01')], days, '1Day')).toEqual([]);
  });

  it('puts a weekly or monthly mark on the candle that holds its day', () => {
    const weeks = ['2026-03-02', '2026-03-09', '2026-03-16'] as Time[];
    expect(placeEvents([ev('2026-03-12')], weeks, '1Week')[0].time).toBe('2026-03-09');
    expect(placeEvents([ev('2026-03-20')], weeks, '1Week')[0].time).toBe('2026-03-16');
    expect(placeEvents([ev('2026-03-24')], weeks, '1Week')).toEqual([]);
    const months = ['2026-02-02', '2026-03-02'] as Time[];
    expect(placeEvents([ev('2026-03-31')], months, '1Month')[0].time).toBe('2026-03-02');
    expect(placeEvents([ev('2026-04-01')], months, '1Month')).toEqual([]);
  });
});

describe('eventCard', () => {
  const [earnings, split] = normalizeChartEvents(MNDR, 'MNDR').events;

  it("reads like Webull's card: date, period, revenue, with where a later-tagged figure came from", () => {
    const card = eventCard(earnings, 'Results filed on Form 6-K are read from Sep 12, 2024.');
    const rows = Object.fromEntries(card.rows.map((r) => [r.label, r]));
    expect(rows.Date.value).toBe('Mar 12, 2026');
    expect(rows.Period.value).toBe('2026 H1 · 6 months to Dec 31, 2025');
    expect(rows.Revenue.value).toBe('3.95M USD');
    expect(rows.Revenue.note).toBe('as tagged in the F-1/A of Apr 17, 2026');
    expect(rows.EPS.value).toBe('-0.51 USD');
    expect(rows.Report.value).toBe('not filed yet');
    expect(card.quote).toContain('Interim 2026 Financial Results');
    expect(card.source).toBe('SEC EDGAR');
    expect(card.coverage).toContain('Form 6-K');
  });

  it('names a reverse split in shares and every list that has it', () => {
    const card = eventCard(split);
    expect(card.title).toBe('Reverse split');
    expect(card.rows).toEqual([{ label: 'Date', value: 'Jun 29, 2026' }, { label: 'Reverse split', value: '1 for 6' }]);
    expect(card.source).toBe('Listed by Massive · Yahoo');
  });
});

describe('words', () => {
  it('writes money at the precision reports state it, and days in full', () => {
    expect(moneyWords(3948768)).toBe('3.95M');
    expect(moneyWords(-1_204_000_000)).toBe('-1.20B');
    expect(moneyWords(950_000)).toBe('950.0K');
    expect(dayWords('2026-06-29')).toBe('Jun 29, 2026');
    expect(dayWords(null)).toBe('—');
  });
});
